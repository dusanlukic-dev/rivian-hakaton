"""Advice per behavior, shown with the trip summary. Every Behavior needs one (a test checks it)."""

from app.domain.enums import Behavior

TIPS: dict[Behavior, str] = {
    Behavior.LOOKING_AT_PHONE: "Put your phone in a holder or turn on Do Not Disturb while driving.",
    Behavior.LOOKING_BEHIND: "Use your mirrors instead of looking back; pull over if something in the back seat needs attention.",
    Behavior.TURNING_AROUND: "Stay facing the road - turning in your seat takes your eyes and hands away from driving.",
    Behavior.HANDS_OFF_WHEEL: "Keep both hands on the wheel - it's your fastest way to react.",
    Behavior.DROWSY: "You showed signs of drowsiness - take a break at least every 2 hours and don't drive tired.",
    Behavior.EYES_OFF_ROAD: "Keep your eyes on the road - a glance away should never last longer than 2 seconds.",
}
