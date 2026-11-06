"""Run the backend for the in-car demo.

Listens on every network interface so the phone can reach the laptop over the mobile hotspot, and prints
the address to put into the app (a hotspot has no DNS).

    python run.py                                   # coordinator + server in one process, port 8000 (the demo)
    python run.py --port 9000
    python run.py --role server --port 8001         # split: the server alone...
    SERVER_URL=http://127.0.0.1:8001/api/v1 python run.py --role coordinator   # ...and the coordinator alone
"""

import argparse
import socket

import uvicorn

APPS = {"all": "app.main:app", "coordinator": "app.coordinator.main:app", "server": "app.server.main:app"}


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
    parser.add_argument("--role", choices=sorted(APPS), default="all", help="both parts (default) or one of them")
    parser.add_argument("--no-reload", action="store_true", help="don't restart on code changes")
    args = parser.parse_args()

    ip, port = lan_ip(), args.port
    lines = [f"\n  Role: {args.role}  (docs/ARCHITECTURE.md)"]
    if args.role in ("all", "coordinator"):
        lines += [
            "  Phone / dashboard:",
            f"    REST       http://{ip}:{port}/api/v1",
            f"    WebSocket  ws://{ip}:{port}/api/v1/ws",
            "  Camera + model (same laptop):",
            f"    camera     ws://127.0.0.1:{port}/api/v1/camera/ws   (python ../tools/camera_stream.py)",
            f"    model      ws://127.0.0.1:{port}/api/v1/model/ws    (python ../model/worker.py)",
            f"    simulator  http://127.0.0.1:{port}/api/v1/telemetry (python ../notebooks/safety_client.py)",
            f"    status     http://127.0.0.1:{port}/api/v1/coordinator/status",
        ]
    if args.role in ("all", "server"):
        lines += [
            "  Server storage: Postgres :5433 + RustFS :9000 (docker compose up -d, or .\\scripts\\services.ps1 start)",
        ]
    print("\n".join(lines) + "\n")
    uvicorn.run(APPS[args.role], host="0.0.0.0", port=port, reload=not args.no_reload, reload_dirs=["app"])
