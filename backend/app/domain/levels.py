"""Score bands -> safety level. Shared: the coordinator reacts to them, the server labels stored summaries."""

from app.domain.enums import SafetyLevel

# (lower bound inclusive, level), checked top to bottom.
LEVEL_BANDS: tuple[tuple[float, SafetyLevel], ...] = (
    (90.0, SafetyLevel.SAFE),
    (75.0, SafetyLevel.CAUTION),
    (55.0, SafetyLevel.WARNING),
    (35.0, SafetyLevel.HIGH_RISK),
    (10.0, SafetyLevel.CRITICAL),
    (0.0, SafetyLevel.EMERGENCY),
)


def level_for(score: float) -> SafetyLevel:
    for lower, level in LEVEL_BANDS:
        if score >= lower:
            return level
    return SafetyLevel.EMERGENCY
