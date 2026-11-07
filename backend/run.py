"""Run the backend for the in-car demo.

Listens on every network interface so the phone can reach the laptop over the mobile hotspot, and prints
the address to put into the app (a hotspot has no DNS).

    python run.py                                   # coordinator + server in one process, port 8000
    python run.py --port 9000
    python run.py --role server --port 8001         # split (the demo): the server alone...
    SERVER_URL=http://127.0.0.1:8001/api/v1 python run.py --role coordinator   # ...and the coordinator alone

The car's other parts are their own processes: the model (rivian_model/rivian_detector.py, its own venv) and the
camera (tools/camera_stream.py). ../demo.ps1 starts all of them, each in its own window.
"""

import argparse
import socket
import subprocess
import sys

import uvicorn

APPS = {"all": "app.main:app", "coordinator": "app.coordinator.main:app", "server": "app.server.main:app"}


def port_owner(port: int) -> str:
    """' (PID 1234, python.exe)' for whoever listens on the port, Windows only; '' if unknown."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
        pid = next(line.split()[-1] for line in out.splitlines()
                   if "LISTENING" in line and line.split()[1].endswith(f":{port}"))
        name = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                              capture_output=True, text=True, timeout=10).stdout.split(",")[0].strip('"')
        return f" (PID {pid}, {name})"
    except (StopIteration, OSError, subprocess.SubprocessError):
        return ""


def port_problem(port: int) -> str | None:
    """Why the backend couldn't listen on the port, said before uvicorn tries. On Windows both failures are confusing:
    a second process can share a port (an orphaned worker keeps serving old code), and Hyper-V/WSL/Docker reserve
    whole port ranges (WinError 10013, "access forbidden")."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return (f"something already listens on port {port}{port_owner(port)}: an old backend? "
                    "..\\demo.ps1 -Stop stops ours, or pick another --port")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform == "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError as e:
            if getattr(e, "winerror", None) == 10013:
                return (f"Windows reserved port {port} (Hyper-V/WSL/Docker: netsh interface ipv4 show excludedportrange "
                        "protocol=tcp). Once, as administrator: ..\\tools\\reserve-ports.ps1. Or pick another --port")
            return f"port {port} can't be used: {e}"
    return None


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
    if problem := port_problem(args.port):
        sys.exit(f"\n  Can't start: {problem}\n")

    ip, port = lan_ip(), args.port
    lines = [f"\n  Role: {args.role}  (docs/ARCHITECTURE.md)"]
    if args.role in ("all", "coordinator"):
        lines += [
            "  Phone / dashboard:",
            f"    REST       http://{ip}:{port}/api/v1",
            f"    WebSocket  ws://{ip}:{port}/api/v1/ws",
            "  Camera + model (same laptop):",
            f"    camera     ws://127.0.0.1:{port}/api/v1/camera/ws   (python ../tools/camera_stream.py --video <clip>)",
            f"    model      ws://127.0.0.1:{port}/api/v1/model/ws    "
            "(../rivian_model/.venv/Scripts/python.exe ../rivian_model/rivian_detector.py --camera 05_23)",
            f"    simulator  http://127.0.0.1:{port}/api/v1/telemetry (python ../notebooks/safety_client.py)",
            f"    status     http://127.0.0.1:{port}/api/v1/coordinator/status",
        ]
    if args.role in ("all", "server"):
        lines += [
            "  Server storage: Postgres :5433 + RustFS :9000 (docker compose up -d, or .\\scripts\\services.ps1 start)",
        ]
    print("\n".join(lines) + "\n")
    uvicorn.run(APPS[args.role], host="0.0.0.0", port=port, reload=not args.no_reload, reload_dirs=["app"])
