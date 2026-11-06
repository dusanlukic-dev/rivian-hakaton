"""The CV team's risk model, extracted into the coordinator: model evidence -> risk, alert, active categories.

Source: `RiskEngine` in `notebooks/risk_pipeline.py` (CV team, commit 6de0163, 2026-11-06), copied without
editing their file. The model worker now only *detects* (perception + FeatureExtractor -> evidence p_i per
category, see `model/worker.py`); the coordinator computes everything after that: this engine, then our
0-100 score (`scoring.py`) and the car's reaction (`alerts.py`).

The math is unchanged. The only difference: plain Python instead of numpy for the risk histogram (same
arithmetic, no numpy in the coordinator). `tests/test_risk_engine.py` replays random evidence through this
copy and the original and requires identical records and summaries, so a change on either side shows up.
Until the CV code is cleaned up, tune thresholds in `notebooks/risk_config.json` (both read it).

Per step, in order (MATEMATICKI_MODEL.md, CV team):
  1. EMA smoothing of each category's evidence (evidence_tau_s)
  2. hysteresis on/off thresholds -> `active`
  3. duration accumulator D (grows while active, decays otherwise) -> duration factor h(D)
  4. contribution r_i = weight * p_hat * h
  5. max within a group (visual / manual / fatigue), noisy-OR between groups -> raw risk
  6. optional speed context (off in the config: our score handles speed)
  7. EMA smoothing of the risk (risk_tau_s)
  8. hard rules (microsleep, long distraction, phone, VATS) -> a risk floor
  9. alert level green / yellow / red with hysteresis and hold times
 10. trip statistics for summary()
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from collections import deque
from itertools import accumulate
from pathlib import Path
from typing import Any

LEVELS = ["green", "yellow", "red"]


def load_risk_config(path: Path) -> dict[str, Any]:
    """`risk_config.json` of the CV team (categories, rules, alerts, smoothing, logging)."""
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
    __slots__ = ("name", "cfg", "p_hat", "active", "D", "run", "ev_start", "ev_end", "ev_peak_r", "ev_peak_p")

    def __init__(self, name, cfg):
        self.name, self.cfg = name, cfg
        self.p_hat, self.active, self.D, self.run = 0.0, False, 0.0, 0.0
        self.ev_start, self.ev_end, self.ev_peak_r, self.ev_peak_p = None, None, 0.0, 0.0

    def duration_factor(self) -> float:
        """h_i(D) = b + (1-b) * s(D), s = normalized logistic curve, s(0)=0, s(inf)=1."""
        c = self.cfg
        k, T, b = c["k"], c["T_crit_s"], c["base"]
        s0 = sigmoid(-k * T)
        s = (sigmoid(k * (self.D - T)) - s0) / (1.0 - s0)
        return b + (1.0 - b) * clip01(s)


class RiskEngine:
    """One engine per trip (it keeps per-category durations, the VATS buffer and the alert state)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.groups = cfg["groups"]
        self.cats = {n: _Cat(n, c) for n, c in cfg["categories"].items()}
        self.tau_e = cfg["smoothing"]["evidence_tau_s"]
        self.tau_r = cfg["smoothing"]["risk_tau_s"]
        self.t_prev = None
        self.R_smooth = 0.0
        # VATS (Euro NCAP short distraction) state
        self.vats_buf: deque = deque()
        self.on_road_run = 0.0
        # alert state
        a = cfg["alerts"]
        self.a = a
        self.level, self.level_since = 0, 0.0
        self.rise_t, self.fall_t = 0.0, 0.0
        self.alert_ev = None
        # trip summary
        self.p = cfg["logging"].get("summary_power_p", 2.0)
        self.ev_min = cfg["logging"].get("event_min_s", 0.5)
        self.ev_gap = cfg["logging"].get("event_merge_gap_s", 0.5)
        self.T_total = self.S1 = self.Sp = self.R_max = 0.0
        self.hist = [0.0] * 200  # time-weighted histogram of R (numpy.zeros(200) in the original)
        self.t_level = [0.0, 0.0, 0.0]
        self.cat_stats = {n: {"active_s": 0.0, "events": 0, "max_event_s": 0.0} for n in self.cats}
        self.alert_counts = {"yellow": 0, "red": 0}
        self.rule_counts = {r["name"]: 0 for r in cfg["rules"]}
        self._rules_prev: set = set()

    # ---------------------------------------------------------------- step
    def step(self, t: float, evidence: dict, speed_kmh: float | None = None) -> tuple[dict, list]:
        """One model step at time t. Returns (frame record, list of events)."""
        dt = 0.0 if self.t_prev is None else max(0.0, t - self.t_prev)
        self.t_prev = t
        events = []

        # (1) smoothing of the evidence, (2) hysteresis, (3) duration accumulator, (4) contribution r_i
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

        # (5) aggregation: max within a group (correlated categories), noisy-OR between groups
        R_g = {}
        for g in self.groups:
            R_g[g] = max((cc.cfg["membership"].get(g, 0.0) * r[n] for n, cc in self.cats.items()), default=0.0)
        prod = 1.0
        for g in self.groups:
            prod *= (1.0 - R_g[g])
        R_raw = 1.0 - prod

        # (6) context (speed, if available over CAN)
        ctx = self.cfg["context"]
        cf = 1.0
        if ctx.get("use_speed") and speed_kmh is not None and speed_kmh < ctx["speed_min_kmh"]:
            cf = ctx["stationary_factor"]

        # (7) smoothing of the total risk over time
        self.R_smooth += ema_alpha(dt, self.tau_r) * (cf * R_raw - self.R_smooth) if dt > 0 else 0.0
        if dt == 0:
            self.R_smooth = cf * R_raw

        # (8) hard rules (Euro NCAP inspired) -> a floor under the risk
        floor, fired, vats_cum = self._rules(dt)
        R = max(self.R_smooth, cf * floor)

        # (9) alert with hysteresis
        events += self._alert(t, dt, R, fired, r)

        # (10) statistics for the end of the trip
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

    # ---------------------------------------------------------------- rules
    def _rules(self, dt):
        floor, fired = 0.0, set()
        eor = self.cats.get("eyes_off_road")
        ph = self.cats.get("phone_use")
        off_road = (eor is not None and eor.active) or (ph is not None and ph.active)
        # VATS buffer: cumulative time looking away from the road in a sliding window
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

    # ---------------------------------------------------------------- alert
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

    # ---------------------------------------------------------------- events
    def _category_event(self, c, was, t, r_i):
        """Behavior event: merges breaks shorter than event_merge_gap_s, drops events shorter than event_min_s."""
        out = []
        if c.active:
            if not was:
                gap = c.cfg.get("event_merge_gap_s", self.ev_gap)
                if c.ev_start is not None and c.ev_end is not None and t - c.ev_end <= gap:
                    c.ev_end = None  # the same event continues
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
        """Closes the open events at the end of the trip."""
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

    # ---------------------------------------------------------------- summary
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
        # np.searchsorted(np.cumsum(hist) / T_total, q) in the original: the same sums, in the same order
        cum = [c / self.T_total for c in accumulate(self.hist)]
        return (bisect_left(cum, q) + 0.5) / len(self.hist)

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
