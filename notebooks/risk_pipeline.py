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


HAND_LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


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
# 4. LOGOVANJE — JSON Lines (append-only, otporno na nestanak struje)
# ----------------------------------------------------------------------------
class TripLogger:
    def __init__(self, cfg, session_id, log_all=False):
        lc = cfg["logging"]
        self.dir = Path(lc["out_dir"]) / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.f_frames = open(self.dir / "frames.jsonl", "a", buffering=1 << 16)
        self.f_events = open(self.dir / "events.jsonl", "a", buffering=1 << 14)
        self.period = 0.0 if log_all else 1.0 / lc["frame_log_hz"] if lc["frame_log_hz"] > 0 else 0.0
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
# 5. PRIKAZ — sve promenljive modela uz video (dijagnostika)
# ----------------------------------------------------------------------------
CAT_COLORS = {   # BGR
    "phone_use": (255, 0, 255), "eyes_off_road": (0, 165, 255), "hands_off_wheel": (255, 255, 0),
    "eating_drinking": (120, 255, 120), "drowsiness": (255, 140, 60), "eyes_closed": (180, 105, 255),
}
CAT_SHORT = {"phone_use": "phone", "eyes_off_road": "eyes off road", "hands_off_wheel": "hands off wheel",
             "eating_drinking": "eat/drink", "drowsiness": "drowsy", "eyes_closed": "eyes closed"}
LEVEL_BGR = [(0, 200, 0), (0, 220, 255), (0, 0, 255)]
WHITE, GREY, DIM = (240, 240, 240), (150, 150, 150), (90, 90, 90)


class Overlay:
    """Levo: video sa ROI-jevima i svim detekcijama. Desno: panel sa svim promenljivim iz rec/perception.

    Kako citati panel (vrednosti po kategoriji):
      p     sirovi dokaz u ovom frejmu (izlaz FeatureExtractor-a)
      p_hat zagladjen dokaz (EMA, evidence_tau_s); ON kad p_hat >= on, OFF kad p_hat < off (histerezis)
            (bele crtice na traci p su pragovi on/off)
      run   koliko sekundi je kategorija neprekidno aktivna;  D = akumulirano trajanje (opada kad nije aktivna)
      h     faktor trajanja h(D) (base..1);   r = weight * p_hat * h  = doprinos riziku
    """

    def __init__(self, cfg, panel_w=600, history_s=30.0):
        import cv2
        self.cv2, self.cfg, self.pw, self.hist_s = cv2, cfg, panel_w, history_s
        self.hist: deque = deque()
        self.cats = list(cfg["categories"])

    # -- pomocne
    def _t(self, img, x, y, s, col=WHITE, sc=0.45, th=1):
        self.cv2.putText(img, s, (int(x), int(y)), self.cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, self.cv2.LINE_AA)

    def _bar(self, img, x, y, w, h, v, col, marks=()):
        cv2 = self.cv2
        cv2.rectangle(img, (x, y), (x + w, y + h), (55, 55, 55), -1)
        cv2.rectangle(img, (x, y), (x + int(w * clip01(v)), y + h), col, -1)
        for m, mc in marks:
            mx = x + int(w * m)
            cv2.line(img, (mx, y - 2), (mx, y + h + 2), mc, 1)

    def _px(self, pt, W, H):
        return int(pt[0] * W), int(pt[1] * H)

    def _rect(self, img, box, col, label=None, th=1, bottom=False):
        H, W = img.shape[:2]
        p0, p1 = self._px(box[:2], W, H), self._px(box[2:], W, H)
        self.cv2.rectangle(img, p0, p1, col, th)
        if label:
            self._t(img, p0[0] + 4, (p1[1] - 6) if bottom else (p0[1] + 16), label, col, 0.5)

    # -- video deo
    def draw_scene(self, img, rec, face, hands, objects):
        cv2, vc = self.cv2, self.cfg["video"]
        H, W = img.shape[:2]
        self._rect(img, vc["driver_roi"], (200, 200, 0), "driver_roi (hands, phone)", bottom=True)
        self._rect(img, vc["head_roi"], (255, 140, 60), "head_roi (face)")
        self._rect(img, vc["steering_wheel_roi"], (0, 255, 255), "steering_wheel_roi")
        if face is not None:
            for o in face["others"]:
                self._rect(img, o, GREY, "other face (ignored)")
            for p in face["pts"]:
                cv2.circle(img, self._px(p, W, H), 1, (120, 255, 120), -1)
            act = rec["categories"].get("eyes_off_road", {}).get("active", False)
            self._rect(img, face["box"], (0, 0, 255) if act else (0, 255, 0), "driver", 2)
            n = self._px(face["center"], W, H)
            fx, fy = face["fwd"]
            cv2.arrowedLine(img, n, (int(n[0] + 90 * fx), int(n[1] - 90 * fy)), (0, 255, 255), 2, tipLength=0.25)
        for h in (hands or []):
            on = _in_box(h["center"], vc["steering_wheel_roi"])
            col = (0, 255, 0) if on else (0, 140, 255)
            pts = [self._px(p, W, H) for p in h["pts"]]
            for a, b in HAND_LINKS:
                cv2.line(img, pts[a], pts[b], col, 1)
            c = self._px(h["center"], W, H)
            cv2.circle(img, c, 5, col, -1)
            self._t(img, c[0] + 6, c[1] - 6, "on wheel" if on else "off wheel", col, 0.45)
        for o in (objects or []):
            col = (255, 0, 255) if o["cls"] == PHONE_CLS else (120, 255, 120)
            self._rect(img, o["box"], col, f"{COCO_NAMES.get(o['cls'], o['cls'])} {o['conf']:.2f}", 2)
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), LEVEL_BGR[rec["alert"]["code"]], 6)
        return img

    # -- panel
    def draw_panel(self, H, rec, per, info):
        cv2 = self.cv2
        P = np.full((H, self.pw, 3), 28, np.uint8)
        a, rk, cfg = rec["alert"], rec["risk"], self.cfg
        lv = a["code"]
        x, y, L = 10, 22, 19
        self._t(P, x, y, f"t={rec['t']:6.2f}s  frame {rec['frame']}   proc {info['fps']:4.1f} fps  "
                          f"{info['ms']:4.0f} ms/frame", GREY)
        y += L + 6
        cv2.circle(P, (x + 14, y - 6), 14, LEVEL_BGR[lv], -1)
        self._t(P, x + 38, y, f"{a['level'].upper()}   RISK {rk['final']:.2f}", LEVEL_BGR[lv], 0.75, 2)
        self._t(P, x + 330, y, f"(1-R)x100 = {100 * (1 - rk['final']):5.1f}", WHITE, 0.5)
        y += 14
        al = cfg["alerts"]
        self._bar(P, x, y, self.pw - 20, 12, rk["final"], LEVEL_BGR[lv],
                  [(al["yellow"]["on"], LEVEL_BGR[1]), (al["red"]["on"], LEVEL_BGR[2])])
        y += 12 + L
        self._t(P, x, y, f"raw {rk['raw']:.2f}  x ctx {rk['context_factor']:.1f}  -> smooth {rk['smoothed']:.2f}"
                         f"   floor {rk['floor']:.2f}   final = max {rk['final']:.2f}", GREY)
        y += L
        gx = x
        for g, v in rec["groups"].items():
            self._t(P, gx, y + 4, f"{g} {v:.2f}", WHITE)
            self._bar(P, gx + 105, y - 6, 75, 10, v, (200, 200, 200))
            gx += 195
        y += L + 4

        # tabela kategorija
        cols = [x, x + 135, x + 230, x + 285, x + 330, x + 385, x + 440, x + 485]
        for cx, hdr in zip(cols, ["category", "p (raw)", "p_hat", "state", "run s", "D s", "h", "r (contrib)"]):
            self._t(P, cx, y, hdr, GREY, 0.42)
        y += 4
        for n in self.cats:
            c = rec["categories"][n]
            cc = cfg["categories"][n]
            y += L
            col = CAT_COLORS.get(n, WHITE)
            cv2.rectangle(P, (x, y - 10), (x + 8, y), col, -1)
            self._t(P, x + 12, y, CAT_SHORT.get(n, n), WHITE if c["active"] else GREY, 0.45, 2 if c["active"] else 1)
            self._bar(P, cols[1], y - 9, 80, 9, c["p"], col, [(cc["on"], WHITE), (cc["off"], DIM)])
            self._t(P, cols[2], y, f"{c['p_hat']:.2f}", WHITE)
            self._t(P, cols[3], y, "ON" if c["active"] else "off", (0, 0, 255) if c["active"] else DIM, 0.45,
                    2 if c["active"] else 1)
            self._t(P, cols[4], y, f"{c['run_s']:.1f}")
            self._t(P, cols[5], y, f"{c['D_s']:.1f}")
            self._t(P, cols[6], y, f"{c['h']:.2f}")
            self._bar(P, cols[7], y - 9, self.pw - cols[7] - 45, 9, c["r"], col)
            self._t(P, self.pw - 40, y, f"{c['r']:.2f}")
        y += L + 2
        rules = ", ".join(rec["rules_triggered"]) or "-"
        self._t(P, x, y, f"rules: {rules}    VATS off-road in window: {rec['vats_cum_s']:.1f}s",
                (0, 0, 255) if rec["rules_triggered"] else GREY)

        # percepcija
        y += L + 6
        cv2.line(P, (x, y - 12), (self.pw - 10, y - 12), DIM, 1)
        cal = cfg["calibration"]
        if per.get("face_found"):
            self._t(P, x, y, f"FACE yes ({per['n_faces']} in head_roi)   abs yaw {per['yaw_abs']:+6.1f}  "
                             f"pitch {per['pitch_abs']:+6.1f}", (0, 255, 0))
            y += L
            self._t(P, x, y, f"vs road  dyaw {per['yaw']:+6.1f} (thr {cal['yaw_thr_deg']:.0f})  "
                             f"dpitch {per['pitch']:+6.1f} (thr {cal['pitch_thr_deg']:.0f})",
                    (0, 165, 255) if per["p_head"] > 0.5 else WHITE)
            y += L
            self._t(P, x, y, f"p_yaw {per['p_yaw']:.2f}  p_pitch {per['p_pitch']:.2f}  p_head {per['p_head']:.2f}"
                             f"   p_gaze {per['p_gaze']:.2f}  -> eyes_off_road = max")
            y += L
            self._t(P, x, y, f"eyes closed {per['eye_closure']:.2f} (thr {cal['eye_closed_thr']:.2f})  "
                             f"gaze down {per['gaze_down']:.2f} (thr {cal['gaze_down_thr']:.2f})  "
                             f"jaw {per['jaw_open']:.2f}")
        else:
            self._t(P, x, y, f"FACE not found in head_roi -> eyes_off_road = {cal['face_missing_p']:.2f} (fallback)",
                    (0, 0, 255))
            y += 3 * L
        y += L
        b = per["baseline"]
        self._t(P, x, y, f"road baseline yaw {b[0]:+.1f} pitch {b[1]:+.1f}  [{per['baseline_status']}]", GREY)
        y += L
        self._t(P, x, y, f"PERCLOS {per['perclos']:.2f} (window {per['perclos_window_s']:.0f}s, needs >20s)   "
                         f"yawns {per['yawns_window']}", WHITE)
        y += L
        hcol = (0, 255, 0) if per["hands_on_wheel"] >= 2 else (0, 220, 255) if per["hands_on_wheel"] == 1 else (0, 140, 255)
        hs = f"HANDS detected {per['hands_detected']}  on wheel {per['hands_on_wheel']}" if per["hands_detected"] \
            else f"HANDS none detected -> hands_off_wheel = {cal['no_hands_detected_p']:.2f} (fallback)"
        self._t(P, x, y, hs + ("" if per["hands_fresh"] else "  (stale)"), hcol)
        y += L
        ph = per.get("phone")
        if ph:
            self._t(P, x, y, f"PHONE yolo {ph['conf']:.2f}  near hand {ph['near_hand']:.2f}  near face "
                             f"{ph['near_face']:.2f}  lap {ph['lap']:.2f} -> {ph['p']:.2f}", (255, 0, 255))
        else:
            self._t(P, x, y, f"PHONE not seen by YOLO   (memory {per['phone_held']:.2f})", GREY)
        y += L
        objs = ", ".join(f"{COCO_NAMES.get(k, k)} {v:.2f}" for k, v in per["objects"]) or "-"
        self._t(P, x, y, f"objects: {objs}", GREY)

        # vremenska linija
        y += 14
        self._timeline(P, x, y, self.pw - 20, H - y - 10, rec)
        return P

    def _timeline(self, P, x, y, w, h, rec):
        cv2 = self.cv2
        if h < 40:
            return
        t = rec["t"]
        self.hist.append((t, rec["risk"]["final"], rec["alert"]["code"], {n: rec["categories"][n]["r"] for n in self.cats}))
        while self.hist and self.hist[0][0] < t - self.hist_s:
            self.hist.popleft()
        cv2.rectangle(P, (x, y), (x + w, y + h), (40, 40, 40), -1)
        al = self.cfg["alerts"]
        for v, col in ((al["yellow"]["on"], LEVEL_BGR[1]), (al["red"]["on"], LEVEL_BGR[2])):
            yy = y + h - int(v * h)
            cv2.line(P, (x, yy), (x + w, yy), col, 1)
        def X(tt):
            return x + int(w * (1 - (t - tt) / self.hist_s))
        for n in self.cats:
            pts = np.array([(X(tt), y + h - int(rr[n] * h)) for tt, _, _, rr in self.hist], np.int32)
            if len(pts) > 1:
                cv2.polylines(P, [pts], False, CAT_COLORS.get(n, WHITE), 1, cv2.LINE_AA)
        pts = np.array([(X(tt), y + h - int(R * h)) for tt, R, _, _ in self.hist], np.int32)
        if len(pts) > 1:
            cv2.polylines(P, [pts], False, WHITE, 2, cv2.LINE_AA)
        for tt, _, lv, _ in self.hist:
            cv2.line(P, (X(tt), y + h - 4), (X(tt), y + h), LEVEL_BGR[lv], 1)
        self._t(P, x + 4, y + 14, f"last {self.hist_s:.0f}s: white = RISK, colored = r per category", GREY, 0.42)

    def render(self, frame, rec, per, face, hands, objects, info):
        img = self.draw_scene(frame.copy(), rec, face, hands, objects)
        return np.hstack([img, self.draw_panel(img.shape[0], rec, per, info)])


def verbose_line(rec, per):
    c = rec["categories"]
    cats = " ".join(f"{CAT_SHORT.get(n, n).split()[0]}={v['p']:.2f}/{v['r']:.2f}{'*' if v['active'] else ''}"
                    for n, v in c.items())
    face = (f"face yaw{per['yaw']:+.0f} pitch{per['pitch']:+.0f} gd{per['gaze_down']:.2f} cl{per['eye_closure']:.2f}"
            if per["face_found"] else "face --")
    return (f"t={rec['t']:6.2f} R={rec['risk']['final']:.2f} {rec['alert']['level']:6s} | {cats} | {face} | "
            f"hands {per['hands_detected']}/{per['hands_on_wheel']} | phone {per['phone_now']:.2f}")


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
# GLAVNA PETLJA
# ----------------------------------------------------------------------------
def run(video, cfg_path, every=None, show=False, max_seconds=None, save_video=None, verbose=False, log_all=False,
        start_s=0.0):
    import cv2
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    vc, sc, mc = cfg["video"], cfg["schedule"], cfg["models"]
    every = every or vc["process_every_n_frames"]
    roi, head_roi = vc["driver_roi"], vc["head_roi"]

    face = FacePerception(mc["face_landmarker"], mc.get("face_num", 2), mc.get("face_min_conf", 0.4),
                          vc.get("driver_side", "right"))
    hands = HandPerception(mc["hand_landmarker"], mc.get("hands_num", 4))
    objs = ObjectPerception(mc["yolo_onnx"], mc["yolo_input"], mc["yolo_conf"])
    clip = ClipVerifier(mc.get("clip_model", "ViT-B-32"), mc.get("clip_pretrained", "laion2b_s34b_b79k")) \
        if sc.get("clip_every_s", 0) > 0 else None
    fx, engine = FeatureExtractor(cfg), RiskEngine(cfg)
    # jedinstven folder po pokretanju (dva pokretanja u istoj sekundi su ranije pisala u isti frames.jsonl)
    stem = "cam" + str(video) if str(video).isdigit() else Path(str(video)).stem[:40]
    session = f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}"
    n = 1
    while (Path(cfg["logging"]["out_dir"]) / session).exists():
        n += 1
        session = f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}_{n}"
    log = TripLogger(cfg, session, log_all)
    overlay = Overlay(cfg) if (show or save_video) else None
    writer = None

    live = str(video).isdigit()
    cap = cv2.VideoCapture(int(video) if live else video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if start_s and not live:
        cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
    frame0 = 0 if live else int(round(start_s * fps))
    t0 = time.monotonic()
    frame_idx, k, last_ts = frame0 - 1, -1, -1
    held = {"face": (None, -1e9), "hands": (None, -1e9), "objects": (None, -1e9), "clip": (None, -1e9)}
    compute_ms, paused = [], False
    if show:
        cv2.namedWindow("driver risk", cv2.WINDOW_NORMAL)

    while True:
        frame_idx += 1
        if (frame_idx - frame0) % every:
            if not cap.grab():            # preskoceni frejm: bez dekodiranja slike
                break
            continue
        ok, src = cap.read()
        if not ok:
            break
        k += 1
        t = (time.monotonic() - t0) if live else (frame_idx - frame0) / fps
        if max_seconds and t > max_seconds:
            break
        tic = time.perf_counter()

        h, w = src.shape[:2]
        frame = cv2.resize(src, (vc["input_width"], int(h * vc["input_width"] / w)))
        ts_ms = max(int(t * 1000), last_ts + 1)          # MediaPipe VIDEO trazi strogo rastuce vreme
        last_ts = ts_ms
        rgb = lambda img: np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        if k % sc["face_every_n"] == 0:
            held["face"] = (face(rgb(_crop(frame, head_roi)), ts_ms, head_roi), t)
        if k % sc["hands_every_n"] == 0:
            held["hands"] = (hands(rgb(_crop(frame, roi)), ts_ms, roi), t)
        if k % sc["objects_every_n"] == 0:
            # YOLO na isecku iz originalne rezolucije: telefon je mali, a downscale ga brise
            yolo_src = src if vc.get("yolo_full_res", True) else frame
            held["objects"] = (objs(_crop(yolo_src, roi), roi), t)
        get = lambda key: held[key][0] if t - held[key][1] <= sc["max_result_age_s"] else None

        f_res, h_res, o_res = get("face"), get("hands"), get("objects")
        evidence, perception = fx.update(t, f_res, h_res, o_res)
        if clip is not None:
            if t - held["clip"][1] >= sc["clip_every_s"]:
                held["clip"] = (clip(rgb(_crop(frame, roi))), t)
            if held["clip"][0] and t - held["clip"][1] <= 2 * sc["clip_every_s"]:
                for cat, pc in held["clip"][0].items():          # fuzija: CLIP moze samo da podigne dokaz
                    evidence[cat] = max(evidence.get(cat, 0.0), 0.8 * pc)
                perception["clip"] = {kk: r3(v) for kk, v in held["clip"][0].items()}
        rec, events = engine.step(t, evidence, speed_kmh=None)   # speed: iz CAN-a ako postoji
        rec = {"t": rec["t"], "frame": frame_idx, **rec, "perception": perception}
        log.write(rec, events)
        set_cabin_light(rec["alert"]["code"])
        compute_ms.append((time.perf_counter() - tic) * 1000)
        if verbose:
            print(verbose_line(rec, perception), flush=True)

        if overlay is not None:
            recent = compute_ms[-20:]
            info = {"ms": float(np.mean(recent)), "fps": 1000.0 / max(1e-3, float(np.mean(recent)))}
            vis = overlay.render(frame, rec, perception, f_res, h_res, o_res, info)
            if save_video:
                if writer is None:
                    writer = cv2.VideoWriter(save_video, cv2.VideoWriter_fourcc(*"mp4v"), fps / every,
                                             (vis.shape[1], vis.shape[0]))
                writer.write(vis)
            if show:
                cv2.imshow("driver risk", vis)
                key = cv2.waitKey(0 if paused else 1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord(" "):
                    paused = not paused
                if key == ord("s"):
                    p = log.dir / f"frame_{frame_idx}.png"
                    cv2.imwrite(str(p), vis); print(f"saved {p}")

    cap.release()
    if writer is not None:
        writer.release()
    if show:
        cv2.destroyAllWindows()
    log.write_events(engine.finish())
    meta = {"source": str(video), "process_every_n_frames": every, "fps_source": fps,
            "avg_compute_ms_per_processed_frame": r3(np.mean(compute_ms) if compute_ms else 0),
            "road_baseline": [r3(v) for v in fx.baseline.value], "road_baseline_status": fx.baseline.status,
            "config_version": cfg["version"]}
    summ = engine.summary()
    log.close(summ, meta)
    print(json.dumps(summ, indent=2))
    print(f"logs: {log.dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Driver risk from a cabin camera. Keys in --show: SPACE pause, "
                                             "S save screenshot, Q/ESC quit.")
    ap.add_argument("--video", required=True, help="putanja do snimka ili indeks kamere (npr. 0)")
    ap.add_argument("--config", default="risk_config.json")
    ap.add_argument("--every", type=int, default=None, help="obradi svaki N-ti frejm")
    ap.add_argument("--show", action="store_true", help="prozor sa videom i svim promenljivim")
    ap.add_argument("--save-video", default=None, help="snimi prikaz (video + panel) u .mp4")
    ap.add_argument("--verbose", action="store_true", help="jedan red po obradjenom frejmu u terminalu")
    ap.add_argument("--log-all", action="store_true", help="frames.jsonl za svaki obradjeni frejm (ne 5 Hz)")
    ap.add_argument("--start", type=float, default=0.0, help="pocni od ove sekunde snimka")
    ap.add_argument("--max-seconds", type=float, default=None)
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
        run(a.video, a.config, a.every, a.show, a.max_seconds, a.save_video, a.verbose, a.log_all, a.start)
