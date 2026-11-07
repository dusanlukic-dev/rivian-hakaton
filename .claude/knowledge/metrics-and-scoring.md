# Behaviours, score, levels, and what the frontend does with them

The backend owns all the logic: `backend/app/coordinator/services/scoring.py` (score), `.../alerts.py` (levels → car response),
with a summary in the root `CLAUDE.md`. This is the frontend cheat sheet. If the code and this file disagree, **the code wins**, so update this file.

## Behaviours (labels from the camera models, `POST /telemetry` ~2/s)

| label | UI text (EN) | severity at 50 km/h: onset + per s → max | notes |
|---|---|---|---|
| `looking_at_phone` | Looking at phone | 0.30 + 0.12/s → 0.80 | the most demo-able signal |
| `looking_behind` | Looking behind | 0.30 + 0.10/s → 0.75 | usually reported together with `turning_around` |
| `turning_around` | Turning around | 0.25 + 0.10/s → 0.70 | the model has no such output yet: only the simulator sends it (and `looking_behind`) |
| `hands_off_wheel` | Hands off the wheel | 0.15 + 0.05/s → 0.45 | = **no** hand on the wheel (model evidence 0 / 0.45 / 0.85 for 2 / 1 / 0 hands, threshold 0.5) |
| `drowsy` | Drowsiness | 0.60 + 0.15/s → 1.00 | heaviest: a microsleep means no reaction at all. From the model's `drowsiness` **and** `eyes_closed` |
| `eyes_off_road` | Eyes off the road | 0.20 + 0.08/s → 0.50 | usually comes together with `looking_at_phone` (the model reports both) |
| `collapse` | Driver not responding | none until confirmed, then **score 0** | the driver slumped over and still (model `collapse`). After 2 s: score 0, red, loud, seat, contact alerted, **even standing still**; held 10 s after last seen. Phone + dashboard show "The driver is not responding" on the emergency screen |

Background: on 2026-11-06 the CV team listed phone use, turning fully around, hands-on-wheel count, drowsiness and eyes-off-road
(unreliable). The backend split turning into two labels and, once the model's real output arrived, added `eyes_off_road` back.
Since 2026-11-07 the model is Dušan's (`rivian_model/`): it sends `phone_use`, `eyes_off_road`, `eyes_closed` (→ `drowsy`) and
`collapse`. `hands_off_wheel`, `looking_behind` and `turning_around` now come only from the simulators.
The model now sends its own frame record; the backend maps its categories (`phone_use` → `looking_at_phone`...; the full
table is in `backend/README.md`, `eating_drinking` is deliberately not scored) and forwards
its risk, alert and per-category probabilities as `TripState.camera` (display only; may be `null`, may hold unknown category names). The models side maps detections to labels
(`BEHAVIORS` in `notebooks/safety_client.py`). **The UI must also render unknown labels** (generic icon + raw label) in case one gets added.

## Score: 0–100, how safe the driving is RIGHT NOW (since 2026-11-07, D35)

A live reading, **not a points balance**: it falls while something risky happens and is back at 100 a few seconds after it stops.
- danger now = worst behaviour + 30 % of what the others add (they come together: phone + eyes off road), severity grows with how long
  it lasts (table above); or the model's risk if higher (`risk.final` minus its calm baseline 0.1, ×0.8: 0.96 red → 0.77).
- × speed factor: **0 below 5 km/h** (standing: anything goes, no warnings), 0.4 at walking pace, 1.0 at 50, 1.6 at 130 km/h (linear);
  × night 1.25 (22–06 h, from the tick's local timestamp).
- **Episodes, not frames (session 11, D46):** a behaviour counts once seen for its onset (phone 1 s, eyes off road 2 s, eyes closed
  1 s, hands off 2 s, behind/turning 1 s) and, once it counts, survives gaps up to its bridge (phone 2.5 s, eyes off road 1.5 s).
  `trip.active` / `active_behaviors` hold only counted episodes, so the score, alerts, sections and tiles don't flicker. Cost:
  the warning goes on up to the bridge after the behaviour really ends; tiles appear after the onset.
- target = max(100 × (1 − danger × factor), 10): **without a collapse the score never goes below 10** (D47). The score follows
  the target: falls with τ 0.5 s, rises with τ 2.5 s (τ 0.5 s while standing).
- Calibration (daytime): phone 6 s = high risk at 30, critical at 50 and above; a microsleep at speed is critical; hands off =
  caution/warning. Calm driving = 100 exactly. Measured on clips: the phone call clip 021254 falls once and holds (0 reversals,
  was 8), the calm clip 085956 stays at 100 (a 0.4 s glance used to dip it to 87).
- Statistics (behaviour seconds, `average_score`) count **moving time only**. The summary's `level` is for `average_score`;
  `final_score` is the live score at the end (~100 once parked), so the apps headline the average.
- The `emergency` event (contact) fires only for a confirmed collapse (2 s), at any speed, once per trip.

## Levels → car response (`POLICIES` in alerts.py)

| level | score | `dashboard_light` | `vibrate_seat` | `sound` | `message` |
|---|---|---|---|---|---|
| `safe` | 90–100 | `green` | – | `none` | All good - you're driving safely. |
| `caution` | 75–90 | `green_yellow` | – | `none` | Stay focused on the road. |
| `warning` | 55–75 | `yellow` | ✓ | `low` | Risky behavior detected - eyes on the road. |
| `high_risk` | 35–55 | `yellow` | ✓ | `high` | High risk - focus on the road now. |
| `critical` | 10–35 | `red` | ✓ | `high` | Dangerous driving - focus on the road now. |
| `emergency` | 0 (collapse only) | `red` | ✓ | `high` | Driver not responding - emergency contact alerted. Plus the one-off `emergency` event |
| any + model alarm | – | follows the score | ✓ | `high` | at `safe`: Danger detected - eyes on the road now. |
| standing (< 5 km/h) | – | `green` | – | `none` | Standing still - no warnings. |

The light follows the level. `vibrate_seat` and `sound` are on **only while something risky is happening now** (a behaviour, or the
model's yellow/red alert) **and the car moves**: they stop the moment the phone goes away, while the light eases back with the score.
Colours suggested by API.md: green `#22C55E`, green_yellow `#A3E635`, yellow `#FACC15`, red `#EF4444`.

## Frontend reactions (each `state` arrives ~2/s from the models, 1/s from the simulator, so "per message" effects become a rhythm that stops when the field goes off)

| field | phone, foreground (Drive screen, screen kept on) | phone, background / locked | web dashboard (car screen mock) |
|---|---|---|---|
| `dashboard_light` | full-bleed background / big lamp colour | colour + text of the ongoing Drive notification | the car's dashboard lamp |
| `score`, `level` | big number / gauge + level name | notification title | gauge |
| `vibrate_seat: true` | `Vibration.vibrate(300)` per message | same (the foreground service keeps JS alive) | seat-vibration icon pulses |
| `sound: "low"` | nothing (no sound on the phone, D53) | nothing | `chime.wav` |
| `sound: "high"` | red pulse overlay (≤ 2 Hz); sound only at level `critical`: `alarm_critical` bell per message (D53) | silent heads-up notification (`warning_v1` channel) | `alarm_warning.wav` + red pulse |
| `emergency` event | full-screen red + `alarm_siren` loop (stronger bell) + vibration + max brightness + Text/Call contact (no voice, D53) | full-screen intent wakes the phone, insistent `alarm_siren` (`alarm_v2` alarm channel) | full red pulse + `alarm_siren` loop until Dismiss |
| `active_behaviors` | chips: icon + label + seconds | notification body | icon row, lit while active |
| `section` (every 2 s) | "last minute" strip (30 bars: height = score, colour = danger) + what was seen in the last 2 s | – | – |
| `trip_ended` | summary screen (average while driving + lowest + tips + drive chart) | notification "Trip ended" | summary card + drive chart |

- Flashing stays ≤ 3 Hz (D14). Sound is the primary channel.
- Pitch angle: if the driver is looking at the phone, the phone itself becomes the warning.

## Demo drive (no models needed)

`python notebooks/safety_client.py [--interval 0.3]` with the backend running. It starts a trip and goes safe → hands off (caution →
warning) → back to safe → phone (warning → critical) → looking behind + turning at 80 km/h (critical) → phone at 60 (high risk) →
drowsy at 130 km/h (emergency) → phone while stopped at a light (nothing) → 10 s clean → ends the trip and prints a summary with tips.
Each phase recovers to safe before the next. **With the real car instead:** `.\demo.ps1 -PoVoznji` (each trip started on the phone
gets the next dataset clip: collapse `05_23_62_031246`, phone `05_23_62_021254`, phone in the lap `05_23_62_005853`).

## Sections and danger (coordinator, every 2 s; docs/ARCHITECTURE.md)

| `danger` | when (only while moving, ≥ 5 km/h) | chart |
|---|---|---|
| `critical` | model red alert, loud alarm (`sound: high`) or the emergency | red shading; its moment gets a node **and a picture box** |
| `dangerous` | a scored behaviour, model yellow alert, or the seat vibrated | amber shading; its moment gets a node |
| `none` | everything else, and always while standing | – |

Moments = back-to-back dangerous sections (one quiet section bridged), built by the server when it reads the report. The picture
is the frame the model analysed at the section's riskiest tick (danger, then model risk, then score lost), scaled to 960 px.
With the model path, `state` reaches the phone ~2/s (at once on any change), not at the model's 5–10 detections/s.
