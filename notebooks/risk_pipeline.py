"""
risk_pipeline.py — procena rizika vozaca uzivo iz cabin kamere (samo vozac).

Slojevi (svaki je zamenljiv):
  1. Percepcija       MediaPipe Face/Hand Landmarker + YOLO (ONNX preko cv2.dnn) [+ opciono CLIP]
  2. FeatureExtractor sirovi izlazi -> dokaz p_i(n) in [0,1] za svaku kategoriju rizika
  3. RiskEngine       matematika po frejmu: zagladjivanje, trajanje, grupe, pravila, alarm
  4. Izlaz            dev: frames.jsonl + prikaz;  prod: zapis frejma -> backend (POST /telemetry)

Statistiku cele voznje (rezime, epizode ponasanja, alarmi) vise ne racuna pipeline, nego backend
iz toka zapisa frejmova (backend/app/services/model_report.py -> GET /trips/{id}/report, polje "model").

Modovi:
  python risk_pipeline.py --video snimak.mp4                      # dev (podrazumevano): video + metrike
  python risk_pipeline.py --video 0 --mode prod                   # prod: bez prozora, salje backendu
  python risk_pipeline.py --video snimak.mp4 --mode prod --start-trip demo   # prod sa snimkom, bez telefona

Ugradjeni sistem: preskoceni frejmovi se samo grab()-uju (bez dekodiranja slike),
teski modeli rade redje (schedule u konfiguraciji), a sve vremenske velicine
racunaju se iz stvarnih timestamp-ova, pa preskakanje frejmova ne kvari model.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import deque
from pathlib import Path

import numpy as np

LEVELS = ["green", "yellow", "red"]


# ----------------------------------------------------------------------------
# Pomocne funkcije
# ----------------------------------------------------------------------------
def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def ema_alpha(dt: float, tau: float) -> float:
    """Vremenski konzistentan EMA koeficijent (radi i kad se preskacu frejmovi)."""
    if dt <= 0 or tau <= 0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


def r3(x: float) -> float:
    return round(float(x), 3)




# ----------------------------------------------------------------------------
# 3. RISK ENGINE — cista matematika po frejmu, bez zavisnosti od modela (lako za test)
#    Statistika cele voznje (rezime, epizode, alarmi) NIJE ovde: racuna je backend iz toka ovih
#    zapisa (backend/app/services/model_report.py), pa ista logika vazi i uzivo i za izvestaj.
# ----------------------------------------------------------------------------
class _Cat:
    __slots__ = ("name", "cfg", "p_hat", "active", "D", "run")

    def __init__(self, name, cfg):
        self.name, self.cfg = name, cfg
        self.p_hat, self.active, self.D, self.run = 0.0, False, 0.0, 0.0

    def duration_factor(self) -> float:
        """h_i(D) = b + (1-b) * s(D), s = normalizovana logisticka kriva, s(0)=0, s(inf)=1."""
        c = self.cfg
        k, T, b = c["k"], c["T_crit_s"], c["base"]
        s0 = sigmoid(-k * T)
        s = (sigmoid(k * (self.D - T)) - s0) / (1.0 - s0)
        return b + (1.0 - b) * clip01(s)


class RiskEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.groups = cfg["groups"]
        self.cats = {n: _Cat(n, c) for n, c in cfg["categories"].items()}
        self.tau_e = cfg["smoothing"]["evidence_tau_s"]
        self.tau_r = cfg["smoothing"]["risk_tau_s"]
        self.t_prev = None
        self.R_smooth = 0.0
        # VATS (Euro NCAP short distraction) stanje
        self.vats_buf: deque = deque()
        self.on_road_run = 0.0
        # alarm stanje
        self.a = cfg["alerts"]
        self.level, self.level_since = 0, 0.0
        self.rise_t, self.fall_t = 0.0, 0.0

    # ---------------------------------------------------------------- korak
    def step(self, t: float, evidence: dict, speed_kmh: float | None = None) -> dict:
        """Jedan korak modela u trenutku t. Vraca zapis frejma (red u frames.jsonl, isto ide backendu)."""
        dt = 0.0 if self.t_prev is None else max(0.0, t - self.t_prev)
        self.t_prev = t

        # (1) zagladjivanje dokaza, (2) histerezis, (3) akumulator trajanja, (4) doprinos r_i
        a_e = ema_alpha(dt, self.tau_e) if dt > 0 else 1.0
        cat_out, r = {}, {}
        for n, c in self.cats.items():
            cc = c.cfg
            p = clip01(float(evidence.get(n, 0.0)))
            c.p_hat += a_e * (p - c.p_hat)
            was = c.active
            if not c.active and c.p_hat >= cc["on"]:
                c.active = True
            elif c.active and c.p_hat < cc["off"]:
                c.active = False
            if c.active:
                c.D += dt
                c.run = c.run + dt if was else 0.0
            else:
                c.D = max(0.0, c.D - cc["decay"] * dt)
                c.run = 0.0
            h = c.duration_factor()
            r[n] = cc["weight"] * c.p_hat * h
            cat_out[n] = {"p": r3(p), "p_hat": r3(c.p_hat), "active": c.active,
                          "run_s": r3(c.run), "D_s": r3(c.D), "h": r3(h), "r": r3(r[n])}

        # (5) agregacija: max unutar grupe (korelisane kategorije), noisy-OR izmedju grupa
        R_g = {}
        for g in self.groups:
            R_g[g] = max((cc.cfg["membership"].get(g, 0.0) * r[n] for n, cc in self.cats.items()), default=0.0)
        prod = 1.0
        for g in self.groups:
            prod *= (1.0 - R_g[g])
        R_raw = 1.0 - prod

        # (6) kontekst (brzina, ako je dostupna preko CAN-a)
        ctx = self.cfg["context"]
        cf = 1.0
        if ctx.get("use_speed") and speed_kmh is not None and speed_kmh < ctx["speed_min_kmh"]:
            cf = ctx["stationary_factor"]

        # (7) vremensko zagladjivanje ukupnog rizika
        self.R_smooth += ema_alpha(dt, self.tau_r) * (cf * R_raw - self.R_smooth) if dt > 0 else 0.0
        if dt == 0:
            self.R_smooth = cf * R_raw

        # (8) tvrda pravila (Euro NCAP inspirisana) -> donja granica rizika
        floor, fired, vats_cum = self._rules(dt)
        R = max(self.R_smooth, cf * floor)

        # (9) alarm sa histerezisom
        self._alert(t, dt, R, fired)

        top = [n for n, v in sorted(r.items(), key=lambda kv: -kv[1]) if v > 0.05][:3]
        return {
            "t": r3(t), "dt": r3(dt),
            "categories": cat_out,
            "groups": {g: r3(v) for g, v in R_g.items()},
            "risk": {"raw": r3(R_raw), "context_factor": r3(cf), "smoothed": r3(self.R_smooth),
                     "floor": r3(cf * floor), "final": r3(R)},
            "rules_triggered": sorted(fired),
            "vats_cum_s": r3(vats_cum),
            "alert": {"level": LEVELS[self.level], "code": self.level},
            "top_contributors": top,
        }

    # ---------------------------------------------------------------- pravila
    def _rules(self, dt):
        floor, fired = 0.0, set()
        eor = self.cats.get("eyes_off_road")
        ph = self.cats.get("phone_use")
        off_road = (eor is not None and eor.active) or (ph is not None and ph.active)
        # VATS bafer: kumulativno vreme pogleda van puta u kliznom prozoru
        vats_cum = 0.0
        for rule in self.cfg["rules"]:
            if rule["type"] == "duration":
                c = self.cats[rule["category"]]
                if c.active and c.run >= rule["min_s"]:
                    floor = max(floor, rule["floor"]); fired.add(rule["name"])
            elif rule["type"] == "vats":
                t = self.t_prev
                if off_road:
                    self.vats_buf.append((t, dt)); self.on_road_run = 0.0
                else:
                    self.on_road_run += dt
                    if self.on_road_run >= rule["reset_on_road_s"]:
                        self.vats_buf.clear()
                while self.vats_buf and self.vats_buf[0][0] < t - rule["window_s"]:
                    self.vats_buf.popleft()
                vats_cum = sum(d for _, d in self.vats_buf)
                if vats_cum >= rule["cum_s"]:
                    floor = max(floor, rule["floor"]); fired.add(rule["name"])
        return floor, fired, vats_cum

    # ---------------------------------------------------------------- alarm
    def _alert(self, t, dt, R, fired):
        a = self.a
        up = 2 if R >= a["red"]["on"] else 1 if R >= a["yellow"]["on"] else 0
        new = self.level
        if up > self.level:
            self.rise_t += dt
            if self.rise_t >= a["rise_hold_s"] or fired:
                new = up
            self.fall_t = 0.0
        else:
            self.rise_t = 0.0
            down = self.level
            if self.level == 2 and R < a["red"]["off"]:
                down = 1 if R >= a["yellow"]["off"] else 0
            elif self.level == 1 and R < a["yellow"]["off"]:
                down = 0
            if down < self.level:
                self.fall_t += dt
                if self.fall_t >= a["fall_hold_s"] and t - self.level_since >= a["min_display_s"]:
                    new = down
            else:
                self.fall_t = 0.0
        if new != self.level:
            self.level, self.level_since = new, t
            self.rise_t = self.fall_t = 0.0


# ----------------------------------------------------------------------------
# 2. FEATURE EXTRACTOR — percepcija -> dokaz p_i(n) za svaku kategoriju
# ----------------------------------------------------------------------------
EAT_DRINK_CLS = {39, 40, 41, 46, 47, 48, 52, 53, 54}   # COCO: bottle, wine glass, cup, banana, ...
PHONE_CLS = 67                                         # COCO: cell phone
COCO_NAMES = {39: "bottle", 40: "wine glass", 41: "cup", 46: "banana", 47: "apple", 48: "sandwich",
              52: "hot dog", 53: "pizza", 54: "donut", 67: "phone"}


def _prox(a, b, sigma=0.12):
    """Gausova blizina dve tacke u normalizovanim koordinatama."""
    if a is None or b is None:
        return 0.0
    d2 = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    return math.exp(-d2 / (sigma ** 2))


def _in_box(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def robust_mode(samples, radius=6.0):
    """Najgusci klaster (yaw, pitch) uzoraka: tacka sa najvise suseda u krugu `radius`, pa medijana tih suseda.
    Za razliku od medijane svih uzoraka, ne pomera se kad vozac deo vremena gleda u telefon."""
    a = np.asarray(samples, dtype=float)
    d = np.hypot(a[:, None, 0] - a[None, :, 0], a[:, None, 1] - a[None, :, 1])
    j = int((d < radius).sum(1).argmax())
    m = a[d[j] < radius]
    return float(np.median(m[:, 0])), float(np.median(m[:, 1])), len(m) / len(a)


def calib_usable(c, closure, gaze_down):
    """Uzorak za kalibraciju samo kad su oci jasno otvorene i pogled nije nadole."""
    return closure < c.get("calib_max_closure", 0.45) and gaze_down < c.get("calib_max_gaze_down", 0.25)


class HeadBaseline:
    """Poza glave koja znaci "gleda u put" (yaw0, pitch0), zavisi od polozaja kamere.

    mode "fixed": uvek prior iz konfiguracije (izmeriti sa --calibrate na snimku ciste voznje).
    mode "auto":  prvih duration_s sekundi skuplja uzorke (samo otvorene oci, pogled ne nadole) i uzima
                  najgusci klaster, ali ga drzi najvise max_shift_deg od priora. Tako kratki snimak na kome
                  vozac sve vreme kucka po telefonu ne moze da proglasi "telefon" za "put".
    """

    def __init__(self, c):
        self.mode = c.get("mode", "auto")
        self.prior = (float(c.get("prior_yaw_deg", 0.0)), float(c.get("prior_pitch_deg", 0.0)))
        self.max_shift = float(c.get("max_shift_deg", 10.0))
        self.dur = float(c.get("duration_s", 10.0))
        self.min_n = int(c.get("min_samples", 15))
        self.samples: list = []
        self.value = self.prior
        self.status = "fixed" if self.mode == "fixed" else "prior"

    def add(self, t, yaw, pitch, usable):
        if self.mode != "auto" or t > self.dur or not usable:
            return
        self.samples.append((yaw, pitch))
        if len(self.samples) >= self.min_n:
            y, p, _ = robust_mode(self.samples)
            s = self.max_shift
            y = self.prior[0] + max(-s, min(s, y - self.prior[0]))
            p = self.prior[1] + max(-s, min(s, p - self.prior[1]))
            self.value = (y, p)
            self.status = f"auto n={len(self.samples)}"


class FeatureExtractor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cal = cfg["calibration"]
        self.dr = cfg["drowsiness"]
        self.ph = cfg.get("phone", {})
        self.wheel = cfg["video"]["steering_wheel_roi"]
        self.baseline = HeadBaseline(self.cal)
        self.perclos_buf: deque = deque()
        self.jaw_run, self.yawn_counted = 0.0, False
        self.yawns: deque = deque()
        self.phone_mem, self.phone_mem_t = 0.0, -1e9
        self.t_prev = None

    def update(self, t, face, hands, objects):
        """
        face:    None ili dict(yaw, pitch, blend: dict, center: (x,y), ...)   [x,y normalizovani na ceo frejm]
        hands:   None (nije pokrenuto/zastarelo) ili lista dict(center=(x,y), pts=[...])
        objects: None ili lista dict(cls, conf, center=(x,y), box=(x0,y0,x1,y1))
        Vraca (evidence: dict kategorija->p, perception: dict za log i prikaz).
        """
        dt = 0.0 if self.t_prev is None else max(0.0, t - self.t_prev)
        self.t_prev = t
        c = self.cal
        ev, per = {}, {"face_found": face is not None, "n_faces": face["n_faces"] if face else 0}

        # ---- glava, pogled, oci
        if face is not None:
            yaw, pitch, bl = face["yaw"], face["pitch"], face["blend"]
            closure = 0.5 * (bl.get("eyeBlinkLeft", 0) + bl.get("eyeBlinkRight", 0))
            gaze_down = 0.5 * (bl.get("eyeLookDownLeft", 0) + bl.get("eyeLookDownRight", 0))
            self.baseline.add(t, yaw, pitch, calib_usable(c, closure, gaze_down))
            y0, p0 = self.baseline.value
            dyaw, dpitch = yaw - y0, pitch - p0
            s = c["angle_softness_deg"]
            p_yaw = sigmoid((abs(dyaw) - c["yaw_thr_deg"]) / s)
            p_pitch = sigmoid((abs(dpitch) - c["pitch_thr_deg"]) / s)
            p_head = max(p_yaw, p_pitch)
            # Kamera je iznad vozaca: kad gleda nadole (telefon, krilo) kapci se spuste, pa eyeBlink raste zajedno
            # sa eyeLookDown (izmereno na datasetu: closure 0.4-0.75 uz gaze_down 0.3-0.7). Zato pogled nadole
            # ne mnozimo sa (1 - closure), a zatvorene oci trazimo tek iznad visokog praga i bez pogleda nadole.
            p_gaze = sigmoid((gaze_down - c["gaze_down_thr"]) / 0.05)
            ev["eyes_off_road"] = max(p_head, p_gaze)
            ev["eyes_closed"] = sigmoid((closure - c["eye_closed_thr"]) / 0.05) * (1.0 - 0.7 * max(p_head, p_gaze))
            jaw = bl.get("jawOpen", 0.0)
            per.update(yaw_abs=r3(yaw), pitch_abs=r3(pitch), yaw=r3(dyaw), pitch=r3(dpitch),
                       p_yaw=r3(p_yaw), p_pitch=r3(p_pitch), p_head=r3(p_head), p_gaze=r3(p_gaze),
                       eye_closure=r3(closure), gaze_down=r3(gaze_down), jaw_open=r3(jaw))
        else:
            ev["eyes_off_road"] = c["face_missing_p"]
            ev["eyes_closed"] = 0.0
            closure, jaw, gaze_down = None, 0.0, 0.0
        per["baseline"] = [r3(self.baseline.value[0]), r3(self.baseline.value[1])]
        per["baseline_status"] = self.baseline.status

        # ---- pospanost: PERCLOS + zevanje
        if closure is not None:
            self.perclos_buf.append((t, dt, closure >= c["eye_closed_thr"]))
        while self.perclos_buf and self.perclos_buf[0][0] < t - self.dr["perclos_window_s"]:
            self.perclos_buf.popleft()
        tot = sum(d for _, d, _ in self.perclos_buf)
        perclos = sum(d for _, d, cl in self.perclos_buf if cl) / tot if tot > 20.0 else 0.0
        if jaw >= self.dr["yawn_jaw_thr"]:
            self.jaw_run += dt
            if self.jaw_run >= self.dr["yawn_min_s"] and not self.yawn_counted:
                self.yawns.append(t); self.yawn_counted = True
        else:
            self.jaw_run, self.yawn_counted = 0.0, False
        while self.yawns and self.yawns[0] < t - self.dr["yawn_window_s"]:
            self.yawns.popleft()
        p_perclos = clip01((perclos - self.dr["perclos_normal"]) / (self.dr["perclos_high"] - self.dr["perclos_normal"]))
        p_yawn = min(1.0, len(self.yawns) / self.dr["yawns_high"])
        ev["drowsiness"] = 1.0 - (1.0 - p_perclos) * (1.0 - p_yawn)
        per.update(perclos=r3(perclos), perclos_window_s=r3(tot), yawns_window=len(self.yawns))

        # ---- ruke na volanu
        # Detektor saka cesto ne vidi saku na volanu (mrak, fisheye, volan je zaklanja). Zato "nije videna" nije
        # isto sto i "skinuta": dokaz raste tek kad se saka VIDI van volana (vrednosti u cfg["hands"]).
        hc = self.cfg.get("hands", {})
        hand_ctrs = [h["center"] for h in (hands or [])]
        n_det = len(hand_ctrs)
        n_on = sum(1 for h in hand_ctrs if _in_box(h, self.wheel))
        n_off = n_det - n_on
        if n_det == 0:
            ev["hands_off_wheel"] = c["no_hands_detected_p"]
        elif n_on >= 2:
            ev["hands_off_wheel"] = 0.0
        elif n_on == 1:
            ev["hands_off_wheel"] = hc.get("one_on_other_off_p", 0.45) if n_off else hc.get("one_on_other_unseen_p", 0.2)
        else:
            ev["hands_off_wheel"] = hc.get("none_on_p", 0.85)
        per.update(hands_detected=n_det, hands_on_wheel=n_on, hands_fresh=hands is not None)

        # ---- telefon, hrana/pice (YOLO) — blizina saci ili licu
        fc = face["center"] if face is not None else None
        sig = self.ph.get("prox_sigma", 0.12)
        conf_full = self.ph.get("conf_full", 0.5)
        p_phone, p_eat, best = 0.0, 0.0, None
        lap = 0.6 * sigmoid((gaze_down - c["gaze_down_thr"]) / 0.05)   # telefon u krilu + pogled dole
        for o in (objects or []):
            ph = max([_prox(o["center"], h, sig) for h in hand_ctrs] + [0.0])
            pf = _prox(o["center"], fc, sig)
            conf = min(1.0, o["conf"] / conf_full)          # YOLO na ovoj kameri retko ide preko 0.6
            if o["cls"] == PHONE_CLS:
                p = conf * max(ph, pf, lap)
                if best is None or p > best["p"]:
                    best = {"p": r3(p), "conf": r3(o["conf"]), "near_hand": r3(ph), "near_face": r3(pf), "lap": r3(lap)}
                p_phone = max(p_phone, p)
            elif o["cls"] in EAT_DRINK_CLS:
                p_eat = max(p_eat, conf * pf)
        # YOLO vidi telefon samo na delu frejmova -> kratka memorija sa eksponencijalnim zaboravom
        tau = self.ph.get("hold_tau_s", 1.0)
        held = self.phone_mem * math.exp(-(t - self.phone_mem_t) / tau) if tau > 0 else 0.0
        if p_phone >= held:
            self.phone_mem, self.phone_mem_t = p_phone, t
        ev["phone_use"], ev["eating_drinking"] = max(p_phone, held), p_eat
        per["phone"] = best
        per["phone_now"], per["phone_held"] = r3(p_phone), r3(held)
        per["objects"] = [[int(o["cls"]), r3(o["conf"])] for o in (objects or [])]
        return ev, per


# ----------------------------------------------------------------------------
# 1. PERCEPCIJA — MediaPipe Tasks + YOLO ONNX (cv2.dnn, bez PyTorch-a na uredjaju)
# ----------------------------------------------------------------------------
def _to_full(pt, roi):
    """Koordinata iz isecka (ROI) -> normalizovana koordinata celog frejma."""
    x0, y0, x1, y1 = roi
    return (x0 + pt[0] * (x1 - x0), y0 + pt[1] * (y1 - y0))


def _crop(img, roi):
    H, W = img.shape[:2]
    return img[int(roi[1] * H):int(roi[3] * H), int(roi[0] * W):int(roi[2] * W)]


class FacePerception:
    """Lice se trazi u head_roi (uzak isecak oko glave vozaca). Detektor lica u MediaPipe-u radi na 128x128,
    pa je na celom frejmu glava vozaca premala i lice se gubi cim spusti glavu ili je mrak."""

    def __init__(self, model_path, num_faces=2, min_conf=0.4, side="right"):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp, self.side = mp, side
        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO, num_faces=num_faces,
            min_face_detection_confidence=min_conf, min_face_presence_confidence=min_conf,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True)
        self.lm = vision.FaceLandmarker.create_from_options(opts)

    def __call__(self, rgb, ts_ms, roi):
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts_ms)
        if not res.face_landmarks:
            return None
        cands = []
        for i, lms in enumerate(res.face_landmarks):
            xs = [p.x for p in lms]; ys = [p.y for p in lms]
            a, b = _to_full((min(xs), min(ys)), roi), _to_full((max(xs), max(ys)), roi)
            cands.append((i, (a[0], a[1], b[0], b[1]), (b[0] - a[0]) * (b[1] - a[1])))
        # izbor vozaca: odbaci mala lica (zadnje sediste), pa uzmi ono najblize strani vozaca
        amax = max(c[2] for c in cands)
        big = [c for c in cands if c[2] >= 0.5 * amax]
        sgn = 1.0 if self.side == "right" else -1.0
        i, box, _ = max(big, key=lambda c: sgn * (c[1][0] + c[1][2]))
        lms = res.face_landmarks[i]
        M = np.array(res.facial_transformation_matrixes[i])[:3, :3]
        pitch = math.degrees(math.atan2(M[2, 1], M[2, 2]))
        yaw = math.degrees(math.asin(max(-1.0, min(1.0, -M[2, 0]))))
        blend = {b.category_name: b.score for b in res.face_blendshapes[i]}
        return {"yaw": yaw, "pitch": pitch, "blend": blend, "center": _to_full((lms[1].x, lms[1].y), roi),
                "box": box, "fwd": (float(M[0, 2]), float(M[1, 2])),
                "pts": [_to_full((p.x, p.y), roi) for p in lms[::4]],
                "n_faces": len(cands), "others": [c[1] for c in cands if c[0] != i]}



class HandPerception:
    def __init__(self, model_path, num_hands=4):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp = mp
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO, num_hands=num_hands)
        self.lm = vision.HandLandmarker.create_from_options(opts)

    def __call__(self, rgb, ts_ms, roi):
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts_ms)
        out = []
        for lms in res.hand_landmarks:
            cx = sum(p.x for p in lms) / len(lms); cy = sum(p.y for p in lms) / len(lms)
            out.append({"center": _to_full((cx, cy), roi), "pts": [_to_full((p.x, p.y), roi) for p in lms]})
        return out


class ObjectPerception:
    """YOLOv8/11 izvezen u ONNX (yolo export format=onnx imgsz=640); izlaz (1, 84, N)."""

    def __init__(self, onnx_path, size=640, conf=0.2):
        import cv2
        self.cv2, self.size, self.conf = cv2, size, conf
        self.net = cv2.dnn.readNetFromONNX(onnx_path)
        self.keep = EAT_DRINK_CLS | {PHONE_CLS}

    def __call__(self, bgr, roi):
        cv2 = self.cv2
        blob = cv2.dnn.blobFromImage(bgr, 1 / 255.0, (self.size, self.size), swapRB=True, crop=False)
        self.net.setInput(blob)
        out = self.net.forward()[0].T                # (N, 4 + 80)
        scores = out[:, 4:]
        cls = scores.argmax(1); conf = scores.max(1)
        m = (conf >= self.conf) & np.isin(cls, list(self.keep))
        if not m.any():
            return []
        b, cls, conf = out[m, :4], cls[m], conf[m]
        boxes = [[float(x - w / 2), float(y - h / 2), float(w), float(h)] for x, y, w, h in b]
        idx = cv2.dnn.NMSBoxes(boxes, conf.tolist(), self.conf, 0.45)
        res = []
        for i in np.array(idx).flatten():
            x, y, w, h = (float(v) / self.size for v in b[i])
            p0, p1 = _to_full((x - w / 2, y - h / 2), roi), _to_full((x + w / 2, y + h / 2), roi)
            res.append({"cls": int(cls[i]), "conf": float(conf[i]), "center": _to_full((x, y), roi),
                        "box": (p0[0], p0[1], p1[0], p1[1])})
        return res


class ClipVerifier:
    """Opciono: zero-shot provera CLIP-om (retko, npr. 0.5 Hz). Na uredjaju zameniti manjim modelom (MobileCLIP)."""
    PROMPTS = {
        "phone_use": "a photo of a driver using a mobile phone",
        "eating_drinking": "a photo of a driver eating or drinking",
        "_neutral": "a photo of a driver with both hands on the steering wheel looking at the road",
    }

    def __init__(self, model="ViT-B-32", pretrained="laion2b_s34b_b79k"):
        import open_clip
        import torch
        self.torch = torch
        self.model, _, self.prep = open_clip.create_model_and_transforms(model, pretrained=pretrained)
        self.model.eval()
        tok = open_clip.get_tokenizer(model)
        with torch.no_grad():
            t = self.model.encode_text(tok(list(self.PROMPTS.values())))
            self.txt = t / t.norm(dim=-1, keepdim=True)
        self.keys = list(self.PROMPTS)

    def __call__(self, rgb):
        from PIL import Image
        with self.torch.no_grad():
            im = self.model.encode_image(self.prep(Image.fromarray(rgb)).unsqueeze(0))
            im = im / im.norm(dim=-1, keepdim=True)
            probs = (100.0 * im @ self.txt.T).softmax(-1)[0].tolist()
        return {k: p for k, p in zip(self.keys, probs) if not k.startswith("_")}



# ----------------------------------------------------------------------------
# 4. IZLAZ — lokalni log (dev) i slanje backendu (prod)
# ----------------------------------------------------------------------------
WIRE_CATEGORY_KEYS = ("p", "active", "run_s", "r")


def wire_record(rec: dict) -> dict:
    """Zapis frejma u obliku koji backend cita (ModelFrame u backend/app/schemas/camera.py), bez ostatka."""
    return {
        "t": rec["t"], "frame": rec.get("frame"),
        "categories": {n: {k: c[k] for k in WIRE_CATEGORY_KEYS} for n, c in rec["categories"].items()},
        "groups": rec["groups"],
        "risk": {"final": rec["risk"]["final"]},
        "rules_triggered": rec["rules_triggered"],
        "alert": rec["alert"],
    }


class FrameLog:
    """frames.jsonl (JSON Lines, append-only, otporno na nestanak struje) + run.json sa podacima o pokretanju.

    frames.jsonl je ulaz za izvestaj na backendu (python -m app.services.model_report) i za
    safety_client.py --replay. Upisuje se uzorkovano (frame_log_hz), plus svaka promena alarma.
    """

    def __init__(self, cfg, session_id, log_all=False, slim=False):
        lc = cfg["logging"]
        self.dir = Path(lc["out_dir"]) / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.f = open(self.dir / "frames.jsonl", "a", buffering=1 << 16)
        hz = lc.get("frame_log_hz", 5.0)
        self.period = 0.0 if log_all or hz <= 0 else 1.0 / hz
        self.flush_every = lc.get("flush_every_s", 1.0)
        self.slim = slim
        self.t_log, self.t_flush, self.prev_level = -1e9, 0.0, 0
        self.session_id = session_id

    def write(self, rec):
        t = rec["t"]
        if rec["alert"]["code"] != self.prev_level or t - self.t_log >= self.period:
            self.f.write(json.dumps(wire_record(rec) if self.slim else rec, separators=(",", ":")) + "\n")
            self.t_log = t
        self.prev_level = rec["alert"]["code"]
        if t - self.t_flush >= self.flush_every:
            self.f.flush(); self.t_flush = t

    def close(self, meta):
        self.f.close()
        with open(self.dir / "run.json", "w") as f:
            json.dump({"session_id": self.session_id, **meta}, f, indent=2)


class BackendSink:
    """Salje zapise frejmova (POST /telemetry) i JPEG video (POST /video/frames) backendu.

    Mreza radi u pozadinskim nitima sa malim redovima: spor ili ugasen backend nikad ne usporava
    kameru, a kad red ne stigne da se isprazni, bacaju se najstariji. Zapis ide ~send_hz puta u
    sekundi i odmah na svaku promenu alarma. Vreme ticka je trenutak snimanja, ne slanja.
    """

    def __init__(self, url, send_hz=2.0, video_fps=8.0, send_video=True):
        import queue
        import threading
        from datetime import datetime
        from safety_client import SafetyClient   # isti folder; samo standardna biblioteka (+ cv2 za JPEG)
        self.queue, self.datetime = queue, datetime
        self.client = SafetyClient(url, min_interval_s=0, video_fps=0)    # tempo odredjuje ova klasa
        self.period = 1.0 / send_hz if send_hz > 0 else 0.0
        self.video_period = 1.0 / video_fps if video_fps > 0 else 0.0
        self.send_video = send_video
        self.t_sent, self.t_video, self.prev_level = -1e9, -1e9, None
        self.stats = {"sent": 0, "no_trip_or_down": 0, "errors": 0, "dropped": 0, "video": 0}
        self.last_state = None
        self._ticks = queue.Queue(maxsize=20)
        self._video = queue.Queue(maxsize=3)
        self._stop = threading.Event()
        self._threads = [threading.Thread(target=self._loop, args=(self._ticks, self._post_tick), daemon=True),
                         threading.Thread(target=self._loop, args=(self._video, self._post_video), daemon=True)]
        for th in self._threads:
            th.start()

    # -- iz petlje kamere (nikad ne blokira)
    def frame(self, rec):
        now = time.monotonic()
        level = rec["alert"]["code"]
        if level == self.prev_level and now - self.t_sent < self.period:
            return
        self.t_sent, self.prev_level = now, level
        self._put(self._ticks, (wire_record(rec), self.datetime.now().astimezone()))

    def video(self, image):
        if not self.send_video:
            return
        now = time.monotonic()
        if now - self.t_video < self.video_period:
            return
        self.t_video = now
        self._put(self._video, image)

    def _put(self, q, item):
        while True:
            try:
                q.put_nowait(item)
                return
            except self.queue.Full:
                try:
                    q.get_nowait(); self.stats["dropped"] += 1
                except self.queue.Empty:
                    pass

    # -- pozadinske niti
    def _loop(self, q, post):
        while not (self._stop.is_set() and q.empty()):
            try:
                item = q.get(timeout=0.2)
            except self.queue.Empty:
                continue
            try:
                post(item)
            except Exception as e:                 # 422/500 sa backenda: zabelezi i nastavi
                self.stats["errors"] += 1
                if self.stats["errors"] <= 3:
                    print(f"[backend] {type(e).__name__}: {e}", flush=True)

    def _post_tick(self, item):
        frame, ts = item
        state = self.client.send_frame(frame, timestamp=ts)
        if state is None:
            self.stats["no_trip_or_down"] += 1     # 409 (aplikacija jos nije pokrenula voznju) ili nedostupan
        else:
            self.stats["sent"] += 1
            self.last_state = state

    def _post_video(self, image):
        if self.client.send_video_frame(image):
            self.stats["video"] += 1

    def status(self):
        s, st = self.stats, self.last_state
        car = f"score {st['score']:.0f} {st['level']}" if st else "no trip state yet"
        return (f"backend: {s['sent']} sent, {s['no_trip_or_down']} no trip/unreachable, {s['errors']} errors, "
                f"{s['dropped']} dropped, {s['video']} video | {car}")

    def close(self, timeout=5.0):
        self._stop.set()
        for th in self._threads:
            th.join(timeout=timeout)


# ----------------------------------------------------------------------------
# 5. PIPELINE — jedan frejm -> zapis (percepcija, dokaz, rizik). Isto za dev i prod.
# ----------------------------------------------------------------------------
class Pipeline:
    def __init__(self, cfg):
        vc, mc, sc = cfg["video"], cfg["models"], cfg["schedule"]
        self.cfg, self.vc, self.sc = cfg, vc, sc
        self.face = FacePerception(mc["face_landmarker"], mc.get("face_num", 2), mc.get("face_min_conf", 0.4),
                                   vc.get("driver_side", "right"))
        self.hands = HandPerception(mc["hand_landmarker"], mc.get("hands_num", 4))
        self.objs = ObjectPerception(mc["yolo_onnx"], mc["yolo_input"], mc["yolo_conf"])
        self.clip = ClipVerifier(mc.get("clip_model", "ViT-B-32"), mc.get("clip_pretrained", "laion2b_s34b_b79k")) \
            if sc.get("clip_every_s", 0) > 0 else None
        self.fx, self.engine = FeatureExtractor(cfg), RiskEngine(cfg)
        self.k, self.last_ts = -1, -1
        self.held = {"face": (None, -1e9), "hands": (None, -1e9), "objects": (None, -1e9), "clip": (None, -1e9)}

    def process(self, src, t, frame_idx, speed_kmh=None):
        """Vraca (zapis frejma, umanjen frejm, (lice, sake, objekti)) za frejm `src` u trenutku t (s)."""
        import cv2
        vc, sc, held = self.vc, self.sc, self.held
        roi, head_roi = vc["driver_roi"], vc["head_roi"]
        self.k += 1
        k = self.k
        h, w = src.shape[:2]
        frame = cv2.resize(src, (vc["input_width"], int(h * vc["input_width"] / w)))
        ts_ms = max(int(t * 1000), self.last_ts + 1)          # MediaPipe VIDEO trazi strogo rastuce vreme
        self.last_ts = ts_ms

        def rgb(img):
            return np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        if k % sc["face_every_n"] == 0:
            held["face"] = (self.face(rgb(_crop(frame, head_roi)), ts_ms, head_roi), t)
        if k % sc["hands_every_n"] == 0:
            held["hands"] = (self.hands(rgb(_crop(frame, roi)), ts_ms, roi), t)
        if k % sc["objects_every_n"] == 0:
            # YOLO na isecku iz originalne rezolucije: telefon je mali, a downscale ga brise
            yolo_src = src if vc.get("yolo_full_res", True) else frame
            held["objects"] = (self.objs(_crop(yolo_src, roi), roi), t)

        def get(key):
            return held[key][0] if t - held[key][1] <= sc["max_result_age_s"] else None

        results = get("face"), get("hands"), get("objects")
        evidence, perception = self.fx.update(t, *results)
        if self.clip is not None:
            if t - held["clip"][1] >= sc["clip_every_s"]:
                held["clip"] = (self.clip(rgb(_crop(frame, roi))), t)
            if held["clip"][0] and t - held["clip"][1] <= 2 * sc["clip_every_s"]:
                for cat, pc in held["clip"][0].items():          # fuzija: CLIP moze samo da podigne dokaz
                    evidence[cat] = max(evidence.get(cat, 0.0), 0.8 * pc)
                perception["clip"] = {kk: r3(v) for kk, v in held["clip"][0].items()}
        rec = self.engine.step(t, evidence, speed_kmh=speed_kmh)   # speed: iz CAN-a ako postoji
        rec = {"t": rec["t"], "frame": frame_idx, **rec, "perception": perception}
        return rec, frame, results


class FrameSource:
    """Izvor frejmova: (indeks, t u sekundama, BGR slika) za svaki `every`-ti frejm.

    Preskoceni frejmovi se samo grab()-uju (bez dekodiranja). Kamera (indeks) daje t po satu.
    Fajl daje t po polozaju u snimku; sa realtime=True ide brzinom snimanja kao prava kamera:
    ceka kad je obrada brza, a preskace frejmove kad kasni (tako vreme tickova i video za klipove
    na backendu odgovaraju snimku).
    """

    def __init__(self, video, every, start_s=0.0, max_seconds=None, realtime=False):
        import cv2
        self.live = str(video).isdigit()
        self.cap = cv2.VideoCapture(int(video) if self.live else video)
        if not self.cap.isOpened():
            raise SystemExit(f"cannot open video source {video!r}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        if start_s and not self.live:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
        self.frame0 = 0 if self.live else int(round(start_s * self.fps))
        self.every, self.max_seconds, self.realtime = every, max_seconds, realtime and not self.live

    def __iter__(self):
        cap, fps, frame0, every = self.cap, self.fps, self.frame0, self.every
        idx, nxt, wall0 = frame0 - 1, frame0, time.monotonic()
        try:
            while True:
                if self.realtime:
                    ahead = (nxt - frame0) / fps - (time.monotonic() - wall0)
                    if ahead > 0:
                        time.sleep(ahead)
                    else:                                  # kasnimo: skoci na frejm koji je "sada"
                        now_idx = frame0 + int((time.monotonic() - wall0) * fps)
                        nxt = max(nxt, frame0 + (now_idx - frame0) // every * every)
                while idx + 1 < nxt:
                    if not cap.grab():
                        return
                    idx += 1
                ok, src = cap.read()
                if not ok:
                    return
                idx += 1
                t = (time.monotonic() - wall0) if self.live else (idx - frame0) / fps
                if self.max_seconds and t > self.max_seconds:
                    return
                yield idx, t, src
                nxt = idx + every
        finally:
            cap.release()


def _session_name(cfg, video):
    # jedinstven folder po pokretanju (dva pokretanja u istoj sekundi su ranije pisala u isti frames.jsonl)
    stem = "cam" + str(video) if str(video).isdigit() else Path(str(video)).stem[:40]
    session = f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}"
    n = 1
    while (Path(cfg["logging"]["out_dir"]) / session).exists():
        n += 1
        session = f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}_{n}"
    return session


def _run_meta(video, every, pipe, compute_ms, cfg):
    return {"source": str(video), "process_every_n_frames": every,
            "avg_compute_ms_per_processed_frame": r3(np.mean(compute_ms) if compute_ms else 0),
            "road_baseline": [r3(v) for v in pipe.fx.baseline.value], "road_baseline_status": pipe.fx.baseline.status,
            "config_version": cfg["version"]}


def print_model_report(frames_jsonl):
    """Izvestaj cele voznje racuna backend (app/services/model_report.py). Ovde se uvozi isti kod, bez servera."""
    backend = Path(__file__).resolve().parent.parent / "backend"
    try:
        import sys
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        from app.services.model_report import format_report, report_from_records
    except ImportError:
        print(f"trip report: cd backend && python -m app.services.model_report {frames_jsonl}")
        return
    with open(frames_jsonl, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    print("\n--- trip report (backend/app/services/model_report.py) ---")
    print(format_report(report_from_records(records)))


def _start_trip(sink, driver):
    if sink is None or not driver:
        return None
    try:
        trip = sink.client.start_trip(driver)
        print(f"started trip {trip['trip_id']} for {driver}")
        return trip["trip_id"]
    except OSError as e:
        print(f"could not start a trip ({e}); frames are sent to whatever trip the app starts")
        return None


def _end_trip(sink, trip_id):
    if sink is None or trip_id is None:
        return
    try:
        s = sink.client.end_trip(trip_id)
        print(f"trip ended: final score {s['final_score']}, report: GET /trips/{trip_id}/report")
    except OSError as e:
        print(f"could not end trip {trip_id}: {e}")


# ----------------------------------------------------------------------------
# 6. MODOVI
#    dev   prozor sa videom i metrikama, frames.jsonl sa svim promenljivim, izvestaj na kraju
#    prod  bez prozora i bez prikaza: zapisi i video idu backendu, sve ostalo radi backend
# ----------------------------------------------------------------------------
def run_dev(video, cfg_path, every=None, show=True, max_seconds=None, save_video=None, verbose=False,
            log_all=False, start_s=0.0, backend_url=None, start_trip=None, realtime=False):
    import cv2
    from dev_overlay import Overlay, verbose_line
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    every = every or cfg["video"]["process_every_n_frames"]
    pipe = Pipeline(cfg)
    log = FrameLog(cfg, _session_name(cfg, video), log_all)
    bc = cfg.get("backend", {})
    sink = BackendSink(backend_url, bc.get("send_hz", 2.0), bc.get("video_fps", 8.0), bc.get("send_video", True)) \
        if backend_url else None
    trip_id = _start_trip(sink, start_trip)
    overlay = Overlay(cfg) if (show or save_video) else None
    source = FrameSource(video, every, start_s, max_seconds, realtime)
    writer, compute_ms, paused = None, [], False
    if show:
        cv2.namedWindow("driver risk (dev)", cv2.WINDOW_NORMAL)
    try:
        for frame_idx, t, src in source:
            tic = time.perf_counter()
            rec, frame, (f_res, h_res, o_res) = pipe.process(src, t, frame_idx)
            compute_ms.append((time.perf_counter() - tic) * 1000)
            log.write(rec)
            if sink is not None:
                sink.frame(rec); sink.video(frame)
            if verbose:
                print(verbose_line(rec, rec["perception"]), flush=True)
            if overlay is None:
                continue
            recent = compute_ms[-20:]
            info = {"ms": float(np.mean(recent)), "fps": 1000.0 / max(1e-3, float(np.mean(recent)))}
            vis = overlay.render(frame, rec, rec["perception"], f_res, h_res, o_res, info)
            if save_video:
                if writer is None:
                    writer = cv2.VideoWriter(save_video, cv2.VideoWriter_fourcc(*"mp4v"), source.fps / every,
                                             (vis.shape[1], vis.shape[0]))
                writer.write(vis)
            if show:
                cv2.imshow("driver risk (dev)", vis)
                key = cv2.waitKey(0 if paused else 1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord(" "):
                    paused = not paused
                if key == ord("r"):
                    overlay.show_roi = not overlay.show_roi
                if key == ord("s"):
                    p = log.dir / f"frame_{frame_idx}.png"
                    cv2.imwrite(str(p), vis); print(f"saved {p}")
    finally:
        if writer is not None:
            writer.release()
        if show:
            cv2.destroyAllWindows()
        log.close(_run_meta(video, every, pipe, compute_ms, cfg))
        if sink is not None:
            sink.close()
            print(sink.status())
            _end_trip(sink, trip_id)
    print_model_report(log.dir / "frames.jsonl")
    print(f"logs: {log.dir}")


def run_prod(video, cfg_path, backend_url, every=None, max_seconds=None, start_s=0.0, realtime=True,
             send_video=None, log=False, start_trip=None, status_every_s=10.0):
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    every = every or cfg["video"]["process_every_n_frames"]
    bc = cfg.get("backend", {})
    sink = BackendSink(backend_url, bc.get("send_hz", 2.0), bc.get("video_fps", 8.0),
                       bc.get("send_video", True) if send_video is None else send_video)
    pipe = Pipeline(cfg)
    flog = FrameLog(cfg, _session_name(cfg, video), slim=True) if log else None
    trip_id = _start_trip(sink, start_trip)
    print(f"production mode: {video} -> {backend_url} (every {every}. frame, {bc.get('send_hz', 2.0)} Hz, "
          f"video {'on' if sink.send_video else 'off'}). Ctrl+C to stop.", flush=True)
    compute_ms, t_status, n = [], time.monotonic(), 0
    try:
        for frame_idx, t, src in FrameSource(video, every, start_s, max_seconds, realtime):
            tic = time.perf_counter()
            rec, frame, _ = pipe.process(src, t, frame_idx)
            compute_ms.append((time.perf_counter() - tic) * 1000)
            n += 1
            sink.frame(rec)
            sink.video(frame)
            if flog is not None:
                flog.write(rec)
            if time.monotonic() - t_status >= status_every_s:
                t_status = time.monotonic()
                ms = float(np.mean(compute_ms[-50:]))
                print(f"t={t:7.1f}s {rec['alert']['level']:6s} risk {rec['risk']['final']:.2f} | {ms:4.0f} ms/frame | "
                      f"{sink.status()}", flush=True)
    except KeyboardInterrupt:
        print("stopping")
    finally:
        sink.close()
        if flog is not None:
            flog.close(_run_meta(video, every, pipe, compute_ms, cfg))
        print(f"{n} frames processed. {sink.status()}")
        _end_trip(sink, trip_id)


# ----------------------------------------------------------------------------
# PODESAVANJE: ROI i kalibracija pogleda (upisuje se u risk_config.json)
# ----------------------------------------------------------------------------
def _set_cfg_value(cfg_path, key, value):
    """Menja jednu vrednost u JSON-u bez preformatiranja ostatka fajla."""
    import re
    with open(cfg_path, encoding="utf-8", newline="") as f:      # newline="" cuva CRLF/LF kakav jeste
        txt = f.read()
    val = json.dumps(value)
    pat = rf'("{key}"\s*:\s*)(\[[^\]]*\]|-?[0-9.]+|"[^"]*")'
    if not re.search(pat, txt):
        raise KeyError(f"{key} not found in {cfg_path}")
    with open(cfg_path, "w", encoding="utf-8", newline="") as f:
        f.write(re.sub(pat, lambda m: m.group(1) + val, txt, count=1))


def _read_frame(video, at_s):
    import cv2
    cap = cv2.VideoCapture(int(video) if str(video).isdigit() else video)
    if not str(video).isdigit():
        cap.set(cv2.CAP_PROP_POS_MSEC, at_s * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"cannot read a frame from {video}")
    return frame


def pick_roi(video, cfg_path, at_s=5.0):
    """Mišem oznaci ROI-jeve na jednom frejmu i upisi ih u konfiguraciju."""
    import cv2
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    frame = _read_frame(video, at_s)
    h, w = frame.shape[:2]
    s = min(1.0, 900 / h)
    img = cv2.resize(frame, (int(w * s), int(h * s)))
    H, W = img.shape[:2]
    help_ = {"driver_roi": "whole driver: head, torso, both hands, lap (hands + phone are searched here)",
             "head_roi": "tight box where the driver's head moves (face is searched here)",
             "steering_wheel_roi": "steering wheel rim (hand centre inside = hand on wheel)"}
    for key, why in help_.items():
        view = img.copy()
        r = cfg["video"][key]
        cv2.rectangle(view, (int(r[0] * W), int(r[1] * H)), (int(r[2] * W), int(r[3] * H)), (0, 255, 255), 1)
        for i, line in enumerate([f"{key}: {why}", "drag a box, ENTER/SPACE = save, C = keep current (yellow)"]):
            cv2.putText(view, line, (10, 25 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA)
        x, y, bw, bh = cv2.selectROI("pick ROI", view, showCrosshair=False)
        if bw > 5 and bh > 5:
            val = [round(x / W, 3), round(y / H, 3), round((x + bw) / W, 3), round((y + bh) / H, 3)]
            _set_cfg_value(cfg_path, key, val)
            cfg["video"][key] = val
            print(f"{key} = {val}")
        else:
            print(f"{key} unchanged = {r}")
    cv2.destroyAllWindows()


def calibrate(video, cfg_path, every=3, write=True):
    """Meri pozu glave "gleda u put" na snimku normalne voznje i upisuje je kao prior u konfiguraciju."""
    import cv2
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    vc, mc, c = cfg["video"], cfg["models"], cfg["calibration"]
    face = FacePerception(mc["face_landmarker"], mc.get("face_num", 2), mc.get("face_min_conf", 0.4),
                          vc.get("driver_side", "right"))
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    samples, n, i = [], 0, -1
    while True:
        i += 1
        if i % every:
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (vc["input_width"], int(h * vc["input_width"] / w)))
        crop = _crop(frame, vc["head_roi"])
        f = face(np.ascontiguousarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), int(i / fps * 1000), vc["head_roi"])
        if f is None:
            continue
        bl = f["blend"]
        closure = 0.5 * (bl.get("eyeBlinkLeft", 0) + bl.get("eyeBlinkRight", 0))
        gd = 0.5 * (bl.get("eyeLookDownLeft", 0) + bl.get("eyeLookDownRight", 0))
        if calib_usable(c, closure, gd):
            samples.append((f["yaw"], f["pitch"]))
    if len(samples) < 10:
        raise SystemExit(f"face found in only {len(samples)}/{n} frames; check head_roi (--pick-roi)")
    y, p, share = robust_mode(samples)
    print(f"face usable in {len(samples)}/{n} frames; road pose yaw={y:.1f} pitch={p:.1f} "
          f"({100 * share:.0f}% of samples in that cluster)")
    if share < 0.4:
        print("WARNING: no dominant pose; use a clip where the driver mostly looks at the road")
    if write:
        _set_cfg_value(cfg_path, "prior_yaw_deg", round(y, 1))
        _set_cfg_value(cfg_path, "prior_pitch_deg", round(p, 1))
        print(f"written to {cfg_path}: calibration.prior_yaw_deg / prior_pitch_deg")


# ----------------------------------------------------------------------------
# KOMANDNA LINIJA
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Driver risk from a cabin camera. dev: window with video + key metrics "
                    "(SPACE pause, R ROIs, S screenshot, Q/ESC quit). prod: headless, streams to the backend.")
    ap.add_argument("--video", required=True, help="putanja do snimka ili indeks kamere (npr. 0)")
    ap.add_argument("--config", default="risk_config.json")
    ap.add_argument("--mode", choices=["dev", "prod"], default="dev",
                    help="dev = prikaz + lokalni log (podrazumevano); prod = bez prikaza, zapisi idu backendu")
    ap.add_argument("--every", type=int, default=None, help="obradi svaki N-ti frejm")
    ap.add_argument("--start", type=float, default=0.0, help="pocni od ove sekunde snimka")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--backend", nargs="?", const="", default=None, metavar="URL",
                    help="adresa backenda (podrazumevano backend.url iz configa). U dev modu ukljucuje slanje.")
    ap.add_argument("--start-trip", metavar="DRIVER_ID", default=None,
                    help="sam pokrene voznju na backendu (bez telefona) i zavrsi je na kraju")
    # dev
    ap.add_argument("--show", action="store_true", help="(dev) prozor sa videom; ukljucen je i bez ovoga")
    ap.add_argument("--no-show", action="store_true", help="(dev) bez prozora, npr. samo --save-video")
    ap.add_argument("--save-video", default=None, help="(dev) snimi prikaz (video + panel) u .mp4")
    ap.add_argument("--verbose", action="store_true", help="(dev) jedan red po obradjenom frejmu u terminalu")
    ap.add_argument("--log-all", action="store_true", help="(dev) frames.jsonl za svaki obradjeni frejm (ne 5 Hz)")
    ap.add_argument("--realtime", action="store_true", help="(dev) snimak ide brzinom snimanja (u prod je ukljuceno)")
    # prod
    ap.add_argument("--no-realtime", action="store_true", help="(prod) snimak obradi najbrze sto moze")
    ap.add_argument("--no-video", action="store_true", help="(prod) ne salji JPEG frejmove (bez klipova u izvestaju)")
    ap.add_argument("--log", action="store_true", help="(prod) i lokalno logs/<sesija>/frames.jsonl (ono sto ide backendu)")
    # podesavanje
    ap.add_argument("--pick-roi", action="store_true", help="misem oznaci driver/head/wheel ROI i upisi u config")
    ap.add_argument("--calibrate", action="store_true",
                    help="izmeri pozu glave 'gleda u put' na snimku normalne voznje i upisi u config")
    ap.add_argument("--at", type=float, default=5.0, help="sekunda snimka za --pick-roi")
    a = ap.parse_args()

    if a.pick_roi:
        pick_roi(a.video, a.config, a.at)
    elif a.calibrate:
        calibrate(a.video, a.config, a.every or 3)
    else:
        url = a.backend or json.loads(Path(a.config).read_text(encoding="utf-8")).get("backend", {}).get(
            "url", "http://127.0.0.1:8000/api/v1")
        if a.mode == "prod":
            run_prod(a.video, a.config, url, a.every, a.max_seconds, a.start, realtime=not a.no_realtime,
                     send_video=False if a.no_video else None, log=a.log, start_trip=a.start_trip)
        else:
            run_dev(a.video, a.config, a.every, not a.no_show, a.max_seconds, a.save_video, a.verbose, a.log_all,
                    a.start, backend_url=url if a.backend is not None or a.start_trip else None,
                    start_trip=a.start_trip, realtime=a.realtime)
