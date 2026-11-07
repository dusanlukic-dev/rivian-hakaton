# Networking: laptop ("car computer") ⇄ phone ⇄ dashboard

## Demo topology (no server, no DNS)

```
 ┌──────────────── Galaxy A54 ───────────────────────────┐
 │ mobile hotspot (phone = gateway, randomized subnet)   │
 │ Safety Reviewer app ── ws://<laptop-ip>:8000/api/v1/ws ┼──┐ Wi-Fi (hotspot LAN)
 └───────────────────────────────────────────────────────┘  │
 ┌──────────────── laptop = car computer ─────────────────┐ │
 │ backend  python run.py → 0.0.0.0:8000 (prints its IP) ◄┼─┘
 │ camera models / simulator → POST 127.0.0.1:8000/api/v1/telemetry
 │ dashboard (browser) → ws://localhost:8000/api/v1/ws    │
 └────────────────────────────────────────────────────────┘
```

- The phone hosts the hotspot and the laptop joins it. Apps on the hotspot phone can reach hotspot clients, as verified on 2026-11-06:
  `phone → 10.190.62.27:8000/api/v1/health` returned 200.
- The app needs the **laptop's** IP. `backend/run.py` prints it, or use `ipconfig` → adapter `WiFi` → IPv4. **It changes with every hotspot
  session**, so it's never hardcoded. API.md §2 requires a settings screen with an address field (saved in AsyncStorage) and a
  "Test connection" button that calls `GET /health`.
- Any phone works the same way: join the network, enter the IP. Several clients can connect at once, and the backend broadcasts to all.

## Ports

| port | what | bind / notes |
|---|---|---|
| 8000 | FastAPI backend: REST `/api/v1/*`, WS `/api/v1/ws`, Swagger `/docs` | `0.0.0.0` (`run.py`) |
| 8081 | Metro bundler (mobile dev only) | over USB via `adb reverse` (automatic with `expo run:android`) |
| 5173 | dashboard Vite dev server | `localhost` by default. `npm run dev -- --host` exposes it on the LAN |
| 5433 | Postgres for the trip recording (`backend/scripts/services.ps1`) | `127.0.0.1` only. 5432 is taken by a system PostgreSQL 18 service on this laptop |
| 9000 / 9001 | RustFS S3 API / web console (clips) | `127.0.0.1` only. The phone gets clips through the backend (`/api/v1/media/...` on 8000), so no firewall rule is needed |

## Development without hotspot hassle: USB + adb reverse

`adb reverse tcp:8000 tcp:8000` (plus `tcp:8081` for Metro) makes `localhost:8000` **on the phone** reach the laptop over USB, with no IP,
firewall or Wi-Fi involved. `npm run adb:reverse` in `frontend/mobile` sets both. The mappings reset on replug or an adb restart. Verified 2026-11-06.

## Windows firewall: state on Matija's laptop (2026-11-06)

The hotspot network is classed as **Public**.

| program | inbound rule on Public | effect |
|---|---|---|
| `…\Python\pythoncore-3.13-64\python.exe` (the backend venv's base interpreter) | **Allow** (accepted at the first `run.py`) | phone → backend over the hotspot works ✅ |
| `…\nvm\v26.13.0\node.exe` | **Block** (an earlier prompt was denied) | Metro over Wi-Fi and a LAN-exposed dashboard are **blocked** for other devices. USB/`adb reverse` and `localhost` are unaffected |

Block rules beat allow rules. To unblock node (only needed for Metro over Wi-Fi or opening the dashboard from another device), run in an
**elevated** PowerShell, then accept the prompt on the next start:
```powershell
Get-NetFirewallRule -Direction Inbound | Where-Object { $_.DisplayName -eq 'node.exe' -and $_.Action -eq 'Block' } | Remove-NetFirewallRule
```
If a different Python ever runs the backend, Windows prompts again. Tick Public too, or add a port rule (from `backend/README.md`):
`New-NetFirewallRule -DisplayName "Safety API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow`.
Multiple adapters exist (VirtualBox `192.168.56.1`, Hyper-V `192.168.16.1`), so always use the `WiFi` adapter's IP. `run.py` picks it correctly.

## Android gotchas (phone)

- **Cleartext:** release builds block `http://`/`ws://` to non-localhost hosts by default. We set
  `expo-build-properties.android.usesCleartextTraffic = true`, and debug builds already allow it.
- `toybox nc` tests through `adb reverse`: keep stdin open (`(printf …; sleep 2) | toybox nc …`), because the adb tunnel drops the
  stream on a TCP half-close.
- If the phone joins some other Wi-Fi instead of hosting, the laptop must be on the same Wi-Fi. Venue Wi-Fi often has client isolation,
  so **prefer the hotspot**.

## Ports that can't break the demo (2026-11-07, D50)

- Windows (Hyper-V, WSL, Docker's WinNAT) reserves TCP port ranges at boot and they move between reboots: on this laptop
  8685–8884 (`netsh interface ipv4 show excludedportrange protocol=tcp`). A port inside one fails with WinError 10013. Our ports
  (8000, 8001, 5173, 5174, 8081) are outside today; `tools/reserve-ports.ps1` (admin, once, demo stopped) makes them administered
  exclusions (marked `*`) so they stay ours after any reboot. Not run yet: it needs the user's elevation.
- `backend/run.py` checks its port before uvicorn: "taken by PID n (name)" or "reserved by Windows" instead of a raw bind error.
- `demo.ps1` always starts clean: closes its own earlier `demo:` windows and a backend from this repo still holding 8000/8001
  (never anything else), refuses a reserved port up front, keeps the user's running Bluetooth gateway, and opens
  `demo: telefon USB` which re-applies `adb reverse` 8081/8000/8001 within 3 s whenever it's gone (cable replugged,
  `adb kill-server`, phone re-authorized). `demo.ps1 -Stop` stops all of it.
- The video-sim (`frontend/video-sim`, port 5174) streams into the same `WS /camera/ws` as `camera_stream.py` /
  `klip_po_voznji.py`: one camera at a time (a second is refused with HTTP 403), so close the per-trip camera window first.

## Docker stack (2026-11-07, D52)

- Ports published by Docker Desktop are served on the host by `com.docker.backend.exe` on all interfaces (plus `wslrelay` on ::1).
  Docker Desktop's install adds the inbound rule **"Docker Desktop Backend"** (Public, Allow), so the phone on the hotspot reaches
  8000/8001/5173 without a rule of ours (verified via the LAN IP). `start.ps1` warns if that rule is missing.
- Inside Docker the parts find each other by service name (`coordinator:8000`, `server:8001`, `postgres:5432`, `rustfs:9000`).
  Postgres and RustFS have no host ports in this stack.
