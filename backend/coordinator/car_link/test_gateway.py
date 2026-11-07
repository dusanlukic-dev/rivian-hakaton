"""The car link gateway's protocol (docs/BLUETOOTH.md) without Bluetooth: a fake peripheral stands in for WinRT and
an httpx mock for the coordinator. What a phone would reassemble from the notified frames is checked byte for byte."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from framing import Reassembler, encode  # noqa: E402
from gateway import MAX_FRAME, Bridge, allowed  # noqa: E402


class FakePeripheral:
    def __init__(self, subscribed: bool = True, frame: int = 514) -> None:
        self.subscribed = subscribed
        self.frame = frame
        self.frames: list[bytes] = []

    def has_subscribers(self) -> bool:
        return self.subscribed

    def max_frame(self) -> int:
        return self.frame

    async def notify(self, frame: bytes) -> list[str]:
        self.frames.append(frame)
        return []


def make_bridge(handler=None) -> tuple[Bridge, FakePeripheral]:
    bridge = Bridge("http://car.test/api/v1", "Test car", "http://10.0.0.5:8001/api/v1", verbose=False)
    peripheral = FakePeripheral()
    bridge.peripheral = peripheral  # type: ignore[assignment]
    if handler is not None:
        bridge.http = httpx.AsyncClient(base_url=bridge.base, transport=httpx.MockTransport(handler))
    return bridge, peripheral


async def drain(bridge: Bridge) -> list[dict]:
    """Sends everything queued and returns the messages a phone would get."""
    while not bridge.outbox.empty():
        await bridge.send(bridge.outbox.get_nowait())
    phone, out = Reassembler(), []
    for frame in bridge.peripheral.frames:  # type: ignore[union-attr]
        payload = phone.push(frame)
        if payload is not None:
            out.append(json.loads(payload))
    return out


def phone_writes(bridge: Bridge, message: dict, device: str = "phone-1") -> None:
    for frame in encode(9, json.dumps(message).encode(), 100):
        bridge.on_frame(device, frame)


def test_frames_stay_within_one_radio_packet():
    async def run():
        bridge, peripheral = make_bridge()
        bridge.enqueue(json.dumps({"type": "section", "data": {"pad": "x" * 3000}}).encode())
        got = await drain(bridge)
        assert all(len(f) <= MAX_FRAME for f in peripheral.frames)
        assert len(peripheral.frames) > 1
        assert got[0]["data"]["pad"] == "x" * 3000

    asyncio.run(run())


def test_hello_answers_and_replays_the_running_trip():
    async def run():
        bridge, _ = make_bridge()
        bridge.coordinator_up = True
        trip = {"trip_id": "t1", "status": "active", "score": 88.0}
        bridge.on_live(json.dumps({"type": "trip_started", "data": trip}).encode())
        await drain(bridge)
        bridge.peripheral.frames.clear()  # type: ignore[union-attr]

        phone_writes(bridge, {"type": "hello", "app": "mobile", "version": "1"})
        got = await drain(bridge)
        assert got[0]["type"] == "hello"
        assert got[0]["data"] == {"protocol": 1, "car": "Test car", "coordinator": True,
                                  "server_url": "http://10.0.0.5:8001/api/v1"}
        # replayed as a plain state, so the app doesn't reset its sections on a reconnect
        assert got[1] == {"type": "state", "data": trip}

    asyncio.run(run())


def test_trip_end_clears_the_replay():
    async def run():
        bridge, _ = make_bridge()
        bridge.on_live(json.dumps({"type": "state", "data": {"trip_id": "t1", "status": "active"}}).encode())
        bridge.on_live(json.dumps({"type": "trip_ended", "data": {"trip_id": "t1"}}).encode())
        await drain(bridge)
        bridge.peripheral.frames.clear()  # type: ignore[union-attr]
        phone_writes(bridge, {"type": "hello"})
        assert [m["type"] for m in await drain(bridge)] == ["hello"]

    asyncio.run(run())


def test_request_goes_to_the_coordinator_with_the_token():
    seen = {}

    def coordinator(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"trip_id": "t9", "status": "active"})

    async def run():
        bridge, _ = make_bridge(coordinator)
        phone_writes(bridge, {"type": "request", "id": "r1", "method": "POST", "path": "/trips", "token": "tok",
                              "body": {"driver_id": "ana"}})
        await asyncio.sleep(0.05)  # the request runs as its own task
        got = await drain(bridge)
        assert seen == {"url": "http://car.test/api/v1/trips", "auth": "Bearer tok", "body": {"driver_id": "ana"}}
        assert got == [{"type": "response", "id": "r1", "status": 201, "body": {"trip_id": "t9", "status": "active"}}]

    asyncio.run(run())


def test_routes_outside_the_list_never_reach_the_coordinator():
    calls = []

    async def run():
        bridge, _ = make_bridge(lambda r: calls.append(r) or httpx.Response(200, json={}))
        phone_writes(bridge, {"type": "request", "id": "r2", "method": "POST", "path": "/telemetry", "body": {}})
        await asyncio.sleep(0.05)
        got = await drain(bridge)
        assert calls == []
        assert got[0]["status"] == 404 and got[0]["id"] == "r2"

    asyncio.run(run())
    assert allowed("POST", "/trips/abc/end") and allowed("GET", "/trips/abc")
    assert not allowed("GET", "/trips") and not allowed("DELETE", "/trips/abc") and not allowed("GET", "/media/x")


def test_coordinator_down_is_status_zero():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async def run():
        bridge, _ = make_bridge(down)
        phone_writes(bridge, {"type": "request", "id": "r3", "method": "GET", "path": "/health"})
        await asyncio.sleep(0.05)
        got = await drain(bridge)
        assert got[0]["status"] == 0 and got[0]["id"] == "r3"

    asyncio.run(run())


def test_nothing_is_queued_without_a_phone():
    bridge, peripheral = make_bridge()
    peripheral.subscribed = False
    bridge.on_live(json.dumps({"type": "state", "data": {"status": "active"}}).encode())
    assert bridge.outbox.empty()
    assert bridge.last_state is not None  # still remembered for the next phone
