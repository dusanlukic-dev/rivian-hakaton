"""The coordinator's video cache: the last few minutes of camera frames, to pull the image of a dangerous moment.

    camera frame (JPEG) ──► add(frame_id, wall, jpeg) ──► index in memory (wall clock -> frame id)
                                                      └─► bytes: disk (diskcache) or memory, at most `max_fps`
    dangerous section closes ──► get(peak frame id) or nearest(peak time) ──► JPEG for the section summary

A rolling window, not a queue: frames older than `retention_s` (5 min), or past `max_mb`, are deleted oldest
first; nothing is ever sent anywhere from here. Only the image of a dangerous section is copied out (into the
section, which goes to the server through the outbox) when the section closes, 2 s after it started, so it never
depends on the window. Trimming runs on every stored frame and on the coordinator's housekeeping (`expire`), so
frames also age out after the camera stops. Frames are stored only while a trip is active. Disk mode uses diskcache (SQLite index
+ one file per frame, a library built for exactly this kind of bounded cache) in a temp folder that is wiped on
start: frame ids restart with the process. Writes go through one worker thread, so the event loop (the live
score) never waits for the disk; frames not written yet are still served from memory.

`frames_between()` is there for the planned "video of the whole moment" (encode with `video.encode_mp4`).
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from bisect import bisect_left
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class _Store(Protocol):
    def put(self, frame_id: int, jpeg: bytes) -> None: ...
    def get(self, frame_id: int) -> bytes | None: ...
    def drop(self, frame_ids: list[int]) -> None: ...
    def close(self) -> None: ...


class _MemoryStore:
    def __init__(self) -> None:
        self._frames: dict[int, bytes] = {}
        self._lock = threading.Lock()

    def put(self, frame_id: int, jpeg: bytes) -> None:
        with self._lock:
            self._frames[frame_id] = jpeg

    def get(self, frame_id: int) -> bytes | None:
        with self._lock:
            return self._frames.get(frame_id)

    def drop(self, frame_ids: list[int]) -> None:
        with self._lock:
            for frame_id in frame_ids:
                self._frames.pop(frame_id, None)

    def close(self) -> None:
        with self._lock:
            self._frames.clear()


class _DiskStore:
    def __init__(self, path: Path, max_bytes: int, retention_s: float) -> None:
        import diskcache  # only needed in disk mode

        shutil.rmtree(path, ignore_errors=True)  # frames of an earlier run are useless (ids restart)
        path.mkdir(parents=True, exist_ok=True)
        # FIFO eviction by size on top of our own time-based trimming; expire is a safety net.
        self._cache = diskcache.Cache(
            str(path), size_limit=max_bytes, eviction_policy="least-recently-stored", cull_limit=50
        )
        self._expire = retention_s + 60

    def put(self, frame_id: int, jpeg: bytes) -> None:
        self._cache.set(frame_id, jpeg, expire=self._expire)

    def get(self, frame_id: int) -> bytes | None:
        value = self._cache.get(frame_id)
        return value if isinstance(value, bytes) else None

    def drop(self, frame_ids: list[int]) -> None:
        for frame_id in frame_ids:
            self._cache.delete(frame_id)

    def close(self) -> None:
        self._cache.close()


class VideoCache:
    def __init__(
        self,
        mode: str = "memory",
        path: Path | None = None,
        retention_s: float = 300.0,
        max_fps: float = 10.0,
        max_mb: int = 1024,
        clock=time.monotonic,
    ) -> None:
        self.mode = mode
        self.retention_s = retention_s
        self.min_gap_s = 1.0 / max_fps if max_fps > 0 else 0.0
        self.max_bytes = max_mb * 1024 * 1024
        self._path = path
        self._clock = clock
        self._store: _Store | None = None
        self._writer: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._index: deque[tuple[float, int, int]] = deque()  # (wall, frame_id, size), oldest first
        self._walls: deque[float] = deque()  # same order, for bisect
        self._unwritten: OrderedDict[int, bytes] = OrderedDict()  # handed to the writer, not on disk yet
        self._bytes = 0
        self._last_stored_wall = float("-inf")
        self._next_id = 0

    # ---- lifecycle ----

    def open(self) -> None:
        if self._store is not None:
            return
        if self.mode == "disk" and self._path is not None:
            try:
                self._store = _DiskStore(self._path, self.max_bytes, self.retention_s)
                self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-cache")
                logger.info("Video cache on disk: %s (%.0f s, %d MB max)", self._path, self.retention_s, self.max_bytes >> 20)
                return
            except Exception as e:  # diskcache missing or the folder isn't writable
                logger.warning("Video cache can't use %s (%s); keeping frames in memory", self._path, e)
        self.mode = "memory"
        self._store = _MemoryStore()

    def close(self) -> None:
        if self._writer is not None:
            self._writer.shutdown(wait=True, cancel_futures=True)
            self._writer = None
        if self._store is not None:
            self._store.close()
            self._store = None
        with self._lock:
            self._index.clear()
            self._walls.clear()
            self._unwritten.clear()
            self._bytes = 0

    # ---- writing ----

    def new_frame_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def wants(self, wall: float) -> bool:
        """True if a frame arriving now should be stored (keeps the cache at `max_fps`).

        5 % slack: a camera at exactly `max_fps` has gaps like 0.09999 s, which must not skip every other frame.
        """
        return wall - self._last_stored_wall >= self.min_gap_s * 0.95

    def add(self, frame_id: int, wall: float, jpeg: bytes) -> None:
        if self._store is None:
            self.open()
        with self._lock:
            if self._contains(frame_id):
                return
            # Usually appended at the end; the frame sent to the model may be stored a little later than newer
            # frames, so insert by time to keep the index sorted for bisect.
            i = bisect_left(self._walls, wall)
            self._index.insert(i, (wall, frame_id, len(jpeg)))
            self._walls.insert(i, wall)
            self._bytes += len(jpeg)
            self._last_stored_wall = max(self._last_stored_wall, wall)
            dropped = self._trim(wall)
        if self._writer is None:
            self._store.put(frame_id, jpeg)
        else:
            with self._lock:
                self._unwritten[frame_id] = jpeg
            self._writer.submit(self._write, frame_id, jpeg)
        if dropped:
            self._forget(dropped)

    def _write(self, frame_id: int, jpeg: bytes) -> None:
        try:
            self._store.put(frame_id, jpeg)
        except Exception as e:
            logger.warning("Video cache write failed (%s)", e)
        finally:
            with self._lock:
                self._unwritten.pop(frame_id, None)

    def expire(self, now: float | None = None) -> None:
        """Drop what is older than the window now, not only when the next frame arrives (camera stopped)."""
        with self._lock:
            dropped = self._trim(self._clock() if now is None else now)
        if dropped and self._store is not None:
            self._forget(dropped)

    def _trim(self, now: float) -> list[int]:
        dropped = []
        while self._index and (self._index[0][0] < now - self.retention_s or self._bytes > self.max_bytes):
            _, frame_id, size = self._index.popleft()
            self._walls.popleft()
            self._bytes -= size
            dropped.append(frame_id)
        return dropped

    def _forget(self, frame_ids: list[int]) -> None:
        if self._writer is None:
            self._store.drop(frame_ids)
        else:
            self._writer.submit(self._store.drop, frame_ids)

    def _contains(self, frame_id: int) -> bool:
        return any(entry[1] == frame_id for entry in reversed(self._index))

    # ---- reading ----

    def has(self, frame_id: int) -> bool:
        with self._lock:
            return self._contains(frame_id)

    def get(self, frame_id: int) -> bytes | None:
        with self._lock:
            pending = self._unwritten.get(frame_id)
            known = pending is not None or self._contains(frame_id)
        if pending is not None:
            return pending
        if not known or self._store is None:
            return None
        try:
            return self._store.get(frame_id)
        except Exception as e:
            logger.warning("Video cache read failed (%s)", e)
            return None

    def nearest(self, wall: float, max_gap_s: float = 1.0) -> tuple[int, float] | None:
        """(frame_id, wall) of the stored frame closest to `wall`, if one is within `max_gap_s`."""
        with self._lock:
            if not self._walls:
                return None
            i = bisect_left(self._walls, wall)
            best = None
            for j in (i - 1, i):
                if 0 <= j < len(self._index):
                    w, frame_id, _ = self._index[j]
                    if best is None or abs(w - wall) < abs(best[1] - wall):
                        best = (frame_id, w)
        if best is None or abs(best[1] - wall) > max_gap_s:
            return None
        return best

    def frames_between(self, start: float, end: float) -> list[tuple[float, bytes]]:
        """Stored frames with start <= wall <= end, oldest first (for clips of a whole moment)."""
        with self._lock:
            entries = [(w, frame_id) for w, frame_id, _ in self._index if start <= w <= end]
        out = []
        for w, frame_id in entries:
            jpeg = self.get(frame_id)
            if jpeg is not None:
                out.append((w, jpeg))
        return out

    def stats(self) -> dict:
        with self._lock:
            span = self._index[-1][0] - self._index[0][0] if len(self._index) > 1 else 0.0
            return {
                "mode": self.mode,
                "frames": len(self._index),
                "seconds": round(span, 1),
                "mb": round(self._bytes / (1024 * 1024), 1),
                "retention_s": self.retention_s,
            }
