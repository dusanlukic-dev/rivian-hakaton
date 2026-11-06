"""The coordinator alone (split deployment): `python run.py --role coordinator` with SERVER_URL set."""

from app.main import create_app

app = create_app("coordinator")
