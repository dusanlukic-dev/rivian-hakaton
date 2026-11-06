"""Stream a camera into the coordinator: one JPEG per WebSocket message to /api/v1/camera/ws.

Stands in for the car's cabin camera. Decoding is done by the ffmpeg that ships with the backend's
`imageio-ffmpeg`, so it runs in the backend venv with nothing else installed:

    backend/.venv/Scripts/python.exe tools/camera_stream.py                       # moving test pattern
    backend/.venv/Scripts/python.exe tools/camera_stream.py --video clip.mp4      # a cabin clip, looped, real time
    backend/.venv/Scripts/python.exe tools/camera_stream.py --list-webcams        # Windows webcams (DirectShow)
    backend/.venv/Scripts/python.exe tools/camera_stream.py --webcam "Integrated Camera"

Frames are dropped by the coordinator while no trip is active, so it can run all the time. It reconnects on
its own when the backend restarts. Defaults: 10 fps (what the CV pipeline processes: every 3rd frame of 30),
1280 px wide (the driver crop stays big enough for YOLO's 640 px input).
"""

import argparse
import asyncio
import re
import sys
import time

import imageio_ffmpeg
from websockets.asyncio.client import connect

DEFAULT_URL = "ws://127.0.0.1:8000/api/v1/camera/ws"


def ffmpeg_command(args: argparse.Namespace) -> list[str]:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    if args.webcam:
        source = ["-f", "dshow", "-rtbufsize", "64M", "-i", f"video={args.webcam}"]
    elif args.video:
        source = ["-re", "-stream_loop", "-1", "-i", args.video]  # real time, looped
    else:
        source = ["-re", "-f", "lavfi", "-i", f"testsrc=size={args.width}x{args.width * 3 // 4}:rate={args.fps}"]
    return [
        exe, "-hide_banner", "-loglevel", "error", *source,
        "-vf", f"fps={args.fps},scale={args.width}:-2",
        "-f", "mpjpeg", "-c:v", "mjpeg", "-q:v", str(args.quality), "-",
    ]


async def frames(command: list[str]):
    """JPEGs from ffmpeg's multipart output (each part has a Content-length header)."""
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE)
    try:
        while True:
            length = None
            while True:  # part headers, up to the blank line
                line = await process.stdout.readline()
                if not line:
                    return
                line = line.strip()
                if not line and length is not None:
                    break
                match = re.match(rb"content-length:\s*(\d+)", line, re.IGNORECASE)
                if match:
                    length = int(match.group(1))
            yield await process.stdout.readexactly(length)
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def stream(args: argparse.Namespace) -> None:
    delay = 1.0
    while True:
        try:
            async with connect(args.url, max_size=None, ping_interval=20) as ws:
                print(f"Streaming to {args.url} at {args.fps} fps, {args.width} px wide (Ctrl+C stops)")
                delay = 1.0
                sent, size, since = 0, 0, time.monotonic()
                async for jpeg in frames(ffmpeg_command(args)):
                    await ws.send(jpeg)
                    sent += 1
                    size += len(jpeg)
                    if time.monotonic() - since >= 10:
                        elapsed = time.monotonic() - since
                        print(f"  {sent / elapsed:4.1f} fps, {size / sent / 1024:5.0f} KB/frame")
                        sent, size, since = 0, 0, time.monotonic()
                print("The video source ended")
                return
        except (OSError, Exception) as e:  # backend down or restarting: try again
            if isinstance(e, KeyboardInterrupt):
                raise
            print(f"Coordinator unreachable ({type(e).__name__}: {e}); retrying in {delay:.0f} s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)


def list_webcams() -> None:
    import subprocess

    out = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True, text=True, errors="replace",
    )
    names = re.findall(r'"([^"]+)"\s+\(video\)', out.stderr)
    print("\n".join(names) if names else "No DirectShow video devices found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream a camera (or a stand-in) to the coordinator.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--video", help="a video file, looped in real time")
    parser.add_argument("--webcam", help="a DirectShow device name (see --list-webcams)")
    parser.add_argument("--list-webcams", action="store_true")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--quality", type=int, default=4, help="ffmpeg -q:v, 2 (best) .. 31")
    args = parser.parse_args()
    if args.list_webcams:
        list_webcams()
        sys.exit(0)
    try:
        asyncio.run(stream(args))
    except KeyboardInterrupt:
        pass
