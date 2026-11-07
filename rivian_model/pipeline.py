"""
pipeline.py - klip -> JSON događaja + skor + najkritičniji frejm (jpg) + video sa okvirima.

Upotreba:
    python pipeline.py 08_14_62_092916 08_14_62_084339        (ID klipa iz dataseta)
    python pipeline.py "C:\\put\\do\\klipa.mp4"
    python pipeline.py --all-test                              (4 test klipa)
    python pipeline.py 08_14_62_092916 --realtime --send ws://localhost:8000/ingest
                                                               (demo: tempo prave kamere + slanje backendu)
    opcije: --backend onnx|torch  --det-imgsz 640  --pose-imgsz 384  --phone-every 2
            --no-video  --out out_pipeline
            --send URL (WebSocket backenda)  --api URL (REST backenda, inače iz --send)
            --realtime  --vehicle-id demo-auto-1

Po obrađenom frejmu (svaki 3. = 10 fps):
    1. isečak vozača (rois.json po seriji kamere 05_23 / 08_14)
    2. yolo11n-pose  -> 17 tačaka vozača (najveća osoba u isečku)
    3. yolo11n       -> "cell phone" kutije (conf >= 0.15), filter: u šaci ili uz glavu
    4. MediaPipe Face Landmarker na isečku glave -> yaw/pitch, zatvorenost očiju
    5. features.py   -> verovatnoće: phone, look_away, drowsy, collapse
    6. scoring.py    -> live poruka; na kraju finish() JSON
Izlaz u out_pipeline/<clip>/: result.json, live.jsonl, critical.jpg, annotated.mp4
live.jsonl: jedna JSON linija po obrađenom frejmu (10 u sekundi).
Uz --send iste podatke šalje backendu po ugovoru v1 (ARHITEKTURA.md, sekcija 5) - vidi sender.py;
neposlate poruke ostaju u <out>/<clip>/unsent.jsonl.
"""
import os, sys, json, time, argparse, statistics
T0_PROGRAM = time.perf_counter()   # početak programa, pre učitavanja teških biblioteka (za "spreman posle X s")
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO

from scoring import DriverScorer
from features import Pose, phone_ok, DriverLogic

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"C:\Users\PC\Downloads\Hackathon dataset 2026\Hackathon dataset 2026"
ROI_FILE = os.path.join(HERE, "rois.json")
FACE_MODEL = os.path.join(HERE, "face_landmarker.task")
TEST_CLIPS = ["08_14_62_092916", "08_14_62_084339", "08_14_62_085956", "05_23_62_031246"]
STEP = 3                 # svaki 3. frejm (30 fps -> 10 fps)
PHONE_CONF = 0.15
PHONE_CLS = 67           # COCO "cell phone"
SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12), (0, 1), (0, 2), (1, 3), (2, 4)]
ORT_THREADS = int(os.environ.get("ORT_THREADS", "4"))
RULES_VERSION = "v1"     # verzija pravila (features.py + scoring.py), ide u trip_start poruku
_HW = None        # opis hardvera za izveštaj; čita se tek kad zatreba (PowerShell upit traje ~1-2 s)


def _tune_onnxruntime(threads):
    """
    Bez ovoga ONNX Runtime je ~10x sporiji u pipeline-u (300 ms umesto 30 ms po modelu):
    dve ONNX sesije (telefon + poza) + MediaPipe se otimaju o jezgra jer ORT niti po
    defaultu "vrte" u praznom hodu (spin-wait). Isključujemo to i ograničavamo broj niti.
    """
    import onnxruntime as ort
    if getattr(ort.InferenceSession, "_tuned", False):
        return
    orig = ort.InferenceSession

    def session(path, sess_options=None, *a, **k):
        so = sess_options or ort.SessionOptions()
        so.intra_op_num_threads, so.inter_op_num_threads = threads, 1
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        return orig(path, so, *a, **k)
    session._tuned = True
    ort.InferenceSession = session


# ---------------- modeli ----------------
class Models:
    def __init__(self, backend="onnx", det_imgsz=640, pose_imgsz=384):
        # telefon mora na 640 (na 480 se gubi telefon u ruci nisko - 084339: 32 -> 0 pogodaka);
        # poza na 384 se slaže 90-100% sa 640, a duplo je brža
        self.det_imgsz, self.pose_imgsz, self.backend = det_imgsz, pose_imgsz, backend
        if backend == "onnx":
            _tune_onnxruntime(ORT_THREADS)
            self.det = YOLO(self._onnx("yolo11n", det_imgsz), task="detect")
            self.pose = YOLO(self._onnx("yolo11n-pose", pose_imgsz), task="pose")
        else:
            self.det = YOLO(os.path.join(HERE, "yolo11n.pt"))
            self.pose = YOLO(os.path.join(HERE, "yolo11n-pose.pt"))
        o = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=FACE_MODEL),
            running_mode=mp.tasks.vision.RunningMode.IMAGE, num_faces=1,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.4, min_face_presence_confidence=0.4)
        self.face = mp.tasks.vision.FaceLandmarker.create_from_options(o)
        self.load_s = None       # od pokretanja programa do učitanih biblioteka i modela (meri main)
        self.warmup_s = None     # koliko je trajalo zagrevanje (None = još nije urađeno)
        self.ready_s = None      # od pokretanja programa do "spreman" (posle zagrevanja)

    def warmup(self, frame, roi):
        """
        Jednom po pokretanju programa: provuci jedan pravi frejm kroz sva tri modela i baci rezultat.
        Prvi poziv svakog modela je spor (~2 s): pravi se ONNX sesija i optimizuje mreža za ovaj procesor,
        MediaPipe priprema svoj CPU ubrzivač, rezerviše se memorija. Bolje da se to desi PRE nego što
        krene vožnja, nego da prve ~2 s vožnje nema rezultata (grafikon na nuli, ~20 preskočenih frejmova).
        Frejm treba da ima lice, da bi se zagrejao i MediaPipe model za tačke lica.
        """
        if self.warmup_s is not None:
            return
        x, y, w, h = roi
        t0 = time.perf_counter()
        crop = frame[y:y + h, x:x + w]
        kp = run_pose(self, crop, x, y)
        run_phone(self, crop, x, y)
        run_face(self, frame, Pose(kp) if kp else None)
        self.warmup_s = round(time.perf_counter() - t0, 2)
        self.ready_s = round(time.perf_counter() - T0_PROGRAM, 2)
        print(f"  zagrevanje modela: {self.warmup_s} s (jednom, pre voznje) -> spreman {self.ready_s} s "
              f"posle pokretanja", flush=True)

    def close(self):
        """Zatvori MediaPipe eksplicitno; inače pri gašenju Python-a ispiše bezopasnu ali ružnu grešku."""
        self.face.close()

    @staticmethod
    def _onnx(name, imgsz):
        path = os.path.join(HERE, f"{name}_{imgsz}.onnx")
        if not os.path.exists(path):   # izvezi jednom (treba paket onnx)
            YOLO(os.path.join(HERE, name + ".pt")).export(format="onnx", imgsz=imgsz, simplify=True)
            os.replace(os.path.join(HERE, name + ".onnx"), path)
        return path


def run_pose(models, crop, ox, oy):
    """Vozač = najveća osoba u isečku (conf >= 0.25). Probali smo i slabije detekcije (0.10) za vozača
    pognutog na volan (05_23_62_022338), ali su tačke tada besmislene - ne pomaže."""
    r = models.pose(crop, imgsz=models.pose_imgsz, conf=0.25, verbose=False)[0]
    if not len(r.boxes):
        return None
    b = r.boxes.xyxy.tolist()
    j = max(range(len(b)), key=lambda k: (b[k][2] - b[k][0]) * (b[k][3] - b[k][1]))
    return [[p[0] + ox, p[1] + oy, p[2]] for p in r.keypoints.data[j].tolist()]


def run_phone(models, crop, ox, oy):
    r = models.det(crop, imgsz=models.det_imgsz, conf=PHONE_CONF, classes=[PHONE_CLS], verbose=False)[0]
    return [[b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy, c]
            for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]


def run_face(models, frame, pose):
    """Isečak glave oko tačaka nosa/očiju/ušiju iz poze -> Face Landmarker."""
    if pose is None:
        return None
    pts = [p for p in pose.kp[:5] if p[2] > 0.3]
    if not pts:
        return None
    s = 1.1 * max(pose.sw, 80)
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    H, W = frame.shape[:2]
    x1, y1 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    x2, y2 = int(min(W, cx + s / 2)), int(min(H, cy + s / 2))
    if x2 - x1 < 40 or y2 - y1 < 40:
        return None
    rgb = np.ascontiguousarray(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
    r = models.face.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not r.face_landmarks:
        return None
    bs = {b.category_name: b.score for b in r.face_blendshapes[0]}
    R = np.array(r.facial_transformation_matrixes[0])[:3, :3]
    yaw = float(np.degrees(np.arctan2(-R[2, 0], np.hypot(R[0, 0], R[1, 0]))))
    pitch = float(np.degrees(np.arctan2(R[2, 1], R[2, 2])))
    L = r.face_landmarks[0]
    xs = [p.x * (x2 - x1) + x1 for p in L]; ys = [p.y * (y2 - y1) + y1 for p in L]
    return {"yaw": yaw, "pitch": pitch, "blinkL": bs.get("eyeBlinkLeft", 0.0),
            "blinkR": bs.get("eyeBlinkRight", 0.0), "box": [min(xs), min(ys), max(xs), max(ys)]}


# ---------------- crtanje ----------------
def draw(frame, roi, rec, live, scale=0.5):
    img = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    S = lambda v: int(v * scale)
    x, y, w, h = roi
    cv2.rectangle(img, (S(x), S(y)), (S(x + w), S(y + h)), (200, 200, 200), 1)
    kp = rec["kp"]
    if kp:
        for a, b in SKELETON:
            if kp[a][2] > 0.3 and kp[b][2] > 0.3:
                cv2.line(img, (S(kp[a][0]), S(kp[a][1])), (S(kp[b][0]), S(kp[b][1])), (255, 200, 0), 2)
        for i in (9, 10):
            if kp[i][2] > 0.3:
                cv2.circle(img, (S(kp[i][0]), S(kp[i][1])), 5, (255, 0, 255), -1)
    for p in rec["phones"]:
        col = (0, 0, 255) if p[5] else (128, 128, 128)    # crveno = prihvaćen, sivo = odbačen filterom
        cv2.rectangle(img, (S(p[0]), S(p[1])), (S(p[2]), S(p[3])), col, 2)
        cv2.putText(img, f"phone {p[4]:.2f}" + ("" if p[5] else " X"), (S(p[0]), S(p[1]) - 4), 0, 0.45, col, 1)
    if rec["face_box"]:
        fb = rec["face_box"]
        cv2.rectangle(img, (S(fb[0]), S(fb[1])), (S(fb[2]), S(fb[3])), (0, 255, 0), 1)
    # HUD
    pr = rec["probs"]
    color = (0, 0, 255) if live["alert"] else (0, 200, 0)
    cv2.rectangle(img, (0, 0), (330, 175), (0, 0, 0), -1)
    cv2.putText(img, f"t={live['t']:5.1f}s  score {live['live_score']}", (8, 24), 0, 0.65, (255, 255, 255), 2)
    cv2.putText(img, f"ALERT: {live['reason']}" if live["alert"] else "OK", (8, 50), 0, 0.65, color, 2)
    rows = [("phone", pr["phone"]), (" yolo", rec["sig"]["yolo_phone"]), (" call", rec["sig"]["pose_call"]),
            (" typing", rec["sig"]["pose_typing"]), ("look_away", pr["look_away"]), ("drowsy", pr["drowsy"]),
            ("collapse", pr["collapse"])]
    for k, (n, v) in enumerate(rows):
        yy = 70 + k * 15
        cv2.putText(img, n, (8, yy + 4), 0, 0.4, (255, 255, 255), 1)
        cv2.rectangle(img, (95, yy - 6), (95 + int(200 * v), yy + 4), (0, 165, 255) if v >= 0.6 else (120, 120, 120), -1)
    return img


def _rss_mb(peak=False):
    try:
        import psutil
        mi = psutil.Process().memory_info()
        return (getattr(mi, "peak_wset", mi.rss) if peak else mi.rss) / 1e6
    except Exception:
        return -1


def _hardware():
    import platform
    try:
        import psutil
        ram = f"{psutil.virtual_memory().total / 2**30:.0f} GB RAM"
    except Exception:
        ram = "? RAM"
    cpu = platform.processor()
    try:
        import subprocess
        cpu = subprocess.run(["powershell", "-NoProfile", "-c", "(Get-CimInstance Win32_Processor).Name"],
                             capture_output=True, text=True, timeout=10).stdout.strip() or cpu
    except Exception:
        pass
    return f"{cpu}, {os.cpu_count()} logičkih jezgara, {ram}, bez GPU"


def hardware():
    """Opis hardvera za perf; računa se jednom, posle vožnje, da ne usporava pokretanje."""
    global _HW
    if _HW is None:
        _HW = _hardware()
    return _HW


def model_sizes_mb(models):
    files = [f"yolo11n_{models.det_imgsz}.onnx", f"yolo11n-pose_{models.pose_imgsz}.onnx", "face_landmarker.task"]         if models.backend == "onnx" else ["yolo11n.pt", "yolo11n-pose.pt", "face_landmarker.task"]
    return {f: round(os.path.getsize(os.path.join(HERE, f)) / 1e6, 1) for f in files if os.path.exists(os.path.join(HERE, f))}


# ---------------- glavna petlja ----------------
def _no_trip_id(d):
    return {k: v for k, v in d.items() if k != "trip_id"}


def process(clip_path, models, out_root, write_video=True, phone_every=2,
            send_url=None, api_url=None, realtime=False, vehicle_id="demo-auto-1"):
    clip = os.path.basename(clip_path).replace("_video_inCabin.mp4", "").replace(".mp4", "")
    series = clip[:5]
    roi = json.load(open(ROI_FILE))[series]
    x, y, w, h = roi
    out_dir = os.path.join(out_root, clip)
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        raise IOError(f"Ne mogu da otvorim {clip_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if models.warmup_s is None:            # jednom po pokretanju: pre trip_start i pre "sata kamere"
        wcap = cv2.VideoCapture(clip_path)
        ok, first = wcap.read()
        wcap.release()
        if ok:
            models.warmup(first, roi)
    vw = None
    started = time.time()
    # uz slanje: jedinstven ID vožnje (isti klip pušten dvaput = dve vožnje u bazi)
    trip_id = f"{clip}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(started))}" if send_url else clip
    scorer, logic = DriverScorer(trip_id), DriverLogic(series)
    sender = None
    if send_url:
        from sender import Sender, utc_iso
        sender = Sender(send_url, trip_id)
        sender.send("trip_start", {
            "vehicle_id": vehicle_id, "clip": clip, "camera": series, "fps": round(fps / STEP, 1),
            "started_at": utc_iso(started),
            "models": f"yolo11n {models.det_imgsz} + yolo11n-pose {models.pose_imgsz} ({models.backend}) "
                      f"+ MediaPipe face_landmarker, CPU",
            "rules_version": RULES_VERSION})
    n_alerts = n_events = 0
    late = skipped = 0
    records, live_log = [], []
    t_analysis, t_total, ram = [], [], []
    phones, n, fut = [], 0, None
    pool = ThreadPoolExecutor(1)          # telefon-YOLO radi paralelno sa pozom i licem
    i = 0
    wall0 = t_frame0 = time.perf_counter()
    while True:
        if not cap.grab():
            break
        if i % STEP:
            i += 1
            continue
        if realtime and i / fps < time.perf_counter() - wall0 - STEP / fps:
            # obrada kasni: prava kamera bi ovaj frejm već zamenila novim -> preskoči ga
            # (umesto da se kašnjenje gomila). Skor se računa po vremenu, pa i dalje važi.
            skipped += 1
            i += 1
            continue
        _, frame = cap.retrieve()
        t = i / fps
        crop = frame[y:y + h, x:x + w]

        # Telefon-YOLO (najsporiji model) radi asinhrono: na svaki N-ti frejm preuzmemo rezultat
        # prethodnog pokretanja i pokrenemo ga na novom frejmu. Kašnjenje = N/10 s (0.2 s).
        if n % phone_every == 0:
            if fut is not None:
                phones = fut.result()
            fut = pool.submit(run_phone, models, crop.copy(), x, y)
        n += 1
        kp = run_pose(models, crop, x, y)
        face = run_face(models, frame, Pose(kp) if kp else None)
        probs, sig, pose, face = logic.update(t, kp, phones, face)   # sva pravila: features.py
        live = scorer.update(t, probs)
        t_an = time.perf_counter()
        t_analysis.append((t_an - t_frame0) * 1000)   # dekodovanje + modeli + pravila + skor
        if len(t_analysis) % 10 == 0:
            ram.append(_rss_mb())

        rec = {"i": i, "t": round(t, 2), "kp": kp, "sig": sig, "probs": probs,
               "phones": [p + [phone_ok(p, pose)] for p in phones],
               "face_box": face["box"] if face else None, "live": live}
        records.append(rec)
        msg_probs = {k: round(v, 3) for k, v in probs.items()}
        live_log.append({**live, "probs": msg_probs})
        if sender:                         # ne čeka mrežu - samo stavlja u red (sender.py)
            sender.send("live", {**_no_trip_id(live), "probs": msg_probs})
            for a in scorer.alerts[n_alerts:]:
                sender.send("alert", a)
            for e in scorer.events[n_events:]:
                sender.send("event", _no_trip_id(e))
            n_alerts, n_events = len(scorer.alerts), len(scorer.events)

        if write_video:
            img = draw(frame, roi, rec, live)
            if vw is None:
                vw = cv2.VideoWriter(os.path.join(out_dir, "annotated.mp4"),
                                     cv2.VideoWriter_fourcc(*"mp4v"), fps / STEP, (img.shape[1], img.shape[0]))
            vw.write(img)
        t_end = time.perf_counter()
        t_total.append((t_end - t_frame0) * 1000)
        if realtime:                       # tempo prave kamere: sledeći frejm "stiže" tek u t + 0.1 s
            wait = wall0 + t + STEP / fps - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            else:
                late += 1
        t_frame0 = time.perf_counter()     # čekanje se ne računa u vreme obrade
        i += 1
    if vw is not None:
        vw.release()
    pool.shutdown()

    result = scorer.finish()

    # najkritičniji frejm: vrh najgoreg događaja; ako ga nema, vrh hitnog (kolaps) događaja
    crit_t = result["critical_frame_t"]
    if crit_t is None:
        em = [e for e in result["events"] if e["emergency"]]
        crit_t = em[0]["peak_t"] if em else None
    result["critical_frame_file"] = None
    if crit_t is not None:
        rec = min(records, key=lambda r: abs(r["t"] - crit_t))
        cap.set(cv2.CAP_PROP_POS_FRAMES, rec["i"])
        ok, frame = cap.read()
        if ok:
            cv2.imwrite(os.path.join(out_dir, "critical.jpg"), draw(frame, roi, rec, rec["live"], scale=1.0))
            result["critical_frame_file"] = "critical.jpg"
    cap.release()

    p = lambda a, q: round(float(np.percentile(a, q)), 1)   # svi frejmovi (zagrevanje je pre vožnje)
    sizes = model_sizes_mb(models)
    result["perf"] = {"frames_processed": len(records), "analysis_fps": round(fps / STEP, 1),
                      "ms_per_frame_analysis_mean": round(statistics.mean(t_analysis), 1),
                      "ms_per_frame_analysis_median": p(t_analysis, 50),
                      "ms_per_frame_analysis_p95": p(t_analysis, 95),
                      "ms_per_frame_analysis_p99": p(t_analysis, 99),
                      "ms_per_frame_analysis_max": round(max(t_analysis), 1),
                      "ms_per_frame_with_video_mean": round(statistics.mean(t_total), 1),
                      "ram_mb_avg": round(statistics.mean(ram)) if ram else None,
                      "ram_mb_peak": round(_rss_mb(peak=True)),
                      "model_files_mb": sizes, "models_total_mb": round(sum(sizes.values()), 1),
                      "startup_s": {"load": models.load_s, "warmup": models.warmup_s, "ready_after": models.ready_s},
                      "hardware": hardware(),
                      "backend": f"{models.backend} det={models.det_imgsz} pose={models.pose_imgsz} phone_every={phone_every}"}
    if realtime:
        result["perf"]["realtime"] = True
        result["perf"]["realtime_late_frames"] = late       # frejmovi obrađeni sporije od 100 ms
        result["perf"]["realtime_skipped_frames"] = skipped  # preskočeni jer je obrada kasnila
    calib = logic.calib
    result["face_calibration"] = {"source": calib.source,
                                  "neutral_yaw_pitch_eyes": [round(v, 2) for v in calib.neutral] if calib.neutral else None}
    json.dump(result, open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "live.jsonl"), "w", encoding="utf-8") as f:
        for m in live_log:
            f.write(json.dumps(m) + "\n")
    if sender:
        from sender import post_critical, api_base_from_ws
        for e in scorer.events[n_events:]:            # događaji koji su trajali do kraja vožnje
            sender.send("event", _no_trip_id(e))
        sender.send("trip_end", result)
        unsent = sender.close(wait_s=5.0)
        st = sender.stats
        line = (f"  slanje: {st['messages']} poruka, potvrdjeno do seq {st['acked_upto']}, "
                f"veza {st['connects']}x, prekida {st['disconnects']}, nepotvrdjeno {len(unsent)}")
        if unsent:
            with open(os.path.join(out_dir, "unsent.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(unsent) + "\n")
            line += f" -> sacuvano u unsent.jsonl ({st['last_error']})"
        if result["critical_frame_file"]:
            ok, info = post_critical(api_url or api_base_from_ws(send_url), trip_id,
                                     os.path.join(out_dir, "critical.jpg"))
            line += f" | critical.jpg: {info}"
        print(line, flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--all-test", action="store_true")
    ap.add_argument("--all", action="store_true", help="svi klipovi iz dataseta")
    ap.add_argument("--backend", default="onnx", choices=["onnx", "torch"])
    ap.add_argument("--det-imgsz", type=int, default=640)
    ap.add_argument("--pose-imgsz", type=int, default=384)
    ap.add_argument("--phone-every", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--send", default=None, help="WebSocket backenda, npr. ws://localhost:8000/ingest")
    ap.add_argument("--api", default=None, help="REST backenda (za critical.jpg); podrazumevano iz --send")
    ap.add_argument("--realtime", action="store_true", help="obrada tempom prave kamere (10 fps)")
    ap.add_argument("--vehicle-id", default="demo-auto-1")
    ap.add_argument("--out", default=os.path.join(HERE, "out_pipeline"))
    a = ap.parse_args()
    clips = TEST_CLIPS if a.all_test or not a.clips else a.clips
    if a.all:
        clips = sorted(f.replace("_video_inCabin.mp4", "") for f in os.listdir(DATA) if f.endswith(".mp4"))
    models = Models(a.backend, a.det_imgsz, a.pose_imgsz)
    models.load_s = round(time.perf_counter() - T0_PROGRAM, 2)   # biblioteke + modeli
    try:
        run_all(clips, models, a)
    finally:
        models.close()


def run_all(clips, models, a):
    for c in clips:
        path = c if c.lower().endswith(".mp4") else os.path.join(DATA, c + "_video_inCabin.mp4")
        r = process(path, models, a.out, not a.no_video, a.phone_every,
                    send_url=a.send, api_url=a.api, realtime=a.realtime, vehicle_id=a.vehicle_id)
        ev = ", ".join(f'{e["type"]} {e["start"]}-{e["end"]}s' for e in r["events"]) or "-"
        print(f'{r["trip_id"]}: skor {r["score"]} {r["color"]}, emergency={r["emergency"]} | {ev} | '
              f'medijana {r["perf"]["ms_per_frame_analysis_median"]} ms/frejm (p95 {r["perf"]["ms_per_frame_analysis_p95"]}, '
              f'p99 {r["perf"]["ms_per_frame_analysis_p99"]}), RAM avg {r["perf"]["ram_mb_avg"]} / peak {r["perf"]["ram_mb_peak"]} MB | '
              f'kalib: {r["face_calibration"]["source"]}')


if __name__ == "__main__":
    main()
