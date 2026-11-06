"""The coordinator: the in-car half of the backend (docs/ARCHITECTURE.md).

Owns everything live: the phone/dashboard WebSocket, the camera stream, the link to the model worker, the
risk engine and the 0-100 score, the car's reaction, the 5 min video cache and the 2 s section summaries it
delivers to the server. Never touches Postgres or S3.
"""
