"""
Pravila koja sirove izlaze modela (YOLO telefon, YOLO poza, MediaPipe lice) pretvaraju
u verovatnoće 0-1 po kategoriji za scoring.py.

Sve dužine su normalizovane širinom ramena (sw) -> ne zavisi od toga koliko je vozač blizu kameri.
Koordinatni sistem poze: x,y u pikselima punog frejma; centar = sredina ramena.
Pragovi su podešeni na 4 test klipa (08_14 serija + 05_23_62_031246) - videti ATRIBUTI.md.
"""
import math

# COCO ključne tačke
NOSE, L_EAR, R_EAR, L_SH, R_SH, L_WR, R_WR = 0, 3, 4, 5, 6, 9, 10
KP_MIN_CONF = 0.3


def ramp(v, v0, v1):
    """Linearno 0 kod v0 -> 1 kod v1 (radi i kad je v0 > v1)."""
    if v0 == v1:
        return float(v >= v1)
    return max(0.0, min(1.0, (v - v0) / (v1 - v0)))


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Pose:
    """Pomoćne veličine iz 17 ključnih tačaka vozača."""

    def __init__(self, kp):
        self.kp = kp
        self.sw = max(_d(kp[L_SH], kp[R_SH]), 1.0)
        self.cx = (kp[L_SH][0] + kp[R_SH][0]) / 2
        self.cy = (kp[L_SH][1] + kp[R_SH][1]) / 2
        self.wrists = [kp[i] for i in (L_WR, R_WR) if kp[i][2] >= KP_MIN_CONF]
        self.head = [kp[i] for i in (NOSE, L_EAR, R_EAR) if kp[i][2] >= KP_MIN_CONF]

    def rel(self, p):
        return (p[0] - self.cx) / self.sw, (p[1] - self.cy) / self.sw

    @property
    def nose_sh(self):
        """Visina nosa u odnosu na liniju ramena: ~-0.5 normalno, ~-0.15 glava dole, >0 pao napred."""
        return self.rel(self.kp[NOSE])[1]

    def wrist_to_head(self):
        if not self.wrists or not self.head:
            return 9.0
        return min(_d(w, h) for w in self.wrists for h in self.head) / self.sw


# ---------- telefon: YOLO + filter ----------
def phone_ok(box, pose):
    """
    Telefon se računa samo ako je blizu glave (poziv) ili U ŠACI (kucanje).
    Odbacuje: pametni sat na podignutoj ruci (u visini ramena, daleko od glave) i telefon
    odložen u konzolu (daleko i od šake i od glave).
    """
    if pose is None:
        return True
    c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    d_head = min([_d(c, h) for h in pose.head], default=99) / pose.sw
    d_wrist = min([_d(c, w) for w in pose.wrists], default=99) / pose.sw
    if d_head < 0.8:
        return True
    if pose.rel(c)[1] < 0.3:            # u visini ramena/gornjih grudi, a daleko od glave -> nije
        return False                    # telefon u upotrebi (sat na podignutoj ruci u 085956)
    if not pose.wrists:
        return False
    w = min(pose.wrists, key=lambda w: _d(c, w))
    if pose.rel(w)[1] < 0.15:           # ruka podignuta do/iznad ramena, a nije uz glavu:
        return False                    # posezanje ka kameri/štitniku (sat u 085956)
    return 0.35 < d_wrist < 1.2


def yolo_phone_prob(phones, pose):
    """phones: [[x1,y1,x2,y2,conf], ...]. YOLO conf na fisheye isečku je nizak (0.15-0.7),
    pa ga skaliramo: conf 0.30 i više -> 1.0."""
    best = max([p[4] for p in phones if phone_ok(p, pose)], default=0.0)
    return min(1.0, best / 0.30)


# ---------- poza ----------
def pose_call_prob(pose):
    """Ručni zglob uz uvo/nos: 0.75 sw ili bliže -> 1, 0.95 sw ili dalje -> 0."""
    return 0.0 if pose is None else ramp(pose.wrist_to_head(), 0.95, 0.75)


def pose_typing_prob(pose):
    """Glava spuštena + jedna šaka nisko i ka konzoli (ne na volanu)."""
    if pose is None:
        return 0.0
    ns = pose.nose_sh
    if ns > 0.15:                       # glava ispod ramena = kolaps, ne kucanje
        return 0.0
    head_down = ramp(ns, -0.40, -0.22)
    low_console = 0.0
    for w in pose.wrists:
        x, y = pose.rel(w)
        if 0.6 <= y <= 1.7:             # u visini krila/konzole
            low_console = max(low_console, ramp(x, -0.20, -0.50))
    return min(head_down, low_console)


def collapse_prob(pose):
    """Nos ispod linije ramena (vozač pao napred na volan): +0.10 sw -> 0, +0.30 sw -> 1.
    Sam po sebi nije dovoljan - DriverLogic dodaje uslove: telo miruje i nema telefona u ruci."""
    return 0.0 if pose is None else ramp(pose.nose_sh, 0.10, 0.30)


# ---------- lice (MediaPipe): kalibracija, look_away, drowsy ----------
# Rezervni neutralni položaj po seriji kamere (yaw, pitch, eyes) ako kalibracija ne uspe
# za 15 s. Izmereno na test klipovima - grubo.
SERIES_PRIOR = {"08_14": (29.0, 12.0, 0.25), "05_23": (22.0, 17.0, 0.27)}


class FaceCalib:
    """
    Neutralni položaj glave i očiju = medijana "mirnih" frejmova:
    lice nađeno, obe šake ispod ramena i daleko od glave, nema signala telefona,
    i vozač je tako miran bar 1 s bez prekida (da ne uhvatimo kraj pokreta).
    - prva procena posle 3 s (ako ima >= 10 mirnih frejmova; inače čeka do 15 s, pa rezervna vrednost serije)
    - posle toga se STALNO osvežava (medijana poslednjih 60 s mirnih frejmova, svake 1 s).
      Razlog: na celom datasetu jednokratna kalibracija iz prvih 3 s je uhvatila vozača dok gleda
      u stranu / vezuje pojas, pa je cela vožnja izgledala kao "pogled sa puta" (05_23_62_011549: skor 0).
    """
    WINDOW, MAX_WINDOW, MIN_SAMPLES, SETTLE, KEEP_S, REFRESH_S = 3.0, 15.0, 10, 1.0, 60.0, 1.0

    def __init__(self, series):
        self.prior = SERIES_PRIOR.get(series, (25.0, 12.0, 0.25))
        self.samples, self.neutral, self.source = [], None, None
        self.calm_since, self.last_refresh = None, -1e9

    def _median(self):
        n = len(self.samples)
        return tuple(sorted(s[k] for s in self.samples)[n // 2] for k in (1, 2, 3))

    def update(self, t, face, pose, phone_like):
        calm = (face is not None and pose is not None and phone_like < 0.3
                and all(pose.rel(w)[1] > 0.3 for w in pose.wrists)
                and pose.wrist_to_head() > 1.0)
        if not calm:
            self.calm_since = None
        elif self.calm_since is None:
            self.calm_since = t
        if calm and t - self.calm_since >= self.SETTLE:
            self.samples.append((t, face["yaw"], face["pitch"], (face["blinkL"] + face["blinkR"]) / 2))
            while self.samples and self.samples[0][0] < t - self.KEEP_S:
                self.samples.pop(0)
        if t - self.last_refresh < self.REFRESH_S:
            return
        self.last_refresh = t
        if len(self.samples) >= self.MIN_SAMPLES and t >= self.WINDOW:
            self.neutral = self._median()
            self.source = f"auto, neprekidno (poslednja: {len(self.samples)} mirnih frejmova u {t:.1f}s)"
        elif self.neutral is None and t >= self.MAX_WINDOW:
            self.neutral, self.source = self.prior, "rezervna vrednost serije"


def look_away_prob(face, calib):
    """Ugao glave od neutralnog: 15° -> 0, 30° -> 1 (kombinovano yaw + pitch)."""
    if face is None or calib.neutral is None:
        return 0.0
    dy, dp = face["yaw"] - calib.neutral[0], face["pitch"] - calib.neutral[1]
    return ramp(math.hypot(dy, dp), 15.0, 30.0)


def drowsy_prob(face, calib):
    """Zatvorene oči u odnosu na lični nivo iz kalibracije.
    Isključeno kad je glava spuštena > 12° (kamera odozgo tada vidi kapke kao zatvorene)."""
    if face is None or calib.neutral is None:
        return 0.0
    if face["pitch"] - calib.neutral[1] > 12.0:
        return 0.0
    eyes = (face["blinkL"] + face["blinkR"]) / 2
    return ramp(eyes - calib.neutral[2], 0.25, 0.45)


# ---------- spajanje svega po frejmu ----------
class DriverLogic:
    """
    Stanje kroz vreme + sva pravila. Jedan poziv po obrađenom frejmu:
        probs, sig = logic.update(t, kp, phones, face)
    Isti kod koristi pipeline.py (uživo) i tuning skripte (nad sačuvanim sirovim vrednostima).
    """
    PHONE_MEMORY_S = 3.0     # koliko dugo važi YOLO potvrda da telefon postoji
    POSE_ONLY_CAP = 0.5      # poza bez potvrde ne može preko praga 0.6 ...
    TYPING_SUSTAIN_S = 4.0   # ... osim ako se poza kucanja drži bar 4 s (telefon na konzoli koji YOLO ne vidi)
    FACE_HOLD_S = 1.0        # ako lice nestane, zadrži poslednju vrednost do 1 s
    MOTION_WINDOW_S = 1.0

    def __init__(self, series):
        self.calib = FaceCalib(series)
        self.last_phone_t = -1e9
        self.typing_since = None
        self.last_face, self.last_face_t = None, -1e9
        self.track = []          # (t, cx, cy, sw) centra ramena za meru mirovanja

    def _motion(self, t, pose):
        """Pomeraj centra ramena u poslednjih ~1 s, u širinama ramena."""
        self.track = [p for p in self.track if p[0] >= t - self.MOTION_WINDOW_S - 0.05]
        if pose is None:
            return None
        self.track.append((t, pose.cx, pose.cy, pose.sw))
        t0, x0, y0, _ = self.track[0]
        if t - t0 < self.MOTION_WINDOW_S * 0.7:
            return None
        return math.hypot(pose.cx - x0, pose.cy - y0) / pose.sw

    def update(self, t, kp, phones, face):
        pose = Pose(kp) if kp else None
        if face is not None:
            self.last_face, self.last_face_t = face, t
        elif t - self.last_face_t <= self.FACE_HOLD_S:
            face = self.last_face

        yolo = yolo_phone_prob(phones, pose)
        if yolo >= 0.5:
            self.last_phone_t = t
        confirmed = t - self.last_phone_t <= self.PHONE_MEMORY_S
        cap = 1.0 if confirmed else self.POSE_ONLY_CAP
        typing = pose_typing_prob(pose)
        if typing >= 0.6:
            self.typing_since = self.typing_since if self.typing_since is not None else t
        else:
            self.typing_since = None
        typing_long = self.typing_since is not None and t - self.typing_since >= self.TYPING_SUSTAIN_S
        sig = {"yolo_phone": yolo,
               "pose_call": min(cap, pose_call_prob(pose)),
               "pose_typing": typing if typing_long else min(cap, typing),
               "phone_confirmed": float(confirmed)}
        phone = max(sig["yolo_phone"], sig["pose_call"], sig["pose_typing"])

        # kolaps: glava pala ispod ramena + telo MIRUJE + nema telefona u ruci
        # (izlazak iz auta i saginjanje nad telefonom u krilu su davali lažne hitne alarme)
        motion = self._motion(t, pose)
        still = 0.0 if motion is None else ramp(motion, 0.30, 0.15)
        coll = 0.0 if confirmed else collapse_prob(pose) * still
        sig["motion"] = -1.0 if motion is None else motion

        self.calib.update(t, face, pose, phone)
        face_ok = coll < 0.5 and (pose is None or pose.nose_sh < 0.15)   # pognut napred: uglovi lica nisu pouzdani
        probs = {"phone": phone,
                 "look_away": look_away_prob(face, self.calib) if face_ok else 0.0,
                 "drowsy": drowsy_prob(face, self.calib) if face_ok else 0.0,
                 "collapse": coll}
        return probs, sig, pose, face
