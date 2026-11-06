"""The server alone (split deployment): `python run.py --role server --port 8001`."""

from app.main import create_app

app = create_app("server")
