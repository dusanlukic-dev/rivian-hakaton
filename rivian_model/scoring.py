"""
Jedinstveni scoring sistem za pažnju vozača.

Ulaz: za svaki frejm -> timestamp (s) + verovatnoće po kategoriji (0-1),
      dobijene fuzijom YOLO / MediaPipe / CLIP signala.
Izlaz: događaji, alarmi uživo, skor 0-100, boja, najkritičniji frejm (JSON).

Ključne ideje:
- sve se računa po VREMENU (sekunde), ne po broju frejmova (fps varira)
- EMA glačanje + histereza -> nema treperenja alarma
- događaj se računa tek kad traje >= min_duration
- u svakom trenutku se kažnjava samo NAJGORA aktivna kategorija (nema duplog kažnjavanja)
- potvrđen kolaps (hitan alarm) odmah obara skor na 0 (crveno), u istom trenutku kad krene alarm
"""
from dataclasses import dataclass, field
import json


@dataclass
class Category:
    name: str
    weight: float          # koliko je opasno (0-1)
    on_thr: float = 0.6    # ulazak u stanje
    off_thr: float = 0.4   # izlazak iz stanja (histereza)
    min_duration: float = 2.0   # s - kraće od ovoga se ignoriše
    alert_after: float = 3.0    # s - posle ovoga dashboard crveni
    instant_alarm: bool = False # npr. kolaps: hitan alarm (emergency), ne kažnjava se po sekundi
    zero_score: bool = False    # npr. kolaps: kad se potvrdi (>= min_duration), skor odmah pada na 0


DEFAULT_CATEGORIES = [
    Category("phone",      weight=1.0, min_duration=1.5, alert_after=3.0),
    Category("look_away",  weight=0.8, min_duration=2.0, alert_after=2.5),
    Category("drowsy",     weight=0.9, min_duration=1.5, alert_after=2.0),
    Category("eating",     weight=0.4, min_duration=3.0, alert_after=6.0),
    Category("no_belt",    weight=0.6, min_duration=5.0, alert_after=5.0),
    Category("collapse",   weight=1.0, min_duration=2.0, alert_after=2.0, instant_alarm=True, zero_score=True),
]


@dataclass
class _State:
    ema: float = 0.0
    active: bool = False
    start: float = 0.0
    peak: float = 0.0
    peak_t: float = 0.0
    sev_sum: float = 0.0
    n: int = 0
    alerted: bool = False


class DriverScorer:
    def __init__(self, trip_id, categories=DEFAULT_CATEGORIES, ema_alpha=0.3,
                 penalty_per_risk_second=6.0):
        # penalty_per_risk_second: 6 -> ~8s telefona = -50 bodova
        self.trip_id = trip_id
        self.cats = {c.name: c for c in categories}
        self.alpha = ema_alpha
        self.k = penalty_per_risk_second
        self.state = {c: _State() for c in self.cats}
        self.events, self.alerts = [], []
        self.penalty = 0.0
        self.last_t = None
        self.t0 = None

    def update(self, t, probs):
        """t: timestamp u sekundama; probs: {"phone": 0.83, ...}. Vraća live poruku za dashboard."""
        self.t0 = t if self.t0 is None else self.t0
        dt = 0.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t
        live_reason, worst_risk = None, 0.0

        for name, cat in self.cats.items():
            s = self.state[name]
            p = float(probs.get(name, 0.0))
            s.ema = self.alpha * p + (1 - self.alpha) * s.ema

            if not s.active and s.ema >= cat.on_thr:
                s.active, s.start, s.peak, s.sev_sum, s.n, s.alerted = True, t, 0.0, 0.0, 0, False
            elif s.active and s.ema < cat.off_thr:
                self._close(name, t)
                continue

            if s.active:
                s.sev_sum += s.ema; s.n += 1
                if s.ema > s.peak:
                    s.peak, s.peak_t = s.ema, t
                dur = t - s.start
                if dur >= cat.min_duration and cat.zero_score:
                    self.penalty = max(self.penalty, 100.0)   # potvrđen kolaps: skor 0, crveno
                if dur >= cat.min_duration and not cat.instant_alarm:
                    risk = cat.weight * s.ema
                    if risk > worst_risk:
                        worst_risk = risk
                if dur >= cat.alert_after:
                    live_reason = live_reason or name
                    if not s.alerted:
                        s.alerted = True
                        self.alerts.append({"t": round(t - self.t0, 2), "type": name,
                                            "emergency": cat.instant_alarm})

        self.penalty += self.k * worst_risk * dt   # samo najgora kategorija u trenutku
        return {"trip_id": self.trip_id, "t": round(t - self.t0, 2),
                "alert": live_reason is not None, "reason": live_reason,
                "live_score": self.score()}

    def _close(self, name, t):
        s, cat = self.state[name], self.cats[name]
        dur = t - s.start
        if dur >= cat.min_duration:
            self.events.append({
                "trip_id": self.trip_id, "event_id": len(self.events),
                "type": name,
                "start": round(s.start - self.t0, 2), "end": round(t - self.t0, 2),
                "severity": round(cat.weight * s.sev_sum / max(s.n, 1), 3),
                "peak_t": round(s.peak_t - self.t0, 2),   # frejm za "najkritičniju sliku"
                "emergency": cat.instant_alarm,
            })
        s.active = False

    def score(self):
        return int(round(max(0.0, 100.0 - self.penalty)))

    def finish(self):
        for name, s in self.state.items():
            if s.active:
                self._close(name, self.last_t)
        sc = self.score()
        color = "green" if sc >= 80 else "yellow" if sc >= 50 else "red"
        # najkritičniji događaj: hitan (kolaps) ima prednost; inače najveći severity x trajanje
        pool = [e for e in self.events if e["emergency"]] or self.events
        critical = max(pool, key=lambda e: e["severity"] * (e["end"] - e["start"]), default=None)
        return {"trip_id": self.trip_id,
                "duration": round((self.last_t or 0) - (self.t0 or 0), 2),
                "score": sc, "color": color,
                "critical_event_id": critical["event_id"] if critical else None,
                "critical_frame_t": critical["peak_t"] if critical else None,
                "emergency": any(e["emergency"] for e in self.events),
                "events": self.events, "alerts": self.alerts}


if __name__ == "__main__":
    # mali test: 30s vožnje na 10 fps, telefon od 8s do 14s, pogled sa puta 20-21s (prekratko)
    sc = DriverScorer("demo")
    for i in range(300):
        t = i / 10
        probs = {"phone": 0.9 if 8 <= t < 14 else 0.05,
                 "look_away": 0.85 if 20 <= t < 21 else 0.1}
        live = sc.update(t, probs)
        if live["alert"] and i % 10 == 0:
            print("LIVE", live)
    print(json.dumps(sc.finish(), indent=2, ensure_ascii=False))