"""Run the API for the in-car demo.

Listens on every network interface so the phone can reach the laptop over the mobile
hotspot, and prints the address to put into the app (a hotspot has no DNS).

    python run.py            # port 8000
    python run.py --port 9000
"""

import argparse
import socket

import uvicorn


def lan_ip() -> str:
    """IP of the interface with the default route - on a hotspot, the one the phone sees."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))  # UDP connect sends no packets; it only picks the interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    ip = lan_ip()
    print(
        "\n  Mobile app:\n"
        f"    REST       http://{ip}:{args.port}/api/v1\n"
        f"    WebSocket  ws://{ip}:{args.port}/api/v1/ws\n"
        f"  Camera models (same laptop): http://127.0.0.1:{args.port}/api/v1/telemetry\n"
    )
    uvicorn.run("app.main:app", host="0.0.0.0", port=args.port, reload=True, reload_dirs=["app"])
