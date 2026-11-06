"""
dev_overlay.py — prikaz za dev mode (risk_pipeline.py --mode dev). Production mode ga ne uvozi.

Levo video sa onim sto model vidi, desno panel samo sa najbitnijim metrikama:

  video   okvir lica vozaca (narandzast kad je pogled van puta) + strelica pravca glave,
          tacke saka (zelena = na volanu, narandzasta = van volana), okvir telefona (YOLO),
          ivica slike u boji alarma. Taster R prikazuje ROI-jeve (driver / head / wheel).
  panel   alarm i rizik 0..1 (crtice = pragovi zuto/crveno), tvrda pravila koja su opalila,
          kategorije (traka = zagladjen dokaz p_hat, crtica = prag "on", ON + trajanje),
          kljucni signali (glava vs put, oci, ruke, telefon) i rizik poslednjih 30 s.

Sve ostale promenljive (p, D, h, r, grupe, PERCLOS...) su u frames.jsonl i u --verbose.
"""
from __future__ import annotations

from collections import deque

import numpy as np

LEVEL_BGR = [(0, 200, 0), (0, 220, 255), (0, 0, 255)]
WHITE, GREY, DIM, ORANGE, MAGENTA = (240, 240, 240), (150, 150, 150), (90, 90, 90), (0, 140, 255), (255, 0, 255)
BG = 28

# Kategorije na panelu, redom. eating_drinking se ne prikazuje: backend ga ne boduje (root CLAUDE.md).
SHOWN = [("phone_use", "phone"), ("eyes_off_road", "eyes off road"), ("hands_off_wheel", "hands off wheel"),
         ("eyes_closed", "eyes closed"), ("drowsiness", "drowsy")]
SHORT = dict(SHOWN) | {"eating_drinking": "eat/drink"}
PHONE_CLS = 67


def _in_box(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


class Overlay:
    def __init__(self, cfg, panel_w=380, history_s=30.0):
        import cv2
        self.cv2, self.cfg, self.pw, self.hist_s = cv2, cfg, panel_w, history_s
        self.hist: deque = deque()
        self.show_roi = False

    # ---------------------------------------------------------------- pomocne
    def _t(self, img, x, y, s, col=WHITE, sc=0.5, th=1):
        self.cv2.putText(img, s, (int(x), int(y)), self.cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, self.cv2.LINE_AA)

    def _bar(self, img, x, y, w, h, v, col, marks=()):
        cv2 = self.cv2
        v = 0.0 if v < 0 else 1.0 if v > 1 else v
        cv2.rectangle(img, (x, y), (x + w, y + h), (55, 55, 55), -1)
        cv2.rectangle(img, (x, y), (x + int(w * v), y + h), col, -1)
        for m, mc in marks:
            mx = x + int(w * m)
            cv2.line(img, (mx, y - 3), (mx, y + h + 3), mc, 2)

    @staticmethod
    def _px(pt, W, H):
        return int(pt[0] * W), int(pt[1] * H)

    def _rect(self, img, box, col, label=None, th=1):
        H, W = img.shape[:2]
        p0, p1 = self._px(box[:2], W, H), self._px(box[2:], W, H)
        self.cv2.rectangle(img, p0, p1, col, th)
        if label:
            self._t(img, p0[0] + 4, p0[1] - 6, label, col, 0.5)

    # ---------------------------------------------------------------- video
    def draw_scene(self, img, rec, face, hands, objects):
        cv2, vc = self.cv2, self.cfg["video"]
        H, W = img.shape[:2]
        wheel = vc["steering_wheel_roi"]
        if self.show_roi:
            self._rect(img, vc["driver_roi"], (200, 200, 0), "driver_roi")
            self._rect(img, vc["head_roi"], (255, 140, 60), "head_roi")
            self._rect(img, wheel, (0, 255, 255), "wheel")
        if face is not None:
            off = rec["categories"].get("eyes_off_road", {}).get("active", False)
            self._rect(img, face["box"], ORANGE if off else (0, 255, 0), None, 2)
            n = self._px(face["center"], W, H)
            fx, fy = face["fwd"]
            cv2.arrowedLine(img, n, (int(n[0] + 90 * fx), int(n[1] - 90 * fy)), (0, 255, 255), 2, tipLength=0.25)
        for h in (hands or []):
            cv2.circle(img, self._px(h["center"], W, H), 8, (0, 255, 0) if _in_box(h["center"], wheel) else ORANGE, -1)
        for o in (objects or []):
            if o["cls"] == PHONE_CLS:
                self._rect(img, o["box"], MAGENTA, f"phone {o['conf']:.2f}", 2)
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), LEVEL_BGR[rec["alert"]["code"]], 8)
        return img

    # ---------------------------------------------------------------- panel
    def draw_panel(self, H, rec, per, info):
        cv2, cfg = self.cv2, self.cfg
        P = np.full((H, self.pw, 3), BG, np.uint8)
        x, w = 14, self.pw - 28
        lv, risk = rec["alert"]["code"], rec["risk"]["final"]

        # alarm + rizik
        y = 40
        cv2.circle(P, (x + 14, y - 8), 14, LEVEL_BGR[lv], -1)
        self._t(P, x + 38, y, rec["alert"]["level"].upper(), LEVEL_BGR[lv], 0.9, 2)
        self._t(P, x + w - 110, y, f"risk {risk:.2f}", WHITE, 0.65, 2)
        y += 16
        al = cfg["alerts"]
        self._bar(P, x, y, w, 14, risk, LEVEL_BGR[lv], [(al["yellow"]["on"], LEVEL_BGR[1]), (al["red"]["on"], LEVEL_BGR[2])])
        y += 38
        rules = rec["rules_triggered"]
        self._t(P, x, y, ("rule: " + ", ".join(rules)) if rules else "no rule fired", LEVEL_BGR[2] if rules else DIM, 0.5,
                2 if rules else 1)

        # kategorije
        y += 34
        self._t(P, x, y, "BEHAVIOR", GREY, 0.45)
        for name, label in SHOWN:
            c = rec["categories"].get(name)
            if c is None:
                continue
            y += 26
            on = c["active"]
            self._t(P, x, y, label, WHITE if on else GREY, 0.5, 2 if on else 1)
            bx = x + 140
            self._bar(P, bx, y - 11, w - 140 - 70, 11, c["p_hat"], ORANGE if on else (130, 130, 130),
                      [(cfg["categories"][name]["on"], WHITE)])
            if on:
                self._t(P, x + w - 62, y, f"ON {c['run_s']:.1f}s", LEVEL_BGR[2], 0.45, 2)

        # kljucni signali
        y += 36
        self._t(P, x, y, "SIGNALS", GREY, 0.45)
        cal = cfg["calibration"]
        y += 24
        if per.get("face_found"):
            away = abs(per["yaw"]) > cal["yaw_thr_deg"] or abs(per["pitch"]) > cal["pitch_thr_deg"]
            self._t(P, x, y, f"head   yaw {per['yaw']:+4.0f}  pitch {per['pitch']:+4.0f}  (vs road)", ORANGE if away else WHITE)
            y += 22
            down = per["gaze_down"] >= cal["gaze_down_thr"]
            closed = per["eye_closure"] >= cal["eye_closed_thr"]
            self._t(P, x, y, f"eyes   closed {per['eye_closure']:.2f}   down {per['gaze_down']:.2f}",
                    ORANGE if (down or closed) else WHITE)
        else:
            self._t(P, x, y, "head   no face found", ORANGE)
            y += 22
            self._t(P, x, y, "eyes   -", DIM)
        y += 22
        on, det = per["hands_on_wheel"], per["hands_detected"]
        self._t(P, x, y, f"hands  {on} on wheel ({det} seen)" if det else "hands  none seen",
                (0, 255, 0) if on >= 2 else ORANGE if det else GREY)
        y += 22
        ph = per.get("phone")
        if ph:
            self._t(P, x, y, f"phone  yolo {ph['conf']:.2f} -> {ph['p']:.2f}", MAGENTA)
        elif per["phone_held"] > 0.05:
            self._t(P, x, y, f"phone  memory {per['phone_held']:.2f}", MAGENTA)
        else:
            self._t(P, x, y, "phone  -", GREY)

        # rizik kroz vreme
        y += 22
        bottom = H - 34
        self._timeline(P, x, y, w, bottom - y, rec)
        self._t(P, x, H - 12, f"t {rec['t']:6.1f} s   {info['fps']:4.1f} fps   {info['ms']:3.0f} ms"
                              f"{'   ROI' if self.show_roi else ''}", DIM, 0.42)
        return P

    def _timeline(self, P, x, y, w, h, rec):
        cv2 = self.cv2
        t = rec["t"]
        self.hist.append((t, rec["risk"]["final"], rec["alert"]["code"]))
        while self.hist and self.hist[0][0] < t - self.hist_s:
            self.hist.popleft()
        if h < 40:
            return
        cv2.rectangle(P, (x, y), (x + w, y + h), (40, 40, 40), -1)
        al = self.cfg["alerts"]
        for v, col in ((al["yellow"]["on"], LEVEL_BGR[1]), (al["red"]["on"], LEVEL_BGR[2])):
            yy = y + h - int(v * h)
            cv2.line(P, (x, yy), (x + w, yy), col, 1)

        def X(tt):
            return x + int(w * (1 - (t - tt) / self.hist_s))

        pts = [(X(tt), y + h - int(R * h), lv) for tt, R, lv in self.hist]
        for (x0, y0, _), (x1, y1, lv) in zip(pts, pts[1:]):
            cv2.line(P, (x0, y0), (x1, y1), LEVEL_BGR[lv], 2, cv2.LINE_AA)
        self._t(P, x + 6, y + 18, f"risk, last {self.hist_s:.0f} s", GREY, 0.42)

    def render(self, frame, rec, per, face, hands, objects, info):
        img = self.draw_scene(frame.copy(), rec, face, hands, objects)
        return np.hstack([img, self.draw_panel(img.shape[0], rec, per, info)])


def verbose_line(rec, per):
    """Jedan red po obradjenom frejmu (--verbose): p/r svih kategorija, glava, ruke, telefon."""
    c = rec["categories"]
    cats = " ".join(f"{SHORT.get(n, n).split()[0]}={v['p']:.2f}/{v['r']:.2f}{'*' if v['active'] else ''}"
                    for n, v in c.items())
    face = (f"face yaw{per['yaw']:+.0f} pitch{per['pitch']:+.0f} gd{per['gaze_down']:.2f} cl{per['eye_closure']:.2f}"
            if per["face_found"] else "face --")
    return (f"t={rec['t']:6.2f} R={rec['risk']['final']:.2f} {rec['alert']['level']:6s} | {cats} | {face} | "
            f"hands {per['hands_detected']}/{per['hands_on_wheel']} | phone {per['phone_now']:.2f}")
