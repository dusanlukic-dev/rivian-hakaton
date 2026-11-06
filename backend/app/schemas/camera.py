"""One record of the camera model's frames.jsonl, exactly as the CV pipeline writes it.

Only the fields the backend uses are declared. Everything else (dt, p_hat, D_s, h, risk.raw,
top_contributors, perception...) is ignored, so the model side can send its record unchanged and
add fields without breaking anything.
"""

import math
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field


def _finite_or_none(value: Any) -> Any:
    # NaN / inf (e.g. no face in the frame) would break JSON.parse in the app.
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


Number = Annotated[float | None, BeforeValidator(_finite_or_none)]


class FrameCategory(BaseModel):
    p: Number = None
    active: bool = False
    run_s: Number = None
    r: Number = None


class FrameRisk(BaseModel):
    final: Number = None


class FrameAlert(BaseModel):
    level: str | None = None  # "green" | "yellow" | "red"
    code: int | None = None  # 0 | 1 | 2, used when level is missing


class ModelFrame(BaseModel):
    t: Number = None
    frame: int | None = None
    categories: dict[str, FrameCategory] = Field(default_factory=dict)
    groups: dict[str, Number] = Field(default_factory=dict)
    risk: FrameRisk | None = None
    rules_triggered: list[str] = Field(default_factory=list)
    alert: FrameAlert | None = None
