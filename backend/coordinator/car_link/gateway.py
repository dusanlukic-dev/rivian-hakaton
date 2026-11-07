"""Car link gateway: Bluetooth LE <-> the coordinator on this computer (docs/BLUETOOTH.md).

The phone talks to the car over Bluetooth instead of Wi-Fi. This process advertises the car's GATT service, forwards
every message of the coordinator's live WebSocket to the subscribed phones (framed notifications on `rx`), and turns
the phones' requests (frames written to `tx`) into REST calls on the coordinator. The coordinator itself doesn't
change and knows nothing about Bluetooth; if this process dies, scoring and the car screen keep running.

    python car_link/gateway.py                                   # coordinator on http://127.0.0.1:8000/api/v1
    python car_link/gateway.py --name "Rivian R1S" -v            # name shown in the app, log every message
    python car_link/gateway.py --server-url https://xyz.ngrok.app/api/v1   # server address offered to the phone

Windows only (WinRT GattServiceProvider). Turns Bluetooth on if it's off; the adapter must support the peripheral
role (`IsPeripheralRoleSupported`). Requirements: car_link/requirements.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import socket
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect as ws_connect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from framing import HEADER, Reassembler, encode  # noqa: E402

HEADER_ROOM = HEADER + 14  # smallest sensible frame (the default ATT MTU of 23 gives 20 B)

SERVICE = uuid.UUID("5afe0000-7a1e-4c55-8d2b-9c1e0f3a6b01")
RX = uuid.UUID("5afe0001-7a1e-4c55-8d2b-9c1e0f3a6b01")  # car -> phone, notify
TX = uuid.UUID("5afe0002-7a1e-4c55-8d2b-9c1e0f3a6b01")  # phone -> car, write
PROTOCOL = 1
DEFAULT_FRAME = 20  # ATT MTU 23 - 3: until the phone negotiates a bigger MTU
# Frames never exceed one radio packet (251-byte LE data length: 244 B of notification payload), even when the
# phone negotiated MTU 517: larger notifications need L2CAP segmentation, a weak spot of Windows Bluetooth drivers.
MAX_FRAME = 244
PING_S = 2.0  # heartbeat; the phone reconnects after ~7 s of silence
OUTBOX_LIMIT = 200  # messages waiting for Bluetooth; ~1 min of live data

# The [K] routes the phone may call over Bluetooth (docs/BLUETOOTH.md). Everything else is 404.
ROUTES: list[tuple[str, re.Pattern[str]]] = [
    ("GET", re.compile(r"/health")),
    ("POST", re.compile(r"/trips")),
    ("POST", re.compile(r"/trips/[^/]+/end")),
    ("GET", re.compile(r"/trips/[^/]+")),
    ("GET", re.compile(r"/speed")),
    ("POST", re.compile(r"/speed")),
    ("GET", re.compile(r"/coordinator/status")),
]

ADVERTISEMENT_STATUS = {0: "created", 1: "stopped", 2: "started", 3: "aborted", 4: "started without all data"}

log = logging.getLogger("car_link")


def allowed(method: str, path: str) -> bool:
    return any(method == m and pattern.fullmatch(path) for m, pattern in ROUTES)


def lan_ip() -> str:
    """IP of the interface with the default route (what the phone sees on the hotspot); same trick as run.py."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))  # UDP connect sends nothing, it only picks the interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def short(device_id: str) -> str:
    """'BluetoothLE#BluetoothLE00:11:..-aa:bb:cc:dd:ee:ff' -> 'aa:bb:cc:dd:ee:ff'."""
    return device_id.rsplit("-", 1)[-1] if "-" in device_id else device_id


# ---- Bluetooth (WinRT) --------------------------------------------------------------------------------------------


async def ensure_radio_on() -> None:
    from winrt.windows.devices.radios import Radio, RadioAccessStatus, RadioKind, RadioState

    radios = [r for r in await Radio.get_radios_async() if r.kind == RadioKind.BLUETOOTH]
    if not radios:
        raise SystemExit("This computer has no Bluetooth radio.")
    for radio in radios:
        if radio.state == RadioState.ON:
            continue
        log.info("Bluetooth is off, turning it on")
        if await Radio.request_access_async() != RadioAccessStatus.ALLOWED:
            raise SystemExit("Windows refused to turn Bluetooth on. Turn it on in Settings > Bluetooth and start again.")
        await radio.set_state_async(RadioState.ON)
        await asyncio.sleep(2)  # the stack needs a moment before a GATT server can start


class Peripheral:
    """The car's GATT server: `rx` notifies the phones, `tx` receives their frames.

    WinRT calls the handlers below on its own thread pool; they only copy the data and hand it to the asyncio loop.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_frame: Callable[[str, bytes], None],
        on_subscribers: Callable[[list[tuple[str, int]]], None],
    ) -> None:
        self._loop = loop
        self._on_frame = on_frame
        self._on_subscribers = on_subscribers
        self._provider: Any = None
        self._rx: Any = None
        self._tx: Any = None
        self._tokens: list[tuple[Any, str, Any]] = []

    async def start(self) -> None:
        from winrt.windows.devices.bluetooth import BluetoothError
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattCharacteristicProperties,
            GattLocalCharacteristicParameters,
            GattProtectionLevel,
            GattServiceProvider,
            GattServiceProviderAdvertisingParameters,
        )

        await ensure_radio_on()
        result = await GattServiceProvider.create_async(SERVICE)
        if result.error != BluetoothError.SUCCESS:
            raise SystemExit(
                f"Can't create the Bluetooth service ({BluetoothError(result.error).name}). "
                "Is another gateway already running? Does the adapter support the peripheral role?"
            )
        self._provider = result.service_provider

        rx_params = GattLocalCharacteristicParameters()
        # Indications, not notifications: the phone acknowledges every frame. Plain notifications got lost while the
        # phone was writing a request (the reply to "end trip" never arrived), and one lost frame kills a message.
        rx_params.characteristic_properties = GattCharacteristicProperties.INDICATE
        rx_params.read_protection_level = GattProtectionLevel.PLAIN
        rx_params.user_description = "car to phone"
        self._rx = (await self._provider.service.create_characteristic_async(RX, rx_params)).characteristic

        tx_params = GattLocalCharacteristicParameters()
        tx_params.characteristic_properties = (
            GattCharacteristicProperties.WRITE | GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE
        )
        tx_params.write_protection_level = GattProtectionLevel.PLAIN
        tx_params.user_description = "phone to car"
        self._tx = (await self._provider.service.create_characteristic_async(TX, tx_params)).characteristic

        self._tokens = [
            (self._rx, "subscribed_clients_changed", self._rx.add_subscribed_clients_changed(self._subscribers_changed)),
            (self._tx, "write_requested", self._tx.add_write_requested(self._write_requested)),
            (self._provider, "advertisement_status_changed",
             self._provider.add_advertisement_status_changed(self._status_changed)),
        ]

        params = GattServiceProviderAdvertisingParameters()
        params.is_connectable = True
        params.is_discoverable = True
        self._provider.start_advertising_with_parameters(params)

    def stop(self) -> None:
        if self._provider is None:
            return
        for obj, event, token in self._tokens:
            try:
                getattr(obj, f"remove_{event}")(token)
            except Exception:  # noqa: BLE001 - shutting down anyway
                pass
        try:
            self._provider.stop_advertising()
        except Exception:  # noqa: BLE001
            pass
        self._provider = None

    def max_frame(self) -> int:
        """Largest notification every subscribed phone accepts (MTU - 3, read live: the MTU can change)."""
        sizes = [c.max_notification_size for c in self._clients() if c.max_notification_size]
        return min(sizes) if sizes else DEFAULT_FRAME

    def has_subscribers(self) -> bool:
        return bool(self._clients())

    async def notify(self, frame: bytes) -> list[str]:
        """Sends one frame to every subscribed phone; returns what went wrong (empty = every phone got it whole)."""
        from winrt.windows.storage.streams import DataWriter

        writer = DataWriter()
        writer.write_bytes(frame)
        results = await self._rx.notify_value_async(writer.detach_buffer())
        problems = []
        for r in results or []:
            if int(r.status) != 0:
                problems.append(f"status {int(r.status)}")
            elif r.bytes_sent != len(frame):
                problems.append(f"sent {r.bytes_sent} of {len(frame)} B")
        return problems

    def _clients(self) -> list[Any]:
        if self._rx is None:
            return []
        clients = self._rx.subscribed_clients
        return list(clients) if clients is not None else []

    # -- WinRT thread pool --

    def _subscribers_changed(self, sender: Any, _args: Any) -> None:
        clients = list(sender.subscribed_clients or [])
        info = [(c.session.device_id.id, c.max_notification_size) for c in clients]
        self._loop.call_soon_threadsafe(self._on_subscribers, info)

    def _write_requested(self, _sender: Any, args: Any) -> None:
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattWriteOption
        from winrt.windows.storage.streams import DataReader

        deferral = args.get_deferral()
        data, device = b"", ""
        try:
            device = args.session.device_id.id
            waiter = asyncio.new_event_loop()
            try:
                request = waiter.run_until_complete(_await(args.get_request_async()))
            finally:
                waiter.close()
            reader = DataReader.from_buffer(request.value)
            data = bytes(reader.read_byte() for _ in range(reader.unconsumed_buffer_length))
            if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                request.respond()
        except Exception:  # noqa: BLE001 - a bad write must never kill the WinRT callback thread
            log.exception("reading a write from the phone failed")
        finally:
            deferral.complete()
        if data:
            self._loop.call_soon_threadsafe(self._on_frame, device, data)

    def _status_changed(self, _sender: Any, args: Any) -> None:
        status = ADVERTISEMENT_STATUS.get(int(args.status), str(args.status))
        error = int(args.error)
        self._loop.call_soon_threadsafe(
            log.info, "advertising %s%s", status, f" (Bluetooth error {error})" if error else ""
        )


async def _await(operation: Any) -> Any:
    return await operation


# ---- the bridge ---------------------------------------------------------------------------------------------------


class Bridge:
    def __init__(
        self, coordinator: str, car_name: str, server_url: str | None, verbose: bool, max_frame: int = MAX_FRAME
    ) -> None:
        self.max_frame = max_frame
        self.base = coordinator.rstrip("/")
        self.ws_url = re.sub(r"^http", "ws", self.base) + "/ws"
        self.car_name = car_name
        self.server_url = server_url
        self.verbose = verbose
        self.coordinator_up = False
        self.last_state: bytes | None = None  # last `state` of a running trip, replayed to a phone that says hello
        # (kind, payload) waiting for Bluetooth. A newer `state` or `ping` replaces a queued one (see enqueue).
        self.outbox: deque[tuple[str, bytes]] = deque()
        self.wakeup = asyncio.Event()
        self.reassemblers: dict[str, Reassembler] = {}
        self.subscribers: dict[str, int] = {}
        self.msg_id = 0
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self.http = httpx.AsyncClient(base_url=self.base, timeout=httpx.Timeout(12.0, connect=3.0))
        self.peripheral: Peripheral | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        self.peripheral = Peripheral(asyncio.get_running_loop(), self.on_frame, self.on_subscribers)
        await self.peripheral.start()
        log.info("car %r on Bluetooth, coordinator %s, server for the phone %s", self.car_name, self.base,
                 self.server_url or "not offered")
        try:
            await asyncio.gather(self.follow_coordinator(), self.send_loop(), self.heartbeat(), self.report())
        finally:
            self.peripheral.stop()
            await self.http.aclose()

    # -- coordinator -> phones --

    async def follow_coordinator(self) -> None:
        delay = 0.5
        while True:
            try:
                async with ws_connect(self.ws_url, open_timeout=5, ping_interval=20, max_size=2**22) as ws:
                    self.set_coordinator(True)
                    delay = 0.5
                    async for raw in ws:
                        if isinstance(raw, str):
                            self.on_live(raw.encode())
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - refused, reset, handshake errors: retry
                if self.coordinator_up or self.verbose:
                    log.info("coordinator link: %s", e.__class__.__name__)
            self.set_coordinator(False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5.0)

    def set_coordinator(self, up: bool) -> None:
        if up == self.coordinator_up:
            return
        self.coordinator_up = up
        log.info("coordinator %s", "connected" if up else "not answering")
        if not up:
            self.last_state = None
        self.send_hello()

    def on_live(self, raw: bytes) -> None:
        try:
            message = json.loads(raw)
            kind, data = message.get("type"), message.get("data")
        except (ValueError, AttributeError):
            return
        if kind in ("state", "trip_started"):
            active = isinstance(data, dict) and data.get("status") == "active"
            # trip_started is replayed as a plain state: the app must not clear its sections on a reconnect
            self.last_state = json.dumps({"type": "state", "data": data}).encode() if active else None
        elif kind == "trip_ended":
            self.last_state = None
        self.enqueue(raw, kind if isinstance(kind, str) else "")

    def enqueue(self, payload: bytes, kind: str = "") -> None:
        if self.peripheral is None or not self.peripheral.has_subscribers():
            return  # nobody listens: live data is only worth something now
        if kind in ("state", "ping"):
            # Superseded: with indications (every frame acknowledged) Bluetooth can fall behind the coordinator's
            # 2 states/s; only the newest state matters, so the queue never builds up and alerts stay current.
            # Responses, sections and events (trip_started, emergency, trip_ended, hello) always go, in order.
            self.outbox = deque(item for item in self.outbox if item[0] != kind)
        if len(self.outbox) >= OUTBOX_LIMIT:
            self.dropped += 1
            if self.dropped % 50 == 1:
                log.warning("phone too slow, dropped %d messages", self.dropped)
            return
        self.outbox.append((kind, payload))
        self.wakeup.set()

    async def send_loop(self) -> None:
        """One message at a time, so frames of two messages never interleave (the phone would drop both)."""
        while True:
            while not self.outbox:
                self.wakeup.clear()
                await self.wakeup.wait()
            await self.send(self.outbox.popleft()[1])

    async def send(self, payload: bytes) -> None:
        """Frames one message and notifies it, frame by frame (each notify is awaited)."""
        assert self.peripheral is not None
        if self.peripheral.has_subscribers():
            self.msg_id = (self.msg_id + 1) & 0xFFFF
            frames = encode(self.msg_id, payload, min(self.max_frame, self.peripheral.max_frame()))
            started = time.monotonic()
            failed: list[str] = []
            for frame in frames:
                try:
                    failed = await self.peripheral.notify(frame)
                except Exception as e:  # noqa: BLE001 - the phone left mid-message
                    failed = [f"error {e}"]
                if failed:
                    break
            self.sent += 1
            if failed:
                self.failed += 1
                log.info("message %d (%d B, %d frames) not delivered, status %s", self.msg_id, len(payload),
                         len(frames), failed)
            elif self.verbose:
                log.info("sent message %d: %d B in %d frames, %.0f ms", self.msg_id, len(payload), len(frames),
                         (time.monotonic() - started) * 1000)

    async def heartbeat(self) -> None:
        """A tiny `ping` every 2 s: the phone treats a silent link as dead and reconnects (docs/BLUETOOTH.md).
        Needed because Windows keeps the radio link up when this process restarts, and Android doesn't always
        report a drop (e.g. Bluetooth switched off and on), so neither side would notice otherwise."""
        ping = json.dumps({"type": "ping"}).encode()
        while True:
            await asyncio.sleep(PING_S)
            if not self.outbox:
                self.enqueue(ping, "ping")

    async def report(self) -> None:
        """A line every 10 s while a phone listens: how the Bluetooth side keeps up."""
        last = (0, 0)
        while True:
            await asyncio.sleep(10)
            if self.peripheral is None or not self.peripheral.has_subscribers():
                continue
            now = (self.sent, self.failed)
            if now != last:
                log.info("to phones: %d sent, %d failed, %d dropped, %d waiting", self.sent, self.failed,
                         self.dropped, len(self.outbox))
                last = now

    def send_hello(self) -> None:
        hello = {
            "type": "hello",
            "data": {
                "protocol": PROTOCOL,
                "car": self.car_name,
                "coordinator": self.coordinator_up,
                "server_url": self.server_url,
            },
        }
        self.enqueue(json.dumps(hello).encode(), "hello")

    # -- phones -> coordinator --

    def on_subscribers(self, clients: list[tuple[str, int]]) -> None:
        now = dict(clients)
        for device, size in now.items():
            if device not in self.subscribers:
                log.info("phone %s connected (frames up to %d B)", short(device), size)
        for device in list(self.subscribers):
            if device not in now:
                log.info("phone %s left", short(device))
                self.reassemblers.pop(device, None)
        self.subscribers = now

    def on_frame(self, device: str, frame: bytes) -> None:
        payload = self.reassemblers.setdefault(device, Reassembler()).push(frame)
        if payload is None:
            return
        try:
            message = json.loads(payload)
        except ValueError:
            log.warning("phone %s sent something that isn't JSON", short(device))
            return
        kind = message.get("type") if isinstance(message, dict) else None
        if kind == "hello":
            log.info("phone %s: hello from %s %s", short(device), message.get("app"), message.get("version"))
            self.send_hello()
            if self.last_state is not None:
                self.enqueue(self.last_state, "state")
        elif kind == "request":
            task = asyncio.create_task(self.handle_request(message))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        elif self.verbose:
            log.info("phone %s: ignored %r", short(device), kind)

    async def handle_request(self, message: dict[str, Any]) -> None:
        rid = message.get("id")
        method = str(message.get("method", "GET")).upper()
        path = str(message.get("path", ""))
        token = message.get("token")
        body = message.get("body")
        started = time.monotonic()
        if not allowed(method, path):
            status, answer = 404, {"detail": f"{method} {path} is not available over Bluetooth"}
        else:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            try:
                if body is None:
                    response = await self.http.request(method, path, headers=headers)
                else:
                    response = await self.http.request(method, path, headers=headers, json=body)
                status = response.status_code
                try:
                    answer = response.json()
                except ValueError:
                    answer = {"detail": response.text[:300]}
            except httpx.HTTPError:
                status, answer = 0, {"detail": "The car computer doesn't answer."}
        log.info("%s %s -> %s (%d ms)", method, path, status, (time.monotonic() - started) * 1000)
        self.enqueue(json.dumps({"type": "response", "id": rid, "status": status, "body": answer}).encode(), "response")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--coordinator", default="http://127.0.0.1:8000/api/v1", help="the coordinator's API base")
    parser.add_argument("--server-url", default=None,
                        help="server address offered to the phone (default http://<this laptop's LAN IP>:8001/api/v1)")
    parser.add_argument("--name", default=socket.gethostname(), help="car name shown in the app")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every message")
    parser.add_argument("--max-frame", type=int, default=MAX_FRAME,
                        help=f"largest frame in bytes (default {MAX_FRAME}: one radio packet)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s car_link: %(message)s", datefmt="%H:%M:%S")
    if sys.platform != "win32":
        raise SystemExit("The car link gateway needs Windows (WinRT Bluetooth).")
    server_url = args.server_url or f"http://{lan_ip()}:8001/api/v1"
    try:
        asyncio.run(Bridge(args.coordinator, args.name, server_url, args.verbose, max(HEADER_ROOM, args.max_frame)).run())
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
