"""MP4 clips from buffered camera JPEGs.

ffmpeg comes with the `imageio-ffmpeg` wheel (H.264 included), so nothing has to be installed on
the laptop. The JPEGs are piped in as they are, without decoding them in Python.
"""

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

MIN_FPS, MAX_FPS = 1.0, 30.0


def is_jpeg(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff"


def clip_fps(frame_times: list[float]) -> float:
    """Average frame rate of the buffered frames (they arrive at whatever rate the camera side sends)."""
    if len(frame_times) < 2 or frame_times[-1] <= frame_times[0]:
        return 10.0
    fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
    return min(max(fps, MIN_FPS), MAX_FPS)


def encode_mp4(frames: list[bytes], fps: float) -> bytes:
    """H.264 MP4 that phones and browsers play inline (yuv420p, moov atom up front)."""
    with tempfile.TemporaryDirectory(prefix="safety-clip-") as tmp:
        out = Path(tmp) / "clip.mp4"
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner", "-loglevel", "error",
            "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", f"{fps:.3f}", "-i", "-",
            # Even dimensions (H.264 needs them) and TV range: camera JPEGs are full range ("yuvj"),
            # which some players show washed out.
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-an",
            str(out),
        ]
        subprocess.run(
            command,
            input=b"".join(frames),
            capture_output=True,
            check=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no console popup on Windows
        )
        return out.read_bytes()
