"""
sender.py - slanje poruka backendu po ugovoru v1 (ARHITEKTURA.md, sekcija 5).

- Radi u posebnoj niti: petlja sa modelima NIKAD ne čeka mrežu
  (alarm u autu ne sme da zavisi od interneta).
- Svaka poruka se čuva dok backend ne potvrdi upis:
  {"v": 1, "type": "ack", "trip_id": "...", "data": {"seq": n}} = sve do n je upisano.
- Kad veza pukne, nit pokušava ponovo svake 2 s i šalje sve što nije potvrđeno
  (backend po trip_id + seq izbacuje duplikate).
- Na kraju vožnje close() čeka potvrde najviše nekoliko sekundi i vraća nepotvrđene poruke
  (pipeline.py ih čuva u unsent.jsonl, da se ne izgube).
"""
import json
import threading
import time
import datetime as dt
from collections import OrderedDict
from urllib.parse import urlparse

PROTOCOL_VERSION = 1


def utc_iso(ts=None):
    """Vreme u UTC, ISO 8601 sa milisekundama: 2026-11-06T18:00:04.100Z"""
    d = dt.datetime.now(dt.timezone.utc) if ts is None else dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normalize_url(url):
    """'localhost' -> '127.0.0.1'. Na Windowsu 'localhost' prvo ide na IPv6 (::1); ako backend sluša
    samo na IPv4 (uvicorn podrazumevano, mock_backend.py), taj pokušaj traje ~2 s i veza ne uspe."""
    u = urlparse(url)
    if u.hostname == "localhost":
        return u._replace(netloc=u.netloc.replace("localhost", "127.0.0.1", 1)).geturl()
    return url


def api_base_from_ws(url):
    """ws://host:8000/ingest -> http://host:8000 (adresa za REST pozive istog backenda)."""
    u = urlparse(normalize_url(url))
    return f"{'https' if u.scheme == 'wss' else 'http'}://{u.netloc}"


class Sender:
    RECONNECT_S = 2.0     # koliko često pokušavamo ponovo kad backend nije dostupan
    POLL_S = 0.02         # koliko dugo čekamo ack u jednom krugu

    def __init__(self, url, trip_id):
        from websockets.sync.client import connect     # treba samo kad se šalje
        self._connect = connect
        self.url, self.trip_id = normalize_url(url), trip_id
        self.seq = 0
        self.pending = OrderedDict()                   # seq -> JSON tekst, čeka ack
        self.lock = threading.Lock()
        self.stopping, self.deadline = False, None
        self.stats = {"messages": 0, "acked_upto": -1, "connects": 0, "disconnects": 0, "last_error": None}
        self.thread = threading.Thread(target=self._run, name="sender", daemon=True)
        self.thread.start()

    # ---------- poziva glavna nit (pipeline) ----------
    def send(self, typ, data):
        """Ne čeka mrežu: samo stavi poruku u red."""
        msg = {"v": PROTOCOL_VERSION, "type": typ, "trip_id": self.trip_id, "seq": self.seq,
               "sent_at": utc_iso(), "data": data}
        text = json.dumps(msg, ensure_ascii=False)
        with self.lock:
            self.pending[self.seq] = text
            self.stats["messages"] += 1
        self.seq += 1

    def close(self, wait_s=5.0):
        """Čeka potvrdu svih poruka najviše wait_s sekundi; vraća nepotvrđene poruke (JSON tekst)."""
        with self.lock:
            self.stopping, self.deadline = True, time.monotonic() + wait_s
        self.thread.join(wait_s + 3.0)
        with self.lock:
            return list(self.pending.values())

    # ---------- pozadinska nit ----------
    def _ack(self, upto):
        with self.lock:
            for s in [s for s in self.pending if s <= upto]:
                del self.pending[s]
            self.stats["acked_upto"] = max(self.stats["acked_upto"], upto)

    def _run(self):
        ws, sent_upto, last_try = None, -1, -1e9
        while True:
            with self.lock:
                done = self.stopping and (not self.pending or time.monotonic() > self.deadline)
            if done:
                break
            if ws is None:
                if time.monotonic() - last_try < self.RECONNECT_S:
                    time.sleep(self.POLL_S)
                    continue
                last_try = time.monotonic()
                try:
                    ws = self._connect(self.url, open_timeout=3.0, close_timeout=1.0)
                    self.stats["connects"] += 1
                    sent_upto = -1                     # nova veza: ponovo sve što nije potvrđeno
                except Exception as e:
                    self.stats["last_error"] = f"connect: {type(e).__name__}: {e}"
                    ws = None
                    continue
            try:
                with self.lock:
                    batch = [(s, m) for s, m in self.pending.items() if s > sent_upto]
                for s, m in batch:
                    ws.send(m)
                    sent_upto = s
                try:
                    while True:
                        reply = json.loads(ws.recv(timeout=self.POLL_S))
                        if reply.get("type") == "ack":
                            self._ack(int(reply["data"]["seq"]))
                except TimeoutError:
                    pass
            except Exception as e:                     # veza pukla ili čudan odgovor: novi pokušaj
                self.stats["last_error"] = f"{type(e).__name__}: {e}"
                self.stats["disconnects"] += 1
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def post_critical(api_base, trip_id, jpg_path, timeout=5.0):
    """POST /trips/{trip_id}/critical, multipart/form-data, polje "file". Vraća (uspeh, opis)."""
    import requests
    try:
        with open(jpg_path, "rb") as f:
            r = requests.post(f"{normalize_url(api_base)}/trips/{trip_id}/critical",
                              files={"file": ("critical.jpg", f, "image/jpeg")}, timeout=timeout)
        return r.ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:80]}"
