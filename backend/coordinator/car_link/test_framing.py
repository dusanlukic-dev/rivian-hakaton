"""The car link's frames (docs/BLUETOOTH.md): round trips, sizes, and what a lost frame costs."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framing import HEADER, Reassembler, encode  # noqa: E402


def message(size: int) -> bytes:
    return json.dumps({"type": "section", "data": {"pad": "é" * size}}).encode()


@pytest.mark.parametrize("max_frame", [20, 23, 185, 244, 514])
@pytest.mark.parametrize("size", [0, 1, 100, 1500, 6000])
def test_round_trip(max_frame, size):
    payload = message(size)
    frames = encode(7, payload, max_frame)
    assert all(len(f) <= max_frame for f in frames)
    r = Reassembler()
    out = [r.push(f) for f in frames]
    assert out[:-1] == [None] * (len(frames) - 1)
    assert out[-1] == payload
    assert json.loads(out[-1])["type"] == "section"


def test_small_message_is_one_frame():
    frames = encode(1, b'{"type":"hello"}', 244)
    assert len(frames) == 1
    assert frames[0][:HEADER] == bytes([0, 1, 0, 0, 0, 1])


def test_lost_frame_drops_only_that_message():
    r = Reassembler()
    first = encode(1, message(2000), 100)
    second = encode(2, message(10), 100)
    for f in first[:3] + first[4:]:  # frame 3 never arrives
        assert r.push(f) is None
    got = [r.push(f) for f in second]
    assert got[-1] == message(10)
    assert r.dropped == 1


def test_new_message_interrupts_a_partial_one():
    r = Reassembler()
    a = encode(1, message(1000), 100)
    b = encode(2, message(5), 100)
    r.push(a[0])
    assert [r.push(f) for f in b][-1] == message(5)
    assert r.dropped == 1


def test_msg_id_wraps():
    assert encode(0x10000 + 5, b"{}", 50)[0][:2] == bytes([0, 5])


def test_garbage_is_ignored():
    r = Reassembler()
    assert r.push(b"\x00\x01") is None
    assert r.push(bytes([0, 1, 0, 5, 0, 2]) + b"x") is None  # index >= count
    assert r.push(encode(3, b'{"ok":1}', 64)[0]) == b'{"ok":1}'
