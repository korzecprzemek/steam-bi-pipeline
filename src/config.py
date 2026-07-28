from __future__ import annotations

import os


GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

BIGQUERY_DATASET = os.getenv(
    "BIGQUERY_DATASET",
    "steam_analytics",
)

BIGQUERY_TABLE = os.getenv(
    "BIGQUERY_TABLE",
    "games_snapshot",
)

BIGQUERY_LOCATION = os.getenv(
    "BIGQUERY_LOCATION",
    "EU",
)