# Behaviours, score, levels, and what the frontend does with them

The backend owns all the logic: `backend/app/services/scoring.py` (score), `backend/app/services/alerts.py` (levels → car response),
with a summary in the root `CLAUDE.md`. This is the frontend cheat sheet. If the code and this file disagree, **the code wins**, so update this file.

## Behaviours (labels from the camera models, `POST /telemetry` ~2/s)

| label | UI text (EN) | weight (points/s) | notes |
|---|---|---|---|
| `looking_at_phone` | Looking at phone | 2.0 | the most demo-able signal |
| `looking_behind` | Looking behind | 2.0 | usually reported together with `turning_around`, so they add up |
| `turning_around` | Turning around | 1.0 | the model has no such output yet: only the simulator sends it (and `looking_behind`) |
| `hands_off_wheel` | Hands off the wheel | 1.0 | = **no** hand on the wheel (model evidence 0 / 0.45 / 0.85 for 2 / 1 / 0 hands, threshold 0.5) |
| `drowsy` | Drowsiness | 2.5 | heaviest: a microsleep means no reaction at all. From the model's `drowsiness` **and** `eyes_closed` |
| `eyes_off_road` | Eyes off the road | 1.0 | added 2026-11-06; usually comes together with `looking_at_phone`, so they add up |

Background: on 2026-11-06 the CV team listed phone use, turning fully around, hands-on-wheel count, drowsiness and eyes-off-road
(unreliable). The backend split turning into two labels and, once the model's real output arrived, added `eyes_off_road` back.
The model now sends its own frame record; the backend maps its categories (`phone_use` → `looking_at_phone`...; the full
table is in `backend/README.md`, `eating_drinking` is deliberately not scored) and forwards
its risk, alert and per-category probabilities as `TripState.camera` (display only; may be `null`, may hold unknown category names). The models side maps detections to labels
(`BEHAVIORS` in `notebooks/safety_client.py`). **The UI must also render unknown labels** (generic icon + raw label) in case one gets added.

## Score: 0–100, where 100 = fully attentive

- Penalty per tick = Σ weight × seconds, plus a one-off onset worth 2 s when a behaviour starts, then
  × speed (0 below 5 km/h · ×1.0 under 50 · ×1.3 under 90 · ×1.7 highway) × night ×1.5 (22–06 h, from the tick's local timestamp)
  × fragility (1 + (100 − score)/100; the lower the score, the faster it falls).
- Recovery: after 30 s of clean driving, +3 points/min. Stationary (< 5 km/h): no penalty, no recovery, no warnings, not in the statistics.

## Levels → car response (`POLICIES` in alerts.py)

| level | score | `dashboard_light` | reacts when a behaviour has lasted | `vibrate_seat` | `sound` | `message` |
|---|---|---|---|---|---|---|
| `safe` | 90–100 | `green` | never | – | `none` | All good - you're driving safely. |
| `caution` | 75–90 | `green_yellow` | ≥ 5 s | ✓ | `none` | Stay focused on the road. |
| `warning` | 55–75 | `yellow` | ≥ 5 s | ✓ | `low` | Risky behavior detected - eyes on the road. |
| `high_risk` | 35–55 | `yellow` | ≥ 2 s | ✓ | `high` | You're getting distracted often - please focus. |
| `critical` | 10–35 | `red` | immediately | ✓ | `high` | Dangerous driving - focus on the road now. |
| `emergency` | < 10 | `red` | immediately | ✓ | `high` | Critical risk - your emergency contact has been notified. Plus a one-off `emergency` event |
| any + model alarm | – | follows the score | immediately (`camera.alert == "red"`) | ✓ | `high` | at `safe`: Danger detected - eyes on the road now. |

The light always follows the score band. `vibrate_seat` and `sound` are on **only while a behaviour is flagged and the car moves**.
Colours suggested by API.md: green `#22C55E`, green_yellow `#A3E635`, yellow `#FACC15`, red `#EF4444`.

## Frontend reactions (each `state` arrives ~2/s from the models, 1/s from the simulator, so "per message" effects become a rhythm that stops when the field goes off)

| field | phone, foreground (Drive screen, screen kept on) | phone, background / locked | web dashboard (car screen mock) |
|---|---|---|---|
| `dashboard_light` | full-bleed background / big lamp colour | colour + text of the ongoing Drive notification | the car's dashboard lamp |
| `score`, `level` | big number / gauge + level name | notification title | gauge |
| `vibrate_seat: true` | `Vibration.vibrate(300)` per message | same (the foreground service keeps JS alive) | seat-vibration icon pulses |
| `sound: "low"` | `chime` per message | `chime` notification channel | `chime.wav` |
| `sound: "high"` | `alarm_warning` per message + red pulse overlay (≤ 2 Hz) | alarm-stream notification; full-screen intent if locked | `alarm_warning.wav` + red pulse |
| `emergency` event | full-screen red + `alarm_siren` loop + vibration + TTS + max brightness + Text/Call contact | full-screen intent wakes the phone, insistent `alarm_critical` (alarm channel) | full red pulse + `alarm_siren` loop until Dismiss |
| `active_behaviors` | chips: icon + label + seconds | notification body | icon row, lit while active |
| `section` (every 2 s) | "last minute" strip (30 bars: height = score, colour = danger) + what was seen in the last 2 s | – | – |
| `trip_ended` | summary screen (final/avg/min score + tips + drive chart) | notification "Trip ended" | summary card + drive chart |

- Flashing stays ≤ 3 Hz (D14). Sound is the primary channel.
- Pitch angle: if the driver is looking at the phone, the phone itself becomes the warning.

## Demo drive (no models needed)

`python notebooks/safety_client.py [--interval 0.3]` with the backend running. It starts a trip and goes safe → hands off (caution) → phone
(warning) → looking behind + turning (high_risk) → phone at 60 km/h (critical) → drowsy at 130 km/h (emergency) → phone while stopped
at a light (no penalty) → 40 s clean → ends the trip and prints a summary with tips.

## Sections and danger (coordinator, every 2 s; docs/ARCHITECTURE.md)

| `danger` | when (only while moving, ≥ 5 km/h) | chart |
|---|---|---|
| `critical` | model red alert, loud alarm (`sound: high`) or the emergency | red shading; its moment gets a node **and a picture box** |
| `dangerous` | a scored behaviour, model yellow alert, or the seat vibrated | amber shading; its moment gets a node |
| `none` | everything else, and always while standing | – |

Moments = back-to-back dangerous sections (one quiet section bridged), built by the server when it reads the report. The picture
is the frame the model analysed at the section's riskiest tick (danger, then model risk, then score lost), scaled to 960 px.
With the model path, `state` reaches the phone ~2/s (at once on any change), not at the model's 5–10 detections/s.
