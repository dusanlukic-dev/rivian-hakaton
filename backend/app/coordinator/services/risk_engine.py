"""The per-frame risk engine of the coordinator: model evidence -> risk, alert, active categories.

Origin: `RiskEngine` of the CV team's `notebooks/risk_pipeline.py` (commit 76d38e7), copied unchanged. Their
pipeline was removed when the model in `rivian_model/` replaced it (2026-11-07), so this is now the only copy.
The model only *detects* (`rivian_model/rivian_detector.py`: evidence p_i per category); the coordinator computes
everything after that: this engine, then our 0-100 score (`scoring.py`) and the car's reaction (`alerts.py`).
The whole-trip statistics of the model (episodes, alert time, rules) are `app/services/model_report.py`, which
the coordinator feeds with every tick. Thresholds: `notebooks/risk_config.json`.

Per step, in order (MATEMATICKI_MODEL.md, CV team):
  1. EMA smoothing of each category's evidence (evidence_tau_s)
  2. hysteresis on/off thresholds -> `active`
  3. duration accumulator D (grows while active, decays otherwise) -> duration factor h(D)
  4. contribution r_i = weight * p_hat * h
  5. max within a group (visual / manual / fatigue), noisy-OR between groups -> raw risk
  6. optional speed context (off in the config: our score handles speed)
  7. EMA smoothing of the risk (risk_tau_s)
  8. hard rules (microsleep, long distraction, phone, VATS) -> a floor under the risk
  9. alert level green / yellow / red with hysteresis and hold times
"""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any

LEVELS = ["green", "yellow", "red"]


def load_risk_config(path: Path) -> dict[str, Any]:
    """`risk_config.json` of the CV team (categories, rules, alerts, smoothing)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def ema_alpha(dt: float, tau: float) -> float:
    """Time-consistent EMA coefficient (works when frames are skipped)."""
    if dt <= 0 or tau <= 0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


def r3(x: float) -> float:
    return round(float(x), 3)


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
                    floor = max(floor, rule["floor"]); fired.add(rule["name"])  # noqa: E702
            elif rule["type"] == "vats":
                t = self.t_prev
                if off_road:
                    self.vats_buf.append((t, dt)); self.on_road_run = 0.0  # noqa: E702
                else:
                    self.on_road_run += dt
                    if self.on_road_run >= rule["reset_on_road_s"]:
                        self.vats_buf.clear()
                while self.vats_buf and self.vats_buf[0][0] < t - rule["window_s"]:
                    self.vats_buf.popleft()
                vats_cum = sum(d for _, d in self.vats_buf)
                if vats_cum >= rule["cum_s"]:
                    floor = max(floor, rule["floor"]); fired.add(rule["name"])  # noqa: E702
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
