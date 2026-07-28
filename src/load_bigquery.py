from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from src.config import (
    BIGQUERY_DATASET,
    BIGQUERY_LOCATION,
    BIGQUERY_TABLE,
    GOOGLE_CLOUD_PROJECT,
)


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"
PROCESSED_FILE_PATTERN = "steam_games_transformed_*.csv"


class BigQueryLoadError(RuntimeError):
    """Raised when Steam data cannot be loaded into BigQuery."""


def configure_logging() -> None:
    """Configure application logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def validate_configuration() -> None:
    """Validate required BigQuery configuration."""

    if not GOOGLE_CLOUD_PROJECT:
        raise BigQueryLoadError(
            "GOOGLE_CLOUD_PROJECT environment variable is not set."
        )


def find_latest_processed_file(
    processed_directory: Path = PROCESSED_DATA_DIRECTORY,
) -> Path:
    """Return the newest transformed CSV file."""

    if not processed_directory.exists():
        raise BigQueryLoadError(
            f"Processed directory does not exist: {processed_directory}"
        )

    processed_files = list(
        processed_directory.glob(PROCESSED_FILE_PATTERN)
    )

    if not processed_files:
        raise BigQueryLoadError(
            f"No files matching '{PROCESSED_FILE_PATTERN}' "
            f"were found in {processed_directory}"
        )

    return max(
        processed_files,
        key=lambda path: path.stat().st_mtime,
    )


def load_processed_dataframe(
    input_path: Path,
) -> pd.DataFrame:
    """Load transformed Steam data from CSV."""

    try:
        dataframe = pd.read_csv(
    input_path,
    parse_dates=["release_date", "snapshot_at"],
)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise BigQueryLoadError(
            f"Could not read processed file: {input_path}"
        ) from error

    if dataframe.empty:
        raise BigQueryLoadError(
            f"Processed file is empty: {input_path}"
        )

    return dataframe


def prepare_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare DataFrame types for BigQuery."""

    prepared = dataframe.copy()

    prepared["app_id"] = pd.to_numeric(
        prepared["app_id"],
        errors="raise",
    ).astype("int64")

    prepared["release_date"] = pd.to_datetime(
        prepared["release_date"],
        errors="coerce",
    ).dt.date

    prepared["snapshot_at"] = pd.to_datetime(
        prepared["snapshot_at"],
        utc=True,
        errors="raise",
    )

    return prepared


def get_table_schema() -> list[bigquery.SchemaField]:
    """Return the explicit BigQuery table schema."""

    return [
        bigquery.SchemaField("app_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("type", "STRING"),
        bigquery.SchemaField("is_free", "BOOLEAN"),
        bigquery.SchemaField("price_pln", "FLOAT"),
        bigquery.SchemaField("initial_price_pln", "FLOAT"),
        bigquery.SchemaField("discount_percent", "INTEGER"),
        bigquery.SchemaField("currency", "STRING"),
        bigquery.SchemaField("coming_soon", "BOOLEAN"),
        bigquery.SchemaField("release_date", "DATE"),
        bigquery.SchemaField("developers", "STRING"),
        bigquery.SchemaField("publishers", "STRING"),
        bigquery.SchemaField("genres", "STRING"),
        bigquery.SchemaField("categories", "STRING"),
        bigquery.SchemaField("metacritic_score", "INTEGER"),
        bigquery.SchemaField("recommendation_count", "INTEGER"),
        bigquery.SchemaField("current_players", "INTEGER"),
        bigquery.SchemaField("supports_windows", "BOOLEAN"),
        bigquery.SchemaField("supports_mac", "BOOLEAN"),
        bigquery.SchemaField("supports_linux", "BOOLEAN"),
        bigquery.SchemaField(
            "snapshot_at",
            "TIMESTAMP",
            mode="REQUIRED",
        ),
    ]


def load_dataframe_to_bigquery(
    client: bigquery.Client,
    dataframe: pd.DataFrame,
) -> bigquery.Table:
    """Append one Steam snapshot to BigQuery."""

    table_id = (
        f"{GOOGLE_CLOUD_PROJECT}."
        f"{BIGQUERY_DATASET}."
        f"{BIGQUERY_TABLE}"
    )

    job_config = bigquery.LoadJobConfig(
        schema=get_table_schema(),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    LOGGER.info(
        "Loading %s rows into %s",
        len(dataframe),
        table_id,
    )

    load_job = client.load_table_from_dataframe(
        dataframe,
        table_id,
        job_config=job_config,
        location=BIGQUERY_LOCATION,
    )

    load_job.result()

    return client.get_table(table_id)


def main() -> None:
    """Load the newest processed Steam file into BigQuery."""

    configure_logging()
    validate_configuration()

    LOGGER.info("Starting BigQuery load")

    input_path = find_latest_processed_file()
    LOGGER.info("Using processed file: %s", input_path)

    dataframe = load_processed_dataframe(input_path)
    prepared_dataframe = prepare_dataframe(dataframe)

    try:
        client = bigquery.Client(
            project=GOOGLE_CLOUD_PROJECT,
            location=BIGQUERY_LOCATION,
        )

        table = load_dataframe_to_bigquery(
            client=client,
            dataframe=prepared_dataframe,
        )

    except GoogleAPIError as error:
        raise BigQueryLoadError(
            f"BigQuery operation failed: {error}"
        ) from error

    LOGGER.info(
        "Load finished: table=%s, total_rows=%s",
        table.full_table_id,
        table.num_rows,
    )


if __name__ == "__main__":
    main()