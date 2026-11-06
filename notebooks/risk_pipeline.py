"""
risk_pipeline.py — procena rizika vozaca uzivo iz cabin kamere (samo vozac).

Slojevi (svaki je zamenljiv):
  1. Percepcija      MediaPipe Face/Hand Landmarker + YOLO (ONNX preko cv2.dnn) [+ opciono CLIP]
  2. FeatureExtractor sirovi izlazi -> dokaz p_i(n) in [0,1] za svaku kategoriju rizika
  3. RiskEngine      matematicki model (MATEMATICKI_MODEL.md): trajanje, grupe, agregacija, alarm
  4. TripLogger      frames.jsonl (uzorkovano), events.jsonl, summary.json

Pokretanje:
  python risk_pipeline.py --video snimak.mp4 --config risk_config.json --every 3 --show
  python risk_pipeline.py --video 0          # zivi stream sa kamere

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
# 3. RISK ENGINE — cista matematika, bez zavisnosti od modela (lako za test)
# ----------------------------------------------------------------------------
class _Cat:
    __slots__ = ("name", "cfg", "p_hat", "active", "D", "run", "ev_start", "ev_end", "ev_peak_r", "ev_peak_p")

    def __init__(self, name, cfg):
        self.name, self.cfg = name, cfg
        self.p_hat, self.active, self.D, self.run = 0.0, False, 0.0, 0.0
        self.ev_start, self.ev_end, self.ev_peak_r, self.ev_peak_p = None, None, 0.0, 0.0

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
        a = cfg["alerts"]
        self.a = a
        self.level, self.level_since = 0, 0.0
        self.rise_t, self.fall_t = 0.0, 0.0
        self.alert_ev = None
        # rezime vozne
        self.p = cfg["logging"].get("summary_power_p", 2.0)
        self.ev_min = cfg["logging"].get("event_min_s", 0.5)
        self.ev_gap = cfg["logging"].get("event_merge_gap_s", 0.5)
        self.T_total = self.S1 = self.Sp = self.R_max = 0.0
        self.hist = np.zeros(200)                     # vremenski tezinski histogram R
        self.t_level = [0.0, 0.0, 0.0]
        self.cat_stats = {n: {"active_s": 0.0, "events": 0, "max_event_s": 0.0} for n in self.cats}
        self.alert_counts = {"yellow": 0, "red": 0}
        self.rule_counts = {r["name"]: 0 for r in cfg["rules"]}
        self._rules_prev: set = set()

    # ---------------------------------------------------------------- korak
    def step(self, t: float, evidence: dict, speed_kmh: float | None = None) -> tuple[dict, list]:
        """Jedan korak modela u trenutku t. Vraca (zapis_za_frejm, lista_dogadjaja)."""
        dt = 0.0 if self.t_prev is None else max(0.0, t - self.t_prev)
        self.t_prev = t
        events = []

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
            events += self._category_event(c, was, t, r[n])
            if c.active:
                self.cat_stats[n]["active_s"] += dt

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
        events += self._alert(t, dt, R, fired, r)

        # (10) statistika za kraj voznje
        self._accumulate(dt, R)
        for name in fired - self._rules_prev:
            self.rule_counts[name] += 1
        self._rules_prev = fired

        top = [n for n, v in sorted(r.items(), key=lambda kv: -kv[1]) if v > 0.05][:3]
        rec = {
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
        return rec, events

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
    def _alert(self, t, dt, R, fired, r):
        rule_fired = bool(fired)
        a, ev = self.a, []
        up = 2 if R >= a["red"]["on"] else 1 if R >= a["yellow"]["on"] else 0
        new = self.level
        if up > self.level:
            self.rise_t += dt
            if self.rise_t >= a["rise_hold_s"] or rule_fired:
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
            if new > self.level:
                self.alert_counts[LEVELS[new]] += 1
            if self.level == 0 and new > 0:
                self.alert_ev = {"type": "alert", "start_t": r3(t), "max_level": new, "peak_risk": R,
                                 "causes": set()}
            if new == 0 and self.alert_ev:
                e = self.alert_ev
                ev.append({**e, "end_t": r3(t), "duration_s": r3(t - e["start_t"]),
                           "max_level": LEVELS[e["max_level"]], "peak_risk": r3(e["peak_risk"]),
                           "causes": sorted(e["causes"])})
                self.alert_ev = None
            ev.append({"type": "alert_change", "t": r3(t), "from": LEVELS[self.level], "to": LEVELS[new],
                       "risk": r3(R)})
            self.level, self.level_since = new, t
            self.rise_t = self.fall_t = 0.0
        if self.alert_ev:
            e = self.alert_ev
            e["max_level"] = max(e["max_level"], self.level)
            e["peak_risk"] = max(e["peak_risk"], R)
            e["causes"].update(n for n, v in r.items() if v > 0.15)
            e["causes"].update(f"rule:{name}" for name in fired)
        return ev

    # ---------------------------------------------------------------- dogadjaji
    def _category_event(self, c, was, t, r_i):
        """Dogadjaj ponasanja: spaja prekide krace od event_merge_gap_s, odbacuje krace od event_min_s."""
        out = []
        if c.active:
            if not was:
                gap = c.cfg.get("event_merge_gap_s", self.ev_gap)
                if c.ev_start is not None and c.ev_end is not None and t - c.ev_end <= gap:
                    c.ev_end = None                       # nastavak istog dogadjaja
                else:
                    if c.ev_start is not None:
                        out += self._close_event(c)
                    c.ev_start, c.ev_end, c.ev_peak_r, c.ev_peak_p = t, None, r_i, c.p_hat
            c.ev_peak_r, c.ev_peak_p = max(c.ev_peak_r, r_i), max(c.ev_peak_p, c.p_hat)
        else:
            if was:
                c.ev_end = t
            if c.ev_start is not None and c.ev_end is not None and t - c.ev_end > c.cfg.get("event_merge_gap_s", self.ev_gap):
                out += self._close_event(c)
        return out

    def _close_event(self, c):
        end = c.ev_end if c.ev_end is not None else self.t_prev
        d = end - c.ev_start
        out = []
        if d >= self.ev_min:
            st = self.cat_stats[c.name]
            st["events"] += 1
            st["max_event_s"] = max(st["max_event_s"], d)
            out.append({"type": "behavior", "category": c.name, "start_t": r3(c.ev_start), "end_t": r3(end),
                        "duration_s": r3(d), "peak_r": r3(c.ev_peak_r), "peak_p": r3(c.ev_peak_p)})
        c.ev_start = c.ev_end = None
        return out

    def finish(self) -> list:
        """Zatvara otvorene dogadjaje na kraju voznje."""
        out = []
        for c in self.cats.values():
            if c.ev_start is not None:
                out += self._close_event(c)
        if self.alert_ev:
            e, t = self.alert_ev, self.t_prev
            out.append({**e, "end_t": r3(t), "duration_s": r3(t - e["start_t"]),
                        "max_level": LEVELS[e["max_level"]], "peak_risk": r3(e["peak_risk"]),
                        "causes": sorted(e["causes"]), "open_at_end": True})
            self.alert_ev = None
        return out

    # ---------------------------------------------------------------- rezime
    def _accumulate(self, dt, R):
        if dt <= 0:
            return
        self.T_total += dt
        self.S1 += R * dt
        self.Sp += (R ** self.p) * dt
        self.R_max = max(self.R_max, R)
        self.hist[min(len(self.hist) - 1, int(R * len(self.hist)))] += dt
        self.t_level[self.level] += dt

    def _percentile(self, q):
        if self.T_total <= 0:
            return 0.0
        cum = np.cumsum(self.hist) / self.T_total
        return (int(np.searchsorted(cum, q)) + 0.5) / len(self.hist)

    def summary(self) -> dict:
        T = max(self.T_total, 1e-9)
        mean = self.S1 / T
        pmean = (self.Sp / T) ** (1.0 / self.p)
        hours = T / 3600.0
        return {
            "duration_s": r3(self.T_total),
            "risk_mean": r3(mean),
            f"risk_power_mean_p{self.p:g}": r3(pmean),
            "risk_p95": r3(self._percentile(0.95)),
            "risk_max": r3(self.R_max),
            "time_in_level_s": {LEVELS[i]: r3(v) for i, v in enumerate(self.t_level)},
            "time_in_level_frac": {LEVELS[i]: r3(v / T) for i, v in enumerate(self.t_level)},
            "alerts": dict(self.alert_counts),
            "alerts_per_hour": {k: r3(v / hours) for k, v in self.alert_counts.items()},
            "rules": dict(self.rule_counts),
            "categories": {n: {"active_s": r3(s["active_s"]), "events": s["events"],
                               "max_event_s": r3(s["max_event_s"])} for n, s in self.cat_stats.items()},
            "safety_score_0_100": r3(100.0 * (1.0 - pmean)),
        }


# ----------------------------------------------------------------------------
# 2. FEATURE EXTRACTOR — percepcija -> dokaz p_i(n) za svaku kategoriju
# ----------------------------------------------------------------------------
EAT_DRINK_CLS = {39, 40, 41, 46, 47, 48, 52, 53, 54}   # COCO: bottle, wine glass, cup, banana, ...
PHONE_CLS = 67                                         # COCO: cell phone


def _prox(a, b, sigma=0.12):
    """Gausova blizina dve tacke u normalizovanim koordinatama."""
    if a is None or b is None:
        return 0.0
    d2 = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    return math.exp(-d2 / (sigma ** 2))


class FeatureExtractor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cal = cfg["calibration"]
        self.dr = cfg["drowsiness"]
        self.wheel = cfg["video"]["steering_wheel_roi"]
        self.cal_samples: list = []
        self.base = (0.0, 0.0)            # (yaw0, pitch0) — "gleda u put"
        self.perclos_buf: deque = deque()
        self.jaw_run, self.yawn_counted = 0.0, False
        self.yawns: deque = deque()
        self.t_prev = None

    def update(self, t, face, hands, objects):
        """
        face:    None ili dict(yaw, pitch, blend: dict, center: (x,y))   [x,y normalizovani na ceo frejm]
        hands:   None (nije pokrenuto/zastarelo) ili lista centara sake [(x,y), ...]
        objects: None ili lista (cls_id, conf, (cx,cy))
        Vraca (evidence: dict kategorija->p, perception: dict za log).
        """
        dt = 0.0 if self.t_prev is None else max(0.0, t - self.t_prev)
        self.t_prev = t
        c = self.cal
        ev, per = {}, {"face_found": face is not None}

        # ---- glava, pogled, oci
        if face is not None:
            yaw, pitch, bl = face["yaw"], face["pitch"], face["blend"]
            if t <= c["duration_s"]:
                self.cal_samples.append((yaw, pitch))
                if len(self.cal_samples) >= 10:
                    arr = np.array(self.cal_samples)
                    self.base = (float(np.median(arr[:, 0])), float(np.median(arr[:, 1])))
            dyaw, dpitch = abs(yaw - self.base[0]), abs(pitch - self.base[1])
            s = c["angle_softness_deg"]
            p_head = max(sigmoid((dyaw - c["yaw_thr_deg"]) / s), sigmoid((dpitch - c["pitch_thr_deg"]) / s))
            closure = 0.5 * (bl.get("eyeBlinkLeft", 0) + bl.get("eyeBlinkRight", 0))
            gaze_down = 0.5 * (bl.get("eyeLookDownLeft", 0) + bl.get("eyeLookDownRight", 0))
            p_gaze = sigmoid((gaze_down - c["gaze_down_thr"]) / 0.05) * (1.0 - closure)
            ev["eyes_off_road"] = max(p_head, p_gaze)
            # dekorelacija: pogled nadole lazno lici na zatvorene oci
            ev["eyes_closed"] = sigmoid((closure - c["eye_closed_thr"]) / 0.05) * (1.0 - 0.7 * p_head)
            jaw = bl.get("jawOpen", 0.0)
            per.update(yaw=r3(yaw - self.base[0]), pitch=r3(pitch - self.base[1]),
                       eye_closure=r3(closure), gaze_down=r3(gaze_down), jaw_open=r3(jaw))
        else:
            ev["eyes_off_road"] = c["face_missing_p"]
            ev["eyes_closed"] = 0.0
            closure, jaw, gaze_down = None, 0.0, 0.0

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
        per.update(perclos=r3(perclos), yawns_window=len(self.yawns))

        # ---- ruke na volanu
        x0, y0, x1, y1 = self.wheel
        if hands is None or len(hands) == 0:
            ev["hands_off_wheel"] = c["no_hands_detected_p"]
            n_on, n_det = 0, 0
        else:
            n_det = len(hands)
            n_on = sum(1 for (hx, hy) in hands if x0 <= hx <= x1 and y0 <= hy <= y1)
            ev["hands_off_wheel"] = 0.0 if n_on >= 2 else 0.45 if n_on == 1 else 0.85
        per.update(hands_detected=n_det, hands_on_wheel=n_on)

        # ---- telefon, hrana/pice (YOLO) — blizina saci ili licu
        fc = face["center"] if face is not None else None
        p_phone, p_eat = 0.0, 0.0
        for cls, conf, ctr in (objects or []):
            ph = max([_prox(ctr, h) for h in (hands or [])] + [0.0])
            pf = _prox(ctr, fc)
            if cls == PHONE_CLS:
                lap = 0.6 * sigmoid((gaze_down - c["gaze_down_thr"]) / 0.05)   # telefon u krilu + pogled dole
                p_phone = max(p_phone, conf * max(ph, pf, lap))
            elif cls in EAT_DRINK_CLS:
                p_eat = max(p_eat, conf * pf)
        ev["phone_use"], ev["eating_drinking"] = p_phone, p_eat
        per["objects"] = [[int(k), r3(cf)] for k, cf, _ in (objects or [])]
        return ev, per


# ----------------------------------------------------------------------------
# 1. PERCEPCIJA — MediaPipe Tasks + YOLO ONNX (cv2.dnn, bez PyTorch-a na uredjaju)
# ----------------------------------------------------------------------------
class FacePerception:
    def __init__(self, model_path):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp = mp
        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO, num_faces=1,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True)
        self.lm = vision.FaceLandmarker.create_from_options(opts)

    def __call__(self, rgb, ts_ms, roi):
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts_ms)
        if not res.face_landmarks:
            return None
        M = np.array(res.facial_transformation_matrixes[0])[:3, :3]
        pitch = math.degrees(math.atan2(M[2, 1], M[2, 2]))
        yaw = math.degrees(math.asin(max(-1.0, min(1.0, -M[2, 0]))))
        blend = {b.category_name: b.score for b in res.face_blendshapes[0]}
        nose = res.face_landmarks[0][1]
        return {"yaw": yaw, "pitch": pitch, "blend": blend, "center": _to_full((nose.x, nose.y), roi)}


class HandPerception:
    def __init__(self, model_path):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp = mp
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO, num_hands=2)
        self.lm = vision.HandLandmarker.create_from_options(opts)

    def __call__(self, rgb, ts_ms, roi):
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts_ms)
        out = []
        for lms in res.hand_landmarks:
            cx = sum(p.x for p in lms) / len(lms); cy = sum(p.y for p in lms) / len(lms)
            out.append(_to_full((cx, cy), roi))
        return out


class ObjectPerception:
    """YOLOv8/11 izvezen u ONNX (yolo export format=onnx imgsz=320); izlaz (1, 84, N)."""

    def __init__(self, onnx_path, size=320, conf=0.3):
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
            cx, cy = b[i, 0] / self.size, b[i, 1] / self.size
            res.append((int(cls[i]), float(conf[i]), _to_full((float(cx), float(cy)), roi)))
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


def _to_full(pt, roi):
    """Koordinata iz isecka (driver ROI) -> normalizovana koordinata celog frejma."""
    x0, y0, x1, y1 = roi
    return (x0 + pt[0] * (x1 - x0), y0 + pt[1] * (y1 - y0))


# ----------------------------------------------------------------------------
# 4. LOGOVANJE — JSON Lines (append-only, otporno na nestanak struje)
# ----------------------------------------------------------------------------
class TripLogger:
    def __init__(self, cfg, session_id):
        lc = cfg["logging"]
        self.dir = Path(lc["out_dir"]) / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.f_frames = open(self.dir / "frames.jsonl", "a", buffering=1 << 16)
        self.f_events = open(self.dir / "events.jsonl", "a", buffering=1 << 14)
        self.period = 1.0 / lc["frame_log_hz"] if lc["frame_log_hz"] > 0 else 0.0
        self.flush_every = lc["flush_every_s"]
        self.t_log = -1e9; self.t_flush = 0.0; self.prev_level = 0
        self.session_id = session_id

    def write(self, rec, events, force=False):
        t = rec["t"]
        changed = rec["alert"]["code"] != self.prev_level
        if force or changed or events or t - self.t_log >= self.period:
            self.f_frames.write(json.dumps(rec, separators=(",", ":")) + "\n")
            self.t_log = t
        self.prev_level = rec["alert"]["code"]
        for e in events:
            self.f_events.write(json.dumps(e, separators=(",", ":")) + "\n")
        if t - self.t_flush >= self.flush_every:
            self.f_frames.flush(); self.f_events.flush(); self.t_flush = t

    def write_events(self, events):
        for e in events:
            self.f_events.write(json.dumps(e, separators=(",", ":")) + "\n")

    def close(self, summary, meta):
        self.f_frames.close(); self.f_events.close()
        with open(self.dir / "summary.json", "w") as f:
            json.dump({"session_id": self.session_id, **meta, "summary": summary}, f, indent=2)


def set_cabin_light(level: int):
    """Mesto za integraciju: CAN poruka / GPIO za zutu (1) ili crvenu (2) lampicu."""
    pass


# ----------------------------------------------------------------------------
# GLAVNA PETLJA
# ----------------------------------------------------------------------------
def run(video, cfg_path, every=None, show=False, max_seconds=None):
    import cv2
    cfg = json.loads(Path(cfg_path).read_text())
    vc, sc, mc = cfg["video"], cfg["schedule"], cfg["models"]
    every = every or vc["process_every_n_frames"]
    roi = vc["driver_roi"]

    face = FacePerception(mc["face_landmarker"])
    hands = HandPerception(mc["hand_landmarker"])
    objs = ObjectPerception(mc["yolo_onnx"], mc["yolo_input"], mc["yolo_conf"])
    clip = ClipVerifier(mc.get("clip_model", "ViT-B-32"), mc.get("clip_pretrained", "laion2b_s34b_b79k")) \
        if sc.get("clip_every_s", 0) > 0 else None
    fx, engine = FeatureExtractor(cfg), RiskEngine(cfg)
    session = time.strftime("%Y%m%d_%H%M%S")
    log = TripLogger(cfg, session)

    live = str(video).isdigit()
    cap = cv2.VideoCapture(int(video) if live else video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t0 = time.monotonic()
    frame_idx, k = -1, -1
    held = {"hands": (None, -1e9), "objects": (None, -1e9), "clip": (None, -1e9)}   # sample-and-hold
    compute_ms = []

    while True:
        frame_idx += 1
        if frame_idx % every:
            if not cap.grab():            # preskoceni frejm: bez dekodiranja slike
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        k += 1
        t = (time.monotonic() - t0) if live else frame_idx / fps
        if max_seconds and t > max_seconds:
            break
        tic = time.perf_counter()

        h, w = frame.shape[:2]
        s = vc["input_width"] / w
        frame = cv2.resize(frame, (vc["input_width"], int(h * s)))
        H, W = frame.shape[:2]
        crop = frame[int(roi[1] * H):int(roi[3] * H), int(roi[0] * W):int(roi[2] * W)]
        rgb = np.ascontiguousarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        ts_ms = int(t * 1000)

        f_res = face(rgb, ts_ms, roi) if k % sc["face_every_n"] == 0 else None
        if k % sc["hands_every_n"] == 0:
            held["hands"] = (hands(rgb, ts_ms, roi), t)
        if k % sc["objects_every_n"] == 0:
            held["objects"] = (objs(crop, roi), t)
        get = lambda key: held[key][0] if t - held[key][1] <= sc["max_result_age_s"] else None

        evidence, perception = fx.update(t, f_res, get("hands"), get("objects"))
        if clip is not None:
            if t - held["clip"][1] >= sc["clip_every_s"]:
                held["clip"] = (clip(rgb), t)
            if held["clip"][0] and t - held["clip"][1] <= 2 * sc["clip_every_s"]:
                for cat, pc in held["clip"][0].items():          # fuzija: CLIP moze samo da podigne dokaz
                    evidence[cat] = max(evidence.get(cat, 0.0), 0.8 * pc)
                perception["clip"] = {k: r3(v) for k, v in held["clip"][0].items()}
        rec, events = engine.step(t, evidence, speed_kmh=None)   # speed: iz CAN-a ako postoji
        rec = {"t": rec["t"], "frame": frame_idx, **rec, "perception": perception}
        log.write(rec, events)
        set_cabin_light(rec["alert"]["code"])
        compute_ms.append((time.perf_counter() - tic) * 1000)

        if show:
            col = [(0, 200, 0), (0, 220, 255), (0, 0, 255)][rec["alert"]["code"]]
            cv2.circle(frame, (W - 30, 30), 18, col, -1)
            cv2.putText(frame, f"R={rec['risk']['final']:.2f} {','.join(rec['top_contributors'])}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            cv2.imshow("driver risk", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    cap.release()
    log.write_events(engine.finish())
    meta = {"source": str(video), "process_every_n_frames": every, "fps_source": fps,
            "avg_compute_ms_per_processed_frame": r3(np.mean(compute_ms) if compute_ms else 0),
            "config_version": cfg["version"]}
    summ = engine.summary()
    log.close(summ, meta)
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="putanja do snimka ili indeks kamere (npr. 0)")
    ap.add_argument("--config", default="risk_config.json")
    ap.add_argument("--every", type=int, default=None, help="obradi svaki N-ti frejm")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args()
    run(a.video, a.config, a.every, a.show, a.max_seconds)
