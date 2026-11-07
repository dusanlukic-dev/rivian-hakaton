"""The coordinator's RiskEngine: model evidence -> risk, active categories, rules, alert.

It started as a copy of the CV team's engine (their pipeline is gone since the model in rivian_model/ replaced it,
2026-11-07), so this is now the only copy. Whole-trip statistics are app/services/model_report.py
(test_model_report.py); the collapse category is covered in test_collapse.py.
"""

import random

import pytest

from app.coordinator.services.risk_engine import LEVELS, RiskEngine, load_risk_config
from app.core.config import REPO_DIR

CONFIG = load_risk_config(REPO_DIR / "notebooks" / "risk_config.json")


def evidence_stream(seed: int, steps: int):
    """Random evidence like the model's: long calm stretches, bursts, skipped frames, repeated timestamps."""
    rng = random.Random(seed)
    names = list(CONFIG["categories"])
    level = {name: 0.0 for name in names}
    t = 0.0
    for _ in range(steps):
        t += rng.choice([0.0, 0.033, 0.1, 0.1, 0.1, 0.2, 0.35, 1.2])
        for name in names:
            if rng.random() < 0.03:
                level[name] = rng.choice([0.0, 0.0, 0.3, 0.6, 0.9, 1.0])
            level[name] = min(1.0, max(0.0, level[name] + rng.uniform(-0.08, 0.08)))
        yield t, dict(level)


@pytest.mark.parametrize("seed", range(3))
def test_records_stay_in_range_on_random_evidence(seed):
    engine = RiskEngine(CONFIG)
    for t, evidence in evidence_stream(seed, 3000):
        record = engine.step(t, evidence)
        assert 0.0 <= record["risk"]["final"] <= 1.0
        assert record["alert"]["level"] in LEVELS
        assert set(record["categories"]) == set(CONFIG["categories"])


def test_a_category_the_model_does_not_send_stays_inactive():
    engine = RiskEngine(CONFIG)
    record = {}
    for i in range(50):  # the model in rivian_model/ never sends hands_off_wheel
        record = engine.step(i * 0.1, {"phone_use": 0.05})
    assert not record["categories"]["hands_off_wheel"]["active"] and record["alert"]["level"] == "green"


def test_sustained_phone_use_goes_red():
    engine = RiskEngine(CONFIG)
    record = {}
    for i in range(40):  # 4 s at 10 Hz: phone in hand, eyes down
        record = engine.step(i * 0.1, {"phone_use": 0.95, "eyes_off_road": 0.9})
    assert record["categories"]["phone_use"]["active"] and record["alert"]["level"] == "red"
    assert "phone_sustained" in record["rules_triggered"]
    for i in range(40, 140):  # 10 s back on the road
        record = engine.step(i * 0.1, {})
    assert record["alert"]["level"] == "green" and not record["categories"]["phone_use"]["active"]
