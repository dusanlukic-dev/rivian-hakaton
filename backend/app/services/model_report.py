"""The camera model's own trip report, built from the stream of its frame records.

The CV pipeline (notebooks/risk_pipeline.py) only computes the per-frame risk and sends each frame
record to POST /telemetry. Everything about the whole drive is computed here, from that stream:

    frame record ──► CameraView ──► ModelReportBuilder.add(t, dt, view, moving)
                                       ├─ risk statistics (mean, RMS, p95, max, model score)
                                       ├─ time per alert level, alert and rule onsets
                                       ├─ per-category active time and behavior episodes
                                       └─ alert episodes (green → yellow/red → green) with their causes

It is the same math the pipeline used to run for its summary.json / events.jsonl. Standing time
(< 5 km/h) is not counted, like the rest of the trip statistics.

Standard library only (plus app.domain), so the pipeline's dev mode can import it too. Offline,
from backend/:

    python -m app.services.model_report ../notebooks/logs/<run>/frames.jsonl [--json]
"""

from __future__ import annotations

import bisect
import json
import math
from dataclasses import dataclass, field
from typing import Any

from app.domain.trip import CameraCategory, CameraView

LEVELS = ("green", "yellow", "red")
_LEVEL_CODE = {name: code for code, name in enumerate(LEVELS)}


@dataclass
class ModelReportConfig:
    power_p: float = 2.0  # risk_rms = (mean of risk^p)^(1/p): long high-risk stretches weigh more than the mean
    episode_min_s: float = 0.5  # shorter behavior episodes are dropped (model flicker)
    episode_merge_gap_s: float = 0.5  # active again within this gap = the same episode
    category_merge_gap_s: dict[str, float] = field(default_factory=lambda: {"eyes_closed": 0.1})  # blinks
    cause_min_r: float = 0.15  # a category contributing at least this much risk is a cause of an alert
    histogram_bins: int = 200  # for the risk percentile
    max_gap_s: float = 5.0  # a longer pause between frames counts as this long
    max_episodes: int = 200  # per list; counts in `categories` stay complete


def _r3(x: float) -> float:
    return round(float(x), 3)


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def view_from_record(record: dict[str, Any]) -> CameraView:
    """A frames.jsonl record (as the pipeline writes it) -> CameraView, without pydantic."""
    alert = record.get("alert") or {}
    level = alert.get("level")
    if level is None and alert.get("code") is not None:
        level = LEVELS[int(alert["code"])] if 0 <= int(alert["code"]) < len(LEVELS) else None
    return CameraView(
        risk=_num((record.get("risk") or {}).get("final")),
        alert=level,
        rules_triggered=list(record.get("rules_triggered") or []),
        categories={
            name: CameraCategory(p=_num(c.get("p")), active=bool(c.get("active")), run_s=_num(c.get("run_s")),
                                 r=_num(c.get("r")))
            for name, c in (record.get("categories") or {}).items()
        },
        groups={name: _num(v) for name, v in (record.get("groups") or {}).items()},
    )


@dataclass
class _Episode:
    start: float
    end: float | None = None  # set while the category is off but may still resume (merge gap)
    peak_r: float = 0.0
    peak_p: float = 0.0


@dataclass
class _CategoryState:
    active: bool = False
    episode: _Episode | None = None
    active_s: float = 0.0
    episodes: int = 0
    max_episode_s: float = 0.0


@dataclass
class _AlertEpisode:
    start: float
    max_level: int
    peak_risk: float
    causes: set[str] = field(default_factory=set)


class ModelReportBuilder:
    """Feed it every model frame of one trip, in order; `snapshot()` is the report so far."""

    def __init__(self, cfg: ModelReportConfig | None = None) -> None:
        self.cfg = cfg or ModelReportConfig()
        self.frames = 0
        self.duration_s = 0.0
        self.stationary_s = 0.0
        self._s1 = self._sp = 0.0
        self._risk_max = 0.0
        self._hist = [0.0] * self.cfg.histogram_bins
        self._t_level = [0.0, 0.0, 0.0]
        self._level = 0
        self._alert_counts = {"yellow": 0, "red": 0}
        self._rule_counts: dict[str, int] = {}
        self._rules_prev: set[str] = set()
        self._cats: dict[str, _CategoryState] = {}
        self._alert: _AlertEpisode | None = None
        self._episodes: list[dict[str, Any]] = []
        self._alert_episodes: list[dict[str, Any]] = []
        self._t_last: float | None = None

    @property
    def empty(self) -> bool:
        return self.frames == 0

    # ---- feeding ----

    def add(self, t: float, dt: float, view: CameraView | None, moving: bool = True) -> None:
        """One frame at time `t` (s), `dt` seconds after the previous one. No view = nothing from the model."""
        if view is None:
            return
        self.frames += 1
        dt = min(max(dt, 0.0), self.cfg.max_gap_s)
        self._t_last = t
        if not moving:  # standing: no statistics, and whatever was going on is over
            self.stationary_s += dt
            self._close_all(t)
            self._level, self._rules_prev = 0, set()
            return

        level = _LEVEL_CODE.get(view.alert or "green", 0)
        risk = view.risk or 0.0
        contributions = {name: c.r or 0.0 for name, c in view.categories.items()}
        for name, c in view.categories.items():
            self._category(name, c, t, dt)
        self._alert_step(t, level, risk, set(view.rules_triggered), contributions)
        for rule in set(view.rules_triggered) - self._rules_prev:
            self._rule_counts[rule] = self._rule_counts.get(rule, 0) + 1
        self._rules_prev = set(view.rules_triggered)

        if dt > 0:
            self.duration_s += dt
            self._s1 += risk * dt
            self._sp += (risk ** self.cfg.power_p) * dt
            self._risk_max = max(self._risk_max, risk)
            bins = len(self._hist)
            self._hist[min(bins - 1, max(0, int(risk * bins)))] += dt
            self._t_level[level] += dt

    def finish(self) -> None:
        """Close the episodes still open at the end of the trip."""
        if self._t_last is not None:
            self._close_all(self._t_last, at_end=True)

    # ---- categories (behavior episodes) ----

    def _gap(self, name: str) -> float:
        return self.cfg.category_merge_gap_s.get(name, self.cfg.episode_merge_gap_s)

    def _category(self, name: str, c: CameraCategory, t: float, dt: float) -> None:
        st = self._cats.setdefault(name, _CategoryState())
        was, st.active = st.active, c.active
        r, p = c.r or 0.0, c.p or 0.0
        ep = st.episode
        if c.active:
            if dt > 0:
                st.active_s += dt
            if not was:
                if ep is not None and ep.end is not None and t - ep.end <= self._gap(name):
                    ep.end = None  # the same episode goes on
                else:
                    if ep is not None:
                        self._close_episode(name, st)
                    ep = st.episode = _Episode(t, peak_r=r, peak_p=p)
            ep.peak_r, ep.peak_p = max(ep.peak_r, r), max(ep.peak_p, p)
        else:
            if was and ep is not None:
                ep.end = t
            if ep is not None and ep.end is not None and t - ep.end > self._gap(name):
                self._close_episode(name, st)

    def _close_episode(self, name: str, st: _CategoryState, end: float | None = None, at_end: bool = False) -> None:
        ep, st.episode = st.episode, None
        if ep is None:
            return
        end = ep.end if ep.end is not None else (end if end is not None else ep.start)
        row = self._episode_row(name, ep, end)
        if row is None:
            return
        st.episodes += 1
        st.max_episode_s = max(st.max_episode_s, row["duration_s"])
        if at_end:
            row["open"] = True
        if len(self._episodes) < self.cfg.max_episodes:
            self._episodes.append(row)

    def _episode_row(self, name: str, ep: _Episode, end: float) -> dict[str, Any] | None:
        duration = end - ep.start
        if duration < self.cfg.episode_min_s:
            return None
        return {"category": name, "t_start": _r3(ep.start), "t_end": _r3(end), "duration_s": _r3(duration),
                "peak_r": _r3(ep.peak_r), "peak_p": _r3(ep.peak_p), "open": False}

    # ---- alerts ----

    def _alert_step(self, t: float, level: int, risk: float, rules: set[str], contributions: dict[str, float]) -> None:
        prev = self._level
        if level > prev:  # green -> red counts as one red alert, not as a yellow one too
            self._alert_counts[LEVELS[level]] += 1
        if prev == 0 and level > 0:
            self._alert = _AlertEpisode(t, level, risk)
        if level == 0 and self._alert is not None:
            self._close_alert(t)
        self._level = level
        if self._alert is not None:
            a = self._alert
            a.max_level, a.peak_risk = max(a.max_level, level), max(a.peak_risk, risk)
            a.causes.update(name for name, r in contributions.items() if r > self.cfg.cause_min_r)
            a.causes.update(f"rule:{rule}" for rule in rules)

    def _alert_row(self, a: _AlertEpisode, end: float, open_: bool) -> dict[str, Any]:
        return {"t_start": _r3(a.start), "t_end": _r3(end), "duration_s": _r3(end - a.start),
                "max_level": LEVELS[a.max_level], "peak_risk": _r3(a.peak_risk), "causes": sorted(a.causes),
                "open": open_}

    def _close_alert(self, t: float, at_end: bool = False) -> None:
        a, self._alert = self._alert, None
        if a is not None and len(self._alert_episodes) < self.cfg.max_episodes:
            self._alert_episodes.append(self._alert_row(a, t, at_end))

    def _close_all(self, t: float, at_end: bool = False) -> None:
        for name, st in self._cats.items():
            if st.episode is not None:
                self._close_episode(name, st, end=t, at_end=at_end and st.episode.end is None)
            st.active = False
        if self._alert is not None:
            self._close_alert(t, at_end)

    # ---- the report ----

    def _percentile(self, q: float) -> float:
        if self.duration_s <= 0:
            return 0.0
        cum, acc = [], 0.0
        for v in self._hist:
            acc += v
            cum.append(acc / self.duration_s)
        return (bisect.bisect_left(cum, q) + 0.5) / len(self._hist)

    def snapshot(self) -> dict[str, Any] | None:
        """The report so far (JSON-ready), with episodes still in progress marked `open`. None without frames."""
        if self.empty:
            return None
        T = self.duration_s
        mean = self._s1 / T if T > 0 else 0.0
        rms = (self._sp / T) ** (1.0 / self.cfg.power_p) if T > 0 else 0.0
        hours = T / 3600.0
        t = self._t_last if self._t_last is not None else 0.0

        episodes = list(self._episodes)
        categories = {}
        for name, st in sorted(self._cats.items()):
            count, longest = st.episodes, st.max_episode_s
            row = None
            if st.episode is not None:  # in progress (or within its merge gap): counted as if it ended now
                row = self._episode_row(name, st.episode, st.episode.end if st.episode.end is not None else t)
            if row is not None:
                row["open"] = st.episode.end is None
                count, longest = count + 1, max(longest, row["duration_s"])
                if len(episodes) < self.cfg.max_episodes:
                    episodes.append(row)
            categories[name] = {"active_s": _r3(st.active_s), "episodes": count, "max_episode_s": _r3(longest)}
        episodes.sort(key=lambda e: (e["t_start"], e["category"]))
        alerts = list(self._alert_episodes)
        if self._alert is not None and len(alerts) < self.cfg.max_episodes:
            alerts.append(self._alert_row(self._alert, t, True))

        return {
            "frames": self.frames,
            "duration_s": _r3(T),
            "stationary_s": _r3(self.stationary_s),
            "risk_mean": _r3(mean),
            "risk_rms": _r3(rms),
            "risk_p95": _r3(self._percentile(0.95)),
            "risk_max": _r3(self._risk_max),
            "model_score": _r3(100.0 * (1.0 - rms)),
            "time_in_alert_s": {LEVELS[i]: _r3(v) for i, v in enumerate(self._t_level)},
            "time_in_alert_frac": {LEVELS[i]: _r3(v / T if T > 0 else 0.0) for i, v in enumerate(self._t_level)},
            "alerts": dict(self._alert_counts),
            "alerts_per_hour": {k: _r3(v / hours if hours > 0 else 0.0) for k, v in self._alert_counts.items()},
            "rules": dict(sorted(self._rule_counts.items())),
            "categories": categories,
            "episodes": episodes,
            "alert_episodes": alerts,
        }


# ---- offline: python -m app.services.model_report frames.jsonl ----

def report_from_records(records: list[dict[str, Any]], cfg: ModelReportConfig | None = None) -> dict[str, Any] | None:
    """The report for a recorded run (frames.jsonl records), on the model's own clock `t`. No speed: all moving."""
    builder = ModelReportBuilder(cfg)
    t_prev: float | None = None
    for record in records:
        t = _num(record.get("t")) or 0.0
        dt = 0.0 if t_prev is None else t - t_prev
        t_prev = t
        builder.add(t, dt, view_from_record(record))
    builder.finish()
    return builder.snapshot()


def format_report(report: dict[str, Any] | None) -> str:
    if report is None:
        return "No model frames."
    lines = [
        f"duration {report['duration_s']:.1f} s ({report['frames']} frames, standing {report['stationary_s']:.1f} s)",
        f"model score {report['model_score']:.1f}   risk mean {report['risk_mean']:.2f}  rms {report['risk_rms']:.2f}"
        f"  p95 {report['risk_p95']:.2f}  max {report['risk_max']:.2f}",
        "time in alert: " + "  ".join(f"{k} {v:.1f} s" for k, v in report["time_in_alert_s"].items()),
        "alerts: " + "  ".join(f"{k} {v}" for k, v in report["alerts"].items())
        + ("   rules: " + ", ".join(f"{k} {v}" for k, v in report["rules"].items()) if report["rules"] else ""),
        "categories:",
    ]
    for name, c in report["categories"].items():
        if c["active_s"] > 0 or c["episodes"]:
            lines.append(f"  {name:<16} active {c['active_s']:5.1f} s  episodes {c['episodes']:>2}"
                         f"  longest {c['max_episode_s']:.1f} s")
    for a in report["alert_episodes"]:
        lines.append(f"  alert {a['max_level']:<6} t={a['t_start']:6.1f}..{a['t_end']:6.1f}  peak {a['peak_risk']:.2f}"
                     f"  {', '.join(a['causes']) or '-'}")
    return "\n".join(lines)


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="The camera model's trip report for a recorded frames.jsonl.")
    ap.add_argument("frames_jsonl")
    ap.add_argument("--json", action="store_true", help="print the report as JSON (what GET /trips/{id}/report has)")
    a = ap.parse_args()
    with open(a.frames_jsonl, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    report = report_from_records(records)
    print(json.dumps(report, indent=2) if a.json else format_report(report))


if __name__ == "__main__":
    _main()
