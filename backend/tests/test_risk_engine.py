"""The coordinator's RiskEngine is a copy of the CV team's (notebooks/risk_pipeline.py). It must stay identical.

The original is imported straight from the CV team's file (it needs numpy, nothing else at import time), so a
change on either side shows up here. Whole-trip statistics are app/services/model_report.py (test_model_report.py).
"""

import importlib.util
import random

import pytest

from app.coordinator.services.risk_engine import RiskEngine, load_risk_config
from app.core.config import REPO_DIR

PIPELINE = REPO_DIR / "notebooks" / "risk_pipeline.py"
CONFIG = load_risk_config(REPO_DIR / "notebooks" / "risk_config.json")


@pytest.fixture(scope="module")
def original():
    pytest.importorskip("numpy")
    if not PIPELINE.exists():
        pytest.skip("notebooks/risk_pipeline.py is not in this checkout")
    spec = importlib.util.spec_from_file_location("cv_risk_pipeline", PIPELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


@pytest.mark.parametrize("seed", range(5))
def test_extracted_engine_matches_the_cv_original(original, seed):
    ours, theirs = RiskEngine(CONFIG), original.RiskEngine(CONFIG)
    for t, evidence in evidence_stream(seed, 4000):
        assert ours.step(t, evidence) == theirs.step(t, evidence)


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
