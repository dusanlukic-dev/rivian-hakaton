"""The backend's category mapping must cover every category the CV model can report."""

import json
from pathlib import Path

import pytest

from app.domain.enums import Behavior
from app.schemas.camera import ModelFrame
from app.services.camera import CATEGORY_TO_BEHAVIOR, IGNORED_CATEGORIES, behaviors_from_frame

RISK_CONFIG = Path(__file__).resolve().parents[2] / "notebooks" / "risk_config.json"


def model_categories() -> list[str]:
    if not RISK_CONFIG.exists():
        pytest.skip(f"{RISK_CONFIG} not found")
    return list(json.loads(RISK_CONFIG.read_text(encoding="utf-8"))["categories"])


def test_every_model_category_is_mapped_or_ignored():
    unknown = [c for c in model_categories() if c not in CATEGORY_TO_BEHAVIOR and c not in IGNORED_CATEGORIES]
    assert not unknown, (
        f"risk_config.json has categories the backend doesn't know: {unknown}. "
        "Map them in CATEGORY_TO_BEHAVIOR or list them in IGNORED_CATEGORIES (app/services/camera.py)."
    )


def test_eyes_closed_counts_as_drowsy():
    frame = ModelFrame(categories={"eyes_closed": {"p": 0.9, "active": True}})
    assert behaviors_from_frame(frame) == {Behavior.DROWSY}


def test_ignored_category_is_not_scored():
    frame = ModelFrame(categories={"eating_drinking": {"p": 0.9, "active": True}})
    assert behaviors_from_frame(frame) == set()
