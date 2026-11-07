"""Frames of the car link (docs/BLUETOOTH.md § Okviri): one JSON message cut into BLE-sized pieces.

    bytes 0-1  msg_id  uint16 BE   the sender's message number (wraps after 65535)
    bytes 2-3  index   uint16 BE   0 .. count-1
    bytes 4-5  count   uint16 BE   >= 1
    bytes 6..  a slice of the UTF-8 JSON

Pure Python on purpose: the phone (modules/car-link, Kotlin) does the same, and tests run without Bluetooth.
"""

from __future__ import annotations

import struct

HEADER = 6
MAX_COUNT = 0xFFFF
_HEAD = struct.Struct(">HHH")


def encode(msg_id: int, payload: bytes, max_frame: int) -> list[bytes]:
    """Cuts `payload` into frames of at most `max_frame` bytes (header included)."""
    chunk = max(1, max_frame - HEADER)
    count = max(1, -(-len(payload) // chunk))
    if count > MAX_COUNT:
        raise ValueError(f"message of {len(payload)} bytes needs {count} frames (max {MAX_COUNT})")
    msg_id &= 0xFFFF
    return [
        _HEAD.pack(msg_id, i, count) + payload[i * chunk : (i + 1) * chunk]
        for i in range(count)
    ]


class Reassembler:
    """Collects the frames of one sender. A missing or foreign frame drops the message being built, so a lost
    frame costs that one message, never the rest of the stream."""

    def __init__(self) -> None:
        self._id = -1
        self._next = 0
        self._count = 0
        self._parts: list[bytes] = []
        self.dropped = 0

    def push(self, frame: bytes) -> bytes | None:
        """Adds one frame; returns the whole payload when this frame completed a message."""
        if len(frame) < HEADER:
            self._reset(drop=True)
            return None
        msg_id, index, count = _HEAD.unpack_from(frame)
        if count == 0 or index >= count:
            self._reset(drop=True)
            return None
        if index == 0:
            self._reset(drop=bool(self._parts))
            self._id, self._count = msg_id, count
        elif msg_id != self._id or index != self._next or count != self._count:
            self._reset(drop=True)
            return None
        self._parts.append(frame[HEADER:])
        self._next = index + 1
        if self._next < self._count:
            return None
        payload = b"".join(self._parts)
        self._reset(drop=False)
        return payload

    def _reset(self, *, drop: bool) -> None:
        if drop and self._parts:
            self.dropped += 1
        self._id, self._next, self._count, self._parts = -1, 0, 0, []
