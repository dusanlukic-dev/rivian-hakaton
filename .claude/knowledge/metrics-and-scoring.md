# Metrics, scoring and alert levels

The CV team works manually and slowly, so **everything here is a best guess** and the frontend runs on mocked data until real
output exists. The backend owns the real scoring. This file is the shared reference for the mock server, the client fallback and
the pitch. Update it when the CV team or backend changes something.

## CV signals (confirmed by the CV team, 2026-11-06)

| key | meaning | value | expected quality | notes |
|---|---|---|---|---|
| `phone_use` | driver holds or looks at a phone | prob 0..1 | good | object detection (phone class) + hand/face proximity. Strongest, most demo-able signal |
| `turned_around` | torso/head rotated toward the rear seats | prob 0..1 | good | pose estimation (shoulder/head yaw). Rare but severe |
| `hands_on_wheel` | number of hands on the wheel | int 0..2 | noisy (occlusion) | in `hands_on` assist mode, ≥1 is required and 2 is ideal |
| `drowsiness` | eye closure (PERCLOS), yawning, head nodding | prob 0..1 | medium, slow-moving | integrate over seconds, never react to a single frame |
| `eyes_off_road` | gaze not on the road ahead | prob 0..1 | **poor** ("can't be proven exactly") | low weight, needs persistence ≥2 s before it counts |

The app must **react to any single metric**, because frames can carry only a subset (see `ws-protocol.md`). Unknown keys get a
generic display: the raw key name and a 0..1 bar.

## Vehicle context (simulated / mocked)

`speed_kmh` (CAN), `gps_speed_kmh` (GPS; later maybe the phone's real GPS through `telemetry`), `assist_mode` (`off` · `hands_on` · `hands_free`), `gear` (`P/R/N/D`).
Gate: **no alerts below 5 km/h or in P**. This is a nice demo moment, because phone use while parked shows nothing.

## Reference scoring (the backend may replace it with a small NN)

Use a **noisy-OR**, not a weighted sum. With a sum, one strong signal (phone in hand) gets diluted by four calm ones. With a
noisy-OR, any single strong signal is enough, which is what "react on a single metric" needs.

```
b_phone  = phone_use                     w = 0.90   persistence 1.0 s
b_turn   = turned_around                 w = 0.95   persistence 0.5 s
b_hands  = {2: 0, 1: 0.35, 0: 1}[hands]  w = 0.60   persistence 3.0 s   (only in hands_on mode)
b_drowsy = drowsiness                    w = 0.85   persistence 2.0 s
b_eyes   = eyes_off_road                 w = 0.50   persistence 2.0 s   (NHTSA: glances off-road ≤ 2 s)

each b_i passes through a persistence filter (leaky integrator: ramps up while b_i > 0.5, decays otherwise)
risk_raw     = 1 − Π (1 − w_i · b_i)
speed_factor = clamp((speed_kmh − 5) / 45, 0, 1)        # 0 below 5 km/h, full at 50 km/h+
risk         = EMA(risk_raw · speed_factor, α ≈ 0.3 at 10 Hz)
level        = 3 if risk ≥ 0.85 · 2 if ≥ 0.60 · 1 if ≥ 0.35 · else 0
hysteresis   : drop a level only when risk < threshold − 0.10 for ≥ 1 s (prevents flicker)
```

## Client fallback (when a frame has no `risk`)

Per-metric rules with persistence. Take the max level, then apply the speed gate:

- `phone_use ≥ 0.7` for 1 s → 2, for 3 s → 3
- `turned_around ≥ 0.7` for 0.5 s → 3
- `hands_on_wheel == 0` for 3 s → 2, for 8 s → 3; `== 1` for 10 s → 1 (only in `hands_on` mode or when the mode is unknown)
- `drowsiness ≥ 0.6` → 2, `≥ 0.8` for 2 s → 3
- `eyes_off_road ≥ 0.7` for 2 s → 2, for 4 s → 3
- no frame for 3 s while the last known speed was > 5 km/h → 2 with reason `connection`

## What each level does

| level | phone, app in foreground ("Drive" screen, screen kept on) | phone, background / locked | web dashboard |
|---|---|---|---|
| 0 ok | calm status, live metric bars | ongoing "Drive mode" foreground-service notification | green state |
| 1 notice | amber banner + `chime` once | nothing (or a silent low-priority notification) | amber icon |
| 2 warning | red pulsing overlay (≤ 2 Hz), `alarm_warning` loop, vibration pattern, brightness up | heads-up notification on the **alarm** channel (sound + vibration); full-screen intent if locked | red edge flash + beeps |
| 3 critical | full-screen red pulse, `alarm_critical` loop, continuous vibration, TTS "Eyes on the road!", max brightness, big "I'm focused" button | full-screen intent wakes the screen and shows the app over the lock screen; insistent alarm | full red pulse + alarm |

- **Flashing must stay ≤ 3 Hz** (WCAG 2.3.1 photosensitive seizure threshold, and red is the worst colour for it). Use 2 Hz. The driver's safety beats demo drama.
- "I'm focused" (ack) mutes the sound for 10 s but keeps the visual, and sends `ack`.
- Clear: stop sound and vibration once the level has stayed < 2 for 1 s, then show a brief "Back on track" toast.
- Pitch line: if the driver is looking at the phone, the phone itself becomes the warning.

## Mock scenarios (mock server + dashboard sim panel)

| scenario | what happens | demonstrates |
|---|---|---|
| `calm` | all metrics low with jitter, 80 km/h, hands 2 | no false alarms, hysteresis |
| `phone_glance` | phone_use 0.9 for 1.5 s, then drops | short glance → notice/warning only |
| `texting` | phone_use 0.95 + eyes_off_road 0.8 sustained 6 s | escalation 1 → 2 → 3 |
| `turn_around` | turned_around 0.97 for 3 s | instant critical |
| `hands_off` | hands 2 → 1 (10 s) → 0 (8 s) | hands-on mode escalation |
| `drowsy` | drowsiness ramps 0.2 → 0.9 over 20 s | slow build-up, TTS "take a break" |
| `parked_phone` | speed 0, gear P, phone_use 0.95 | speed gate, no alert |
| `partial` | frames carry only `phone_use` | single-metric robustness |
| `dropout` | server stops sending for 5 s | connection-lost warning + reconnect |
