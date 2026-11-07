"""Shared computations outside the coordinator/server split.

`model_report.py` builds the camera model's whole-trip report from its frame stream. The coordinator uses it live;
offline: `python -m app.services.model_report <frames.jsonl>`.
"""
