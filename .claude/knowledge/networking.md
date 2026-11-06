# Networking: laptop ("car computer") ⇄ phone ⇄ dashboard

## Demo topology

```
 ┌──────────────── Galaxy A54 ─────────────────┐
 │  Mobile hotspot (phone = gateway)           │
 │  Driver Alert app ── ws://<laptop-ip>:8000 ─┼──┐
 └─────────────────────────────────────────────┘  │  Wi-Fi (hotspot LAN)
 ┌──────────────── Laptop = car computer ───────┐ │
 │  FastAPI backend  0.0.0.0:8000  /api/v1/ws ◄─┼─┘
 │  CV models (or mocks) → backend              │
 │  Dashboard (browser) ── ws://localhost:8000 ─┤
 └──────────────────────────────────────────────┘
```

- The phone hosts the hotspot and the laptop joins it. Apps on the hotspot phone *can* reach hotspot clients
  (Android routes the tether subnet through its `local_network` table for all apps).
- The app needs the **laptop's** IP on the hotspot network: `ipconfig` → "Wireless LAN adapter Wi-Fi" → IPv4.
  Recent Android/Samsung builds randomize the hotspot subnet, so **never hardcode the IP**.
- Any other phone works the same way: join the same network, enter the IP. A second phone on the hotspot is also fine (passenger device).

## Ports

| port | what | bind |
|---|---|---|
| 8000 | FastAPI backend (or the mock server) — HTTP + WS `/api/v1/ws` | `0.0.0.0` (`uvicorn --host 0.0.0.0`) |
| 8081 | Metro bundler (mobile dev only) | expo default |
| 5173 | Dashboard Vite dev server | `npm run dev -- --host` to expose on the LAN |

## How the app finds the server (settings screen, planned)

1. **Manual**: host, port and path fields (default `localhost` · `8000` · `/api/v1/ws`) with a "Test" button that calls the health endpoint.
   Persisted with AsyncStorage, and the last few hosts are remembered.
2. **QR**: the dashboard shows a QR code of the full `ws://…` URL, and the app scans it with expo-camera.
3. **LAN scan** (optional): take the phone's IP from expo-network and probe `/24:8000/api/v1/health` with short timeouts.
   On the hotspot phone itself, expo-network may report the cellular IP, so this is unreliable there. Treat it as a bonus.

## Development without hotspot hassle: USB + adb reverse

`adb reverse tcp:8000 tcp:8000` (and `tcp:8081` for Metro; `expo run:android` already does 8081) makes `localhost:8000`
**on the phone** reach the laptop over USB. No IP, firewall or Wi-Fi needed. `npm run adb:reverse` in `frontend/mobile` sets both.
Reverse mappings reset when the cable or adb server restarts.

## Windows gotchas (laptop)

- **Firewall**: when the laptop joins a phone hotspot, Windows usually marks it *Public*, which blocks inbound connections.
  Run once in an **elevated** PowerShell:
  ```powershell
  New-NetFirewallRule -DisplayName "Hackathon backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
  New-NetFirewallRule -DisplayName "Hackathon Metro 8081"   -Direction Inbound -Protocol TCP -LocalPort 8081 -Action Allow -Profile Any
  # or mark the hotspot network Private (alias is "WiFi" on Matija's laptop, check with Get-NetConnectionProfile):
  Set-NetConnectionProfile -InterfaceAlias "WiFi" -NetworkCategory Private
  ```
  The first Python run may instead pop a firewall dialog: tick both Private and Public.
- Bind the backend to `0.0.0.0`. `127.0.0.1` is reachable only from the laptop.

## Android gotchas (phone)

- **Cleartext**: release builds block `http://`/`ws://` to non-localhost hosts by default. We set
  `expo-build-properties.android.usesCleartextTraffic = true`, and debug builds already allow it.
- Mobile data stays on while hosting a hotspot, so the laptop gets internet through the phone. That's fine.
- If the phone joins some other Wi-Fi instead of hosting, the laptop must be on that same Wi-Fi. Client isolation on venue
  Wi-Fi often blocks device-to-device traffic, so **prefer the hotspot**.
