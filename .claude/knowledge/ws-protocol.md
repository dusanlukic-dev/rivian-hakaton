# WebSocket protocol: car computer ⇄ phone / dashboard

> **Status: DRAFT v0.** This is the frontend's proposal from 2026-11-06. The backend wasn't in the repo yet.
> A teammate's agent described the planned endpoint as `ws://<IP>:8000/api/v1/ws`. It's in `backend/app/api/routes/live.py`,
> `backend/app/services/live.py` keeps the client set and pushes "trip events" with `send_json`, and `backend/run.py`
> prints the URL using the machine's LAN IP.
> **When the real backend lands:** diff its messages against this file. Then update this file and the client adapters
> (`frontend/mobile/src/protocol/`, `frontend/dashboard/src/protocol/`) in the same commit.

## Transport

- `ws://<car-ip>:8000/api/v1/ws`. JSON text frames. Each client opens one socket, and the server broadcasts to all clients.
- Health check (proposed): `GET http://<car-ip>:8000/api/v1/health` returns `{"status":"ok","service":"car-computer","protocol":0}`.
  The app's "Test connection" button and the optional LAN scan use it.
- No auth, because this is a LAN demo. The backend must bind `0.0.0.0`, not `127.0.0.1`, or the phone can't reach it.
- The server pushes `state` at a fixed rate: **target 10 Hz, at least 2 Hz**. State frames double as the heartbeat. If no frame arrives
  for **3 s**, clients show "connection lost", and the phone treats that as a warning, because a silent watchdog is unsafe.
- Clients reconnect forever with backoff 0.5 → 1 → 2 → 5 s, capped at 5 s.
- Every message has a `type` field. Server messages also carry `ts` (epoch ms, server clock).
  **Clients must ignore unknown `type`s and unknown fields**, so either side can add things without breaking the other.

## Server → client

### `state` (periodic, **required**: the only message the frontend strictly needs)

```json
{
  "type": "state",
  "ts": 1762437600123,
  "seq": 1532,
  "trip_id": "trip-42",
  "vehicle": { "speed_kmh": 72.4, "gps_speed_kmh": 71.8, "assist_mode": "hands_on", "gear": "D" },
  "metrics": {
    "phone_use": 0.91,
    "turned_around": 0.02,
    "hands_on_wheel": 1,
    "drowsiness": 0.12,
    "eyes_off_road": 0.4
  },
  "risk": { "score": 0.78, "level": 2, "reasons": ["phone_use"] }
}
```

- `metrics` may hold **any subset** of keys, because a CV model can be offline, and may hold **new keys**. Values are probabilities 0..1,
  except `hands_on_wheel`, which is an integer count 0..2. `null` means the model is running but has no estimate for this frame.
  The key registry and meanings are in `metrics-and-scoring.md`.
- `risk` may be omitted. Clients then compute a fallback level (`metrics-and-scoring.md` § Client fallback).
- `risk.level`: `0` ok · `1` notice · `2` warning · `3` critical. `risk.score` is 0..1.
- `risk.reasons` lists the metric keys (or short codes such as `"connection"`) that drive the level, strongest first.
- `vehicle.assist_mode` is one of `"off" | "hands_on" | "hands_free"`, and `vehicle.gear` is one of `"P" | "R" | "N" | "D"`. Both are optional.

### `welcome` (optional, sent once after connect)

```json
{ "type": "welcome", "ts": 1762437600000, "protocol": 0, "server": "car-computer", "trip_id": "trip-42", "tick_hz": 10 }
```

### `alert` / `alert_clear` (optional, edge-triggered)

Sent when the level rises or a new reason appears. The client derives the same thing from `state`, so these only add a custom message and an id.

```json
{ "type": "alert", "ts": 1762437601000, "id": "al-17", "level": 3, "reasons": ["drowsiness"], "message": "You seem drowsy. Take a break." }
{ "type": "alert_clear", "ts": 1762437609000, "id": "al-17" }
```

### `pong`

```json
{ "type": "pong", "t": 1762437600500, "ts": 1762437600510 }
```

## Client → server

| type | when | payload |
|---|---|---|
| `hello` | first message after open | `{"type":"hello","role":"phone"\|"dashboard"\|"sim","device":"Galaxy A54","app_version":"0.1.0"}` |
| `ping` | every 5 s | `{"type":"ping","t":<client epoch ms>}`; RTT = now − t when `pong` arrives |
| `ack` | driver taps "I'm focused" | `{"type":"ack","id":"al-17","ts":<client ms>}` (id optional) |
| `telemetry` | phone sensors (later) | `{"type":"telemetry","gps_speed_kmh":71.8,"lat":44.8,"lon":20.4,"accuracy_m":5,"app_state":"active"\|"background","screen_on":true}` |
| `sim` | dashboard sim panel / mock | `{"type":"sim","scenario":"texting"}` or `{"type":"sim","set":{"vehicle":{"speed_kmh":80},"metrics":{"phone_use":0.95}}}` |

The backend may ignore any of these. Only the mock server needs to understand `sim`.

## Versioning

`protocol` is an integer. A breaking change bumps it. This draft is `0`.

## Open questions for the backend teammate (mirrored in PROGRESS.md)

1. How close is the real "trip event" payload to `state` above? Field names, nesting, units (km/h or m/s)?
2. What's the tick rate? Is `risk` computed every frame, or only on change?
3. Are client messages (`hello`, `ack`, `telemetry`) read or ignored?
4. What's the health endpoint path? Does `run.py` bind `0.0.0.0`?
5. Who owns the simulated vehicle data (speed, GPS)? The backend, or the dashboard sim panel through `sim`?
