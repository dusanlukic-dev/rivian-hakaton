# Cabin camera + the model (`rivian_model/`)

Since 2026-11-07 the model is **Dušan's `rivian_model/`** (D44); the CV team's `notebooks/risk_pipeline.py` and `model/worker.py`
were removed (`git show 8d05c97:<path>` restores them). Dušan's own notes are the detailed reference, in Serbian:
`rivian_model/ATRIBUTI.md` (every signal, thresholds, accuracy on all 56 clips, what not to promise),
`POREDJENJE_MODELA.md` (his model vs the CV model through the same coordinator), `PLAN_KOORDINATOR.md` (how it was fitted).

## Dataset

- On this PC: `C:\Users\matija\Desktop\faks\hakaton\rivian\dataset` (outside the repo; the model scripts find `../dataset` or
  `$env:DATASET_DIR`). 116 clips, 30 s each, 1920×1536, 30 fps, no labels (the filename is date + time). Two camera series:
  `05_23_*` (82) and `08_14_*` (34). Never commit clips or frames from them (faces of real people; `.gitignore` has `*.mp4`).
- The camera is a **fisheye in the headliner looking backwards**: in this LHD car the **driver is on the RIGHT** of the image.
  The model crops a driver zone per series (`rivian_model/rois.json`, pixels of the 1920×1536 frame, scaled to whatever width
  arrives; `camera_stream.py` sends 1280 px). The protocol doesn't say which camera a frame is from, so the series is a start
  option of the model (`--camera 05_23|08_14`) and **all clips of one run must be from one series**.
- Clips worth knowing (ATRIBUTI.md §1): `08_14_62_092916` phone call ~12–24 s, `08_14_62_084339` texting low at the console
  ~11–28 s, `08_14_62_085956` calm (a hand with a smartwatch in front of the camera 0–9 s: must stay green),
  `05_23_62_031246` sunglasses, slumps onto the wheel at ~9 s and stays (collapse), `05_23_62_022338` collapse with hair over
  the face (late), `05_23_62_021254` / `005853` phone. Dark night clips (`05_23_62_0101xx`) and sunglasses are hard for the face.

## What the model does per frame (`rivian_detector.py` → `pipeline.Models` + `features.DriverLogic`)

| category sent | from | catches / misses (Dušan, whole dataset) |
|---|---|---|
| `phone_use` | YOLO11n `cell phone` at 640 px on the driver crop (every 2nd frame, in a parallel thread, result 0.2 s late) **confirmed** by a box in the hand or next to the head, plus pose cues (wrist at the ear = call, head down + hand low at the console = typing, pose alone capped below the threshold unless held 4 s) | 6 real phone clips caught, 2 doubtful; misses a phone in the lap in the dark, glances < 2 s, a phone on the console YOLO can't see. Seat-belt buckling and a hand on the face used to look like a phone: the YOLO confirmation fixed most |
| `eyes_off_road` | MediaPipe Face Landmarker on a head crop around the pose's nose/ears: head angle vs a **continuously refreshed neutral pose** (median of calm frames of the last 60 s; first estimate after 3 s, series prior after 15 s) | 15° → 0, 30° → 1. A driver who mostly looks aside makes that "neutral". Off while slumped |
| `eyes_closed` | blendshapes eyeBlink vs the personal level, off when the head is down > 12° (the camera above sees lids as closed) | no real drowsiness clip exists; sunglasses make it meaningless. The coordinator maps it to `drowsy` |
| `collapse` | YOLO11n-pose: nose below the shoulder line × the body **still** for 1 s, and no phone confirmed | 2 alarms on the whole dataset, both real (031246, 022338). Getting out of the car and leaning over a phone in the lap no longer fire |

The model sends **no** `hands_off_wheel`, `drowsiness` or `eating_drinking`: they stay in `notebooks/risk_config.json` with
evidence 0. Everything after the evidence (smoothing, durations, rules, alert colour, score, the car's reaction) is the
coordinator's (`RiskEngine` + `scoring.py`); `collapse` has its own rule there (D45).

## Setup gotchas

- Own venv on **Python 3.13** (`rivian_model/.venv`): CPU torch from the PyTorch index first, then `requirements.txt`.
  Ultralytics needs torch even for ONNX models. `pipeline.py` sets `YOLO_AUTOINSTALL=false` and `YOLO_OFFLINE=true` before
  importing it: no pip installs or online checks at run time (a car has no internet).
- **GPU (D48):** on Windows `onnxruntime-directml` (any DX12 GPU, CPU included) replaces `onnxruntime`; they share the module, so
  only one may be installed. `pipeline._configure_onnxruntime` overrides Ultralytics' provider choice: CUDA → DirectML
  (high-performance adapter, or `MODEL_GPU_ID`) → CoreML → CPU, per session, with a CPU fallback if a GPU session fails.
  `MODEL_DEVICE` / `--device auto|gpu|cpu`. Ultralytics warns "requirement onnxruntime not found" for the DirectML build
  (filtered: it is there). On a GPU the phone detector runs on every frame (CPU: every 2nd). MediaPipe stays on the CPU on
  Windows (its GPU delegate exists on Linux/macOS only, tried there). The first DirectML start compiles shaders (~7 s once).
- Weights are not in git: `setup_models.py` exports `yolo11n_640.onnx` + `yolo11n-pose_384.onnx` from the `.pt` files
  (downloaded from the Ultralytics GitHub release) and fetches `face_landmarker.task`. Warm-up (D49): a gray frame at startup,
  no dataset frame any more (`warmup_frame.jpg` stays in `.gitignore` for old checkouts).
- ONNX Runtime threads spin by default and three models fight for the cores (~10× slower): `pipeline._tune_onnxruntime` turns
  spinning off and caps threads (`ORT_THREADS`, default 4).
- MediaPipe on Linux needs `libegl1 libgles2` even without a GPU (Dušan's Dockerfile has them).

## Measured here (2026-11-07, Ryzen 5 5600H, mains power)

- Offline (`test_rivian_detector.py`, fake coordinator, same protocol): 300/300 frames, 0 errors, detector median **38–43 ms**
  (p95 50), round trip ~50 ms; 092916 → 40 red, phone 12.6–24.2 s; 031246 → 0 red + emergency, collapse from 11.0 s. Identical
  to Dušan's results (his i5-1235U: ~73 ms).
- Live through the coordinator (`run_compare.py`, cruise 50–62 km/h, main's live score): every frame processed (~10 fps,
  0 lost), worker ~45–50 ms, latency ~54 ms. 092916 phone 13.1–25.2 s, min 16; 084339 phone 13.7–27.1 s + eyes off road,
  min 13; 085956 stays safe (min 87, one 0.4 s blip); 031246 collapse 11.8–29.9 s, **emergency at 13.8 s**, score 0; 021254
  phone 11.8–29.8 s, min 16. The server got 15 sections per 30 s trip, moments with images, and the model report
  (`collapse` / `phone_sustained` rules).
- On the A54 over Bluetooth: trip start/end, live tiles (incl. "Driver not responding"), seat/sound, the collapse emergency
  overlay ("The driver is not responding"), summary + chart with the slumped-driver picture, history. Dashboard: same overlay.
- GPU (GTX 1650, DirectML, session 11): **25 ms per frame** with the phone detector on every frame (CPU: 43 ms with it on every
  2nd), GPU ~35 % busy, 121 MiB; same detections (092916 phone 12.3–24.2 s, 031246 collapse from 11.0 s).
- Ports **8685–8884 are reserved** on this laptop (Windows excluded range): Dušan's old defaults 8765/8766 failed with WinError
  10013. Now `test_rivian_detector.py` takes any free port (`--port 0`) and `run_compare.py` defaults to 8000.
- Two cameras: the second `/camera/ws` connection gets **HTTP 403** at the handshake (the coordinator closes before accept);
  the test client reports it as close code 1008.
