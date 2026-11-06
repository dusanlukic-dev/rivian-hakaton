"""Camera model frames -> behavior labels for the score, plus a slim view for the app."""

import logging

from app.domain.enums import Behavior
from app.domain.trip import CameraCategory, CameraView
from app.schemas.camera import ModelFrame

logger = logging.getLogger(__name__)

# Model category name -> backend label. Our own label names map to themselves.
# A category missing here still reaches the app through `camera`, but doesn't affect the score.
CATEGORY_TO_BEHAVIOR: dict[str, Behavior] = {
    **{behavior.value: behavior for behavior in Behavior},
    "phone_use": Behavior.LOOKING_AT_PHONE,
    "turned_around": Behavior.TURNING_AROUND,
    "hands_off": Behavior.HANDS_OFF_WHEEL,
    "drowsiness": Behavior.DROWSY,
    "microsleep": Behavior.DROWSY,
}

ALERT_BY_CODE = {0: "green", 1: "yellow", 2: "red"}

_unmapped_seen: set[str] = set()


def behaviors_from_frame(frame: ModelFrame) -> set[Behavior]:
    """Labels for the categories the model currently marks as active."""
    behaviors: set[Behavior] = set()
    for name, category in frame.categories.items():
        behavior = CATEGORY_TO_BEHAVIOR.get(name)
        if behavior is None:
            if name not in _unmapped_seen:
                _unmapped_seen.add(name)
                logger.warning(
                    "Camera category %r has no backend label: shown in the app, not scored. "
                    "Map it in CATEGORY_TO_BEHAVIOR (app/services/camera.py).",
                    name,
                )
            continue
        if category.active:
            behaviors.add(behavior)
    return behaviors


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def to_view(frame: ModelFrame) -> CameraView:
    alert = None
    if frame.alert is not None:
        alert = frame.alert.level or ALERT_BY_CODE.get(frame.alert.code)
    return CameraView(
        risk=_round(frame.risk.final) if frame.risk else None,
        alert=alert,
        rules_triggered=list(frame.rules_triggered),
        categories={
            name: CameraCategory(p=_round(c.p), active=c.active, run_s=_round(c.run_s), r=_round(c.r))
            for name, c in frame.categories.items()
        },
        groups={name: _round(value) for name, value in frame.groups.items()},
    )
