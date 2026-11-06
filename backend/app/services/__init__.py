"""Shared computations outside the coordinator/server split.

`model_report.py` builds the camera model's whole-trip report from its frame stream. The coordinator uses it live,
and the CV team imports it from notebooks/risk_pipeline.py (dev mode) and runs it offline:
`python -m app.services.model_report <frames.jsonl>`. Keep it at this path.
"""
