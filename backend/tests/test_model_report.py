"""The camera model's trip report, built by the backend from the stream of model frames."""

from datetime import timedelta

from app.services.model_report import ModelReportBuilder, report_from_records, view_from_record
from tests.conftest import API, DAY, MODEL_FRAME, send_tick, start_trip


def record(t, risk=0.1, level="green", phone=False, eyes_closed=False, rules=()):
    code = {"green": 0, "yellow": 1, "red": 2}[level]
    return {
        "t": t,
        "categories": {
            "phone_use": {"p": 0.8 if phone else 0.0, "active": phone, "r": 0.6 if phone else 0.0},
            "eyes_closed": {"p": 0.9 if eyes_closed else 0.0, "active": eyes_closed, "r": 0.0},
        },
        "risk": {"final": risk},
        "rules_triggered": list(rules),
        "alert": {"level": level, "code": code},
    }


def drive(spec, step=0.1):
    """spec: list of (seconds, kwargs for record()) -> records every `step` s."""
    out, t = [], 0.0
    for seconds, kw in spec:
        for _ in range(round(seconds / step)):
            out.append(record(round(t, 3), **kw))
            t += step
    return out


def test_statistics_alerts_and_episodes():
    rep = report_from_records(drive([
        (5, {}),
        (3, {"risk": 0.8, "level": "red", "phone": True, "rules": ["phone_sustained"]}),
        (2, {}),
    ]))
    assert rep["frames"] == 100
    assert abs(rep["duration_s"] - 9.9) < 1e-6
    assert rep["time_in_alert_s"]["red"] == 3.0
    assert rep["alerts"] == {"yellow": 0, "red": 1}
    assert rep["rules"] == {"phone_sustained": 1}
    assert rep["risk_max"] == 0.8
    assert 0.1 < rep["risk_mean"] < rep["risk_rms"] < 0.8
    assert abs(rep["model_score"] - 100 * (1 - rep["risk_rms"])) < 0.1

    [ep] = rep["episodes"]
    assert (ep["category"], ep["t_start"], ep["t_end"], ep["duration_s"]) == ("phone_use", 5.0, 8.0, 3.0)
    assert (ep["peak_p"], ep["peak_r"], ep["open"]) == (0.8, 0.6, False)
    assert rep["categories"]["phone_use"] == {"active_s": 3.0, "episodes": 1, "max_episode_s": 3.0}

    [alert] = rep["alert_episodes"]
    assert (alert["t_start"], alert["t_end"], alert["max_level"]) == (5.0, 8.0, "red")
    assert alert["causes"] == ["phone_use", "rule:phone_sustained"]


def test_short_breaks_merge_and_short_flicker_is_dropped():
    rep = report_from_records(drive([
        (1, {"phone": True}), (0.3, {}), (1, {"phone": True}),  # 0.3 s break: one episode
        (2, {}),
        (0.3, {"phone": True}),  # shorter than 0.5 s: no episode, but its time still counts
        (2, {}),
        (0.5, {"eyes_closed": True}), (0.2, {}), (0.5, {"eyes_closed": True}),  # blinks: 0.1 s merge gap
        (1, {}),
    ]))
    phone = [e for e in rep["episodes"] if e["category"] == "phone_use"]
    assert [(e["t_start"], e["t_end"]) for e in phone] == [(0.0, 2.3)]
    assert abs(rep["categories"]["phone_use"]["active_s"] - 2.2) < 1e-6  # the first frame has dt = 0
    assert rep["categories"]["phone_use"]["episodes"] == 1
    closed = [e for e in rep["episodes"] if e["category"] == "eyes_closed"]
    assert len(closed) == 2


def test_open_episode_shows_in_snapshot_and_closes_at_finish():
    builder = ModelReportBuilder()
    for i, r in enumerate(drive([(1, {}), (2, {"risk": 0.5, "level": "yellow", "phone": True})])):
        builder.add(r["t"], 0.0 if i == 0 else 0.1, view_from_record(r))
    live = builder.snapshot()
    assert live["episodes"][0]["open"] and live["alert_episodes"][0]["open"]
    assert live["categories"]["phone_use"]["episodes"] == 1
    builder.finish()
    done = builder.snapshot()
    assert done["episodes"][0]["open"] and done["episodes"][0]["t_end"] == 2.9  # still on at the end
    assert done["alert_episodes"] == [{**live["alert_episodes"][0], "open": True}]


def test_standing_time_is_not_counted():
    builder = ModelReportBuilder()
    red = view_from_record(record(0, risk=0.9, level="red", phone=True))
    for i in range(10):
        builder.add(i * 0.5, 0.5, red, moving=False)
    rep = builder.snapshot()
    assert rep["duration_s"] == 0 and rep["stationary_s"] == 5.0
    assert rep["alerts"] == {"yellow": 0, "red": 0} and rep["episodes"] == []


def test_no_frames_no_report():
    assert ModelReportBuilder().snapshot() is None
    assert report_from_records([]) is None


def test_nan_from_the_model_is_ignored():
    view = view_from_record({"risk": {"final": float("nan")}, "alert": {"code": 2}})
    assert view.risk is None and view.alert == "red"


def test_trip_report_has_the_model_report(client):
    trip_id = start_trip(client)["trip_id"]
    ts = DAY
    clean = {**MODEL_FRAME, "categories": {"phone_use": {"p": 0.0, "active": False, "r": 0.0}},
             "risk": {"final": 0.05}, "rules_triggered": [], "alert": {"level": "green", "code": 0}}
    for i in range(16):
        ts += timedelta(seconds=0.5)
        send_tick(client, ts, 50, frame=MODEL_FRAME if 4 <= i < 10 else clean)
    live = client.get(f"{API}/trips/{trip_id}/report").json()["model"]
    assert live["frames"] == 16 and live["alerts"]["red"] == 1  # live trip: straight from memory

    for _ in range(4):
        ts += timedelta(seconds=0.5)
        send_tick(client, ts, 0, frame=MODEL_FRAME)  # stopped at a light
    assert client.post(f"{API}/trips/{trip_id}/end").status_code == 200

    model = client.get(f"{API}/trips/{trip_id}/report").json()["model"]
    assert model["frames"] == 20 and model["stationary_s"] == 2.0 and model["duration_s"] == 7.5
    assert model["time_in_alert_s"]["red"] == 3.0
    assert model["rules"] == {"long_distraction": 1, "phone_sustained": 1}
    eps = {e["category"]: e for e in model["episodes"]}
    assert (eps["phone_use"]["t_start"], eps["phone_use"]["t_end"]) == (2.0, 5.0)
    [alert] = model["alert_episodes"]
    assert alert["max_level"] == "red" and "phone_use" in alert["causes"]


def test_trip_without_model_frames_has_no_model_report(client):
    trip_id = start_trip(client)["trip_id"]
    send_tick(client, DAY, 50, behaviors=["looking_at_phone"])
    assert client.post(f"{API}/trips/{trip_id}/end").status_code == 200
    assert client.get(f"{API}/trips/{trip_id}/report").json()["model"] is None
