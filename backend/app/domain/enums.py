from enum import StrEnum


class Behavior(StrEnum):
    """Risky behaviors the in-cabin camera models report (labels only, never images)."""

    LOOKING_AT_PHONE = "looking_at_phone"  # gleda u telefon
    LOOKING_BEHIND = "looking_behind"      # gleda iza sebe
    TURNING_AROUND = "turning_around"      # okreće se (telom)
    HANDS_OFF_WHEEL = "hands_off_wheel"    # ruke van volana
    DROWSY = "drowsy"                      # pospan
    EYES_OFF_ROAD = "eyes_off_road"        # pogled van puta


class SafetyLevel(StrEnum):
    SAFE = "safe"            # 90-100
    CAUTION = "caution"      # 75-90
    WARNING = "warning"      # 55-75
    HIGH_RISK = "high_risk"  # 35-55
    CRITICAL = "critical"    # 10-35
    EMERGENCY = "emergency"  # < 10


class DashboardLight(StrEnum):
    GREEN = "green"
    GREEN_YELLOW = "green_yellow"
    YELLOW = "yellow"
    RED = "red"


class SoundLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


class TripStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class SpeedSource(StrEnum):
    """Where the speed used for a tick came from (the camera itself doesn't know it)."""

    MOCK = "mock"            # the backend's simulated drive (default)
    PHONE = "phone"          # the phone's GPS via POST /speed (only with PHONE_SPEED_ENABLED=true)
    TELEMETRY = "telemetry"  # sent in the tick itself (simulator, tests, a car that knows its speed)


class LiveEvent(StrEnum):
    """Message types pushed to the mobile app over the WebSocket."""

    TRIP_STARTED = "trip_started"  # data: TripState
    STATE = "state"                # data: TripState, after every telemetry tick
    EMERGENCY = "emergency"        # data: TripState, once per trip when the score drops below 10
    TRIP_ENDED = "trip_ended"      # data: TripSummary
