# CV pipeline (`notebooks/risk_pipeline.py`): what we measured on the Rivian cabin dataset

Owner of the code: the CV teammate (ttcpavle). Run instructions (Serbian): `notebooks/pokretanje.txt`.
Dataset on this PC: `D:\Hackathon dataset 2026\*.mp4`. There are 56 clips, each 30 s, 1920×1536, 30 fps, from two recording sessions
(`05_23_*`, `08_14_*`). There are no labels; the filename is only date + time.

## Camera geometry (the #1 source of "weird" detections)

- The camera is a **fisheye in the headliner looking backwards**. In this LHD car the **driver is on the RIGHT of the image**
  (face around x 0.45–0.70, y 0.15–0.45). The passenger is on the left, and rear-seat people are small, in the middle.
- The first config had `driver_roi = [0, 0, 0.65, 1]` (the left side). The pipeline was watching the **passenger**: the face was
  found in 4/150 frames of a texting clip, and the "risk" came only from the *face missing* fallback.
- Current ROIs (fractions of the frame, `[x0, y0, x1, y1]`): `driver_roi [0.35,0,1,1]` (hands + YOLO),
  `head_roi [0.35,0,0.9,0.65]` (face), `steering_wheel_roi [0.66,0.55,1,1]` (the rim; x ≥ 0.55 still included the lap, so a
  phone hand counted as "on wheel"). Set them with `--pick-roi`.
- **Face must be searched in a tight head crop.** MediaPipe's face detector runs at 128×128. Over the whole driver crop the head is
  ~15 px and gets lost when the driver looks down or the cabin is dark. Head crop: 4 → 143 of 150 frames on `05_23_62_010216`.
  CLAHE brightening did **not** help.
- Pose from a crop depends on where the head sits in that crop. **Re-calibrate after changing `head_roi`.**

## Head pose / "looking at the road" baseline

- Road pose in `head_roi` geometry: **yaw ≈ 34°, pitch ≈ 8°** (yaw 34–41 in the later `08_14` clips, pitch −3…14 depending on
  driver height). Clips where the driver mostly talks to the passenger have their dominant pose at yaw 3–14. That is why a
  "median of the first N seconds" baseline is wrong.
- The old calibration took the median over the first 20 s of a **30 s** clip. A driver on the phone early would make "phone" the
  baseline, and eyes_off_road stayed at 0.
- Now: `calibration.mode = auto`. The baseline is the densest (yaw, pitch) cluster of the first 10 s, using only open-eye,
  not-looking-down frames, **clamped to ±10° of the prior**. `mode = fixed` uses the prior only. `--calibrate` on a clean clip
  measures and writes the prior.

## Eyes: looking down ≠ eyes closed (this camera is above the driver)

Blendshape survey over 2129 face frames (every 10th frame of 28 clips):
- `eyeBlink` (closure) and `eyeLookDown` (gaze_down) rise **together** when the driver looks down at a phone/lap: closure 0.4–0.75
  with gaze_down 0.3–0.7. Looking at the road gives both < 0.2.
- No genuinely closed eyes were found in the dataset. Closure > 0.8 came from a downward-sideways glance and from sunglasses
  (sunglasses make the eye blendshapes meaningless).
- So: `gaze_down_thr` 0.55 → **0.35**, gaze evidence is no longer multiplied by `(1 − closure)`, `eye_closed_thr` 0.60 → **0.75**,
  and eyes_closed is suppressed when looking down. Before this, texting showed up as `eyes_closed` + PERCLOS "drowsy".
- When texting, the driver moves the **eyes**, not the head: dpitch is only ~+10° (threshold 18°). Head pose alone misses phone use.

## Phone / objects (YOLO, COCO)

- `yolo11n` @320 almost never sees the phone here (max conf 0.2–0.44). `yolo11s` @640 on the **full-resolution** driver crop finds
  it in ~30% of frames of texting / phone-call clips at ~75 ms on this CPU (cv2.dnn). `yolo11m` was 2.5× slower and not better.
- Detections are intermittent, so `phone.hold_tau_s` keeps a decaying memory. Confidence is normalized by `phone.conf_full`
  (0.5 ⇒ 1.0).
- A phone lying on the centre console is detected too. That's why evidence = conf × proximity to a hand or the face, or the lap term.

## Hands

- MediaPipe hands sees both hands on the wheel in 72–85% of frames in daylight clips, but is poor at night (`05_23_62_0101xx`):
  0 hands in ~37% of frames. Tighter crops didn't help consistently.
- Evidence now needs a hand **seen off the wheel**. "Not detected" maps to `no_hands_detected_p` (low), and "one on, other unseen"
  to `hands.one_on_other_unseen_p`.

## Display / debugging

`--show` window = video (ROIs, driver face box + head-direction arrow, ignored faces in grey, hands green/orange, YOLO boxes) plus a
panel with every variable: per category p / p_hat / ON / run / D / h / r, groups, raw→smoothed→floor→final risk, rules + VATS,
head pose vs baseline, eye blendshapes, PERCLOS, hands, phone components, and a 30 s timeline. `--save-video`, `--verbose` and
`--log-all` give the same data offline.

## Whole-dataset check (2026-11-06, all 56 clips, after the fixes)

- 11 clips stay 100% green (e.g. `05_23_62_010829`, `08_14_62_0920xx`, `08_14_62_0932xx`–`0936xx`).
- Phone clips go red: texting `05_23_62_010216` red 85%, `05_23_62_023436` red 90% (phone 17 s), call `08_14_62_092916` red 37%
  (phone active 12 s, the length of the call).
- `05_23_62_025358` has **no driver** (standing outside the door). It goes yellow from the face-missing fallback. That's expected.
- There's no ground truth, so these are plausibility checks, not accuracy numbers. To re-check quickly after a threshold change,
  re-run with `--log-all` once, then **replay** `RiskEngine.step()` over `frames.jsonl` (each line has every category's raw `p`
  and the perception values). That takes seconds instead of 25 s per clip.
- Log folders are `logs/<timestamp>_<clip>`. Before this, two runs started in the same second appended into one `frames.jsonl`.

## Bridge to the backend (landed by the backend teammate in parallel)

- `SafetyClient.send_frame(rec)` (`notebooks/safety_client.py`) posts a `frames.jsonl` record **without `perception`** to `/telemetry`.
  The backend maps active categories to labels (`CATEGORY_TO_BEHAVIOR` in `backend/app/services/camera.py`): `phone_use` →
  `looking_at_phone`, `eyes_off_road` → `eyes_off_road`, `hands_off_wheel` → same, `drowsiness`/`eyes_closed` → `drowsy`,
  `eating_drinking` ignored. Its 0–100 score stays the main one; the model's red alert only forces vibration + sound.
- So **never rename or add a category** in `risk_config.json` without the backend: `backend/tests/test_camera_mapping.py` fails on an
  unknown one. The keys `hands`, `phone`, `head_roi` etc. are outside `categories`, so they're safe.
- `risk_pipeline.py` doesn't call `send_frame` live yet. `safety_client.py --replay logs/<run>/frames.jsonl` replays a recorded run.
