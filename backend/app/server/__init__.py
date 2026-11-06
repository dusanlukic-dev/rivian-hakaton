"""The server: the storage and report half of the backend (docs/ARCHITECTURE.md).

Owns Postgres (accounts, trips, sections) and S3 (images). Takes the coordinator's deliveries on /internal/*
and serves the apps: login, history, the drive report with its chart data and images, analytics.
"""
