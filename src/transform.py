from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"

RAW_FILE_PATTERN = "steam_raw_data_*.json"

class SteamTransformationError(RuntimeError):
    """Raised when Steam data cannot be transformed."""

def configure_logging() -> None:
    """Configure application logging"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

def find_latest_raw_file(
        raw_data_directory: Path = RAW_DATA_DIRECTORY,
) -> Path | None:
    """Return the most recently modified Steam raw JSON file."""
    if not raw_data_directory.exists():
        raise SteamTransformationError(
            f"Raw data directory does not exist: {raw_data_directory}"
        )
    raw_files = list(raw_data_directory.glob(RAW_FILE_PATTERN))

    if not raw_files:
        SteamTransformationError(
            f"No raw data files matching '{RAW_FILE_PATTERN}' "
            f"found in directory: {raw_data_directory}"
        )
    latest_raw_file = max(
        raw_files,
        key=lambda file_path: file_path.stat().st_mtime,
    )
    return latest_raw_file

def load_raw_data(input_path: Path) -> dict[str, Any]:
    """Load a raw Steam JSON document from disk."""

    try:
        with input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            raw_document: dict[str, Any] = json.load(input_file)

    except FileNotFoundError as error:
        raise SteamTransformationError(
            f"Raw file does not exist: {input_path}"
        ) from error

    except json.JSONDecodeError as error:
        raise SteamTransformationError(
            f"Raw file contains invalid JSON: {input_path}"
        ) from error

    records = raw_document.get("records")

    if not isinstance(records, list):
        raise SteamTransformationError(
            "Raw JSON must contain a 'records' list."
        )

    if not records:
        raise SteamTransformationError(
            "Raw JSON contains no records."
        )

    return raw_document

def extract_descriptions(
    values: Any,
) -> str | None:
    """
    Convert a list of Steam objects containing a description field
    into a pipe-separated string.
    """

    if not isinstance(values, list):
        return None

    descriptions = [
        item["description"].strip()
        for item in values
        if isinstance(item, dict)
        and isinstance(item.get("description"), str)
        and item["description"].strip()
    ]

    return " | ".join(descriptions) or None


def extract_string_list(
    values: Any,
) -> str | None:
    """Convert a list of strings into a pipe-separated string."""

    if not isinstance(values, list):
        return None

    cleaned_values = [
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ]

    return " | ".join(cleaned_values) or None


def convert_minor_units_to_pln(
    value: Any,
) -> float | None:
    """
    Convert Steam price minor units to PLN.

    Steam returns prices as integer minor units. For example,
    1999 represents 19.99 PLN when the request uses cc=pl.
    """

    if value is None:
        return None

    try:
        return round(float(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def parse_release_date(
    release_date: Any,
) -> str | None:
    """Convert a Steam release date into ISO format: YYYY-MM-DD."""

    if not isinstance(release_date, str):
        return None

    cleaned_date = release_date.strip()

    if not cleaned_date:
        return None

    parsed_date = pd.to_datetime(
        cleaned_date,
        errors="coerce",
    )

    if pd.isna(parsed_date):
        LOGGER.warning(
            "Could not parse release date: %s",
            cleaned_date,
        )
        return None

    return parsed_date.date().isoformat()


def transform_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Transform one nested Steam record into a flat dictionary."""

    app_id = record.get("app_id")
    snapshot_at = record.get("snapshot_at")

    store_data = record.get("store_data")
    current_players_data = record.get("current_players_data")

    if not isinstance(store_data, dict):
        store_data = {}

    if not isinstance(current_players_data, dict):
        current_players_data = {}

    price_overview = store_data.get("price_overview")
    release_date_data = store_data.get("release_date")
    platforms = store_data.get("platforms")
    metacritic = store_data.get("metacritic")
    recommendations = store_data.get("recommendations")

    if not isinstance(price_overview, dict):
        price_overview = {}

    if not isinstance(release_date_data, dict):
        release_date_data = {}

    if not isinstance(platforms, dict):
        platforms = {}

    if not isinstance(metacritic, dict):
        metacritic = {}

    if not isinstance(recommendations, dict):
        recommendations = {}

    return {
        "app_id": app_id,
        "name": store_data.get("name"),
        "type": store_data.get("type"),
        "is_free": store_data.get("is_free"),
        "price_pln": convert_minor_units_to_pln(
            price_overview.get("final")
        ),
        "initial_price_pln": convert_minor_units_to_pln(
            price_overview.get("initial")
        ),
        "discount_percent": price_overview.get(
            "discount_percent"
        ),
        "currency": price_overview.get("currency"),
        "coming_soon": release_date_data.get("coming_soon"),
        "release_date": parse_release_date(
            release_date_data.get("date")
        ),
        "developers": extract_string_list(
            store_data.get("developers")
        ),
        "publishers": extract_string_list(
            store_data.get("publishers")
        ),
        "genres": extract_descriptions(
            store_data.get("genres")
        ),
        "categories": extract_descriptions(
            store_data.get("categories")
        ),
        "metacritic_score": metacritic.get("score"),
        "recommendation_count": recommendations.get("total"),
        "current_players": current_players_data.get(
            "player_count"
        ),
        "supports_windows": platforms.get("windows"),
        "supports_mac": platforms.get("mac"),
        "supports_linux": platforms.get("linux"),
        "snapshot_at": snapshot_at,
    }


def transform_records(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    """Transform raw Steam records into a validated DataFrame."""

    transformed_records = [
        transform_record(record)
        for record in records
        if isinstance(record, dict)
    ]

    if not transformed_records:
        raise SteamTransformationError(
            "No valid records were available for transformation."
        )

    dataframe = pd.DataFrame(transformed_records)

    apply_dataframe_types(dataframe)
    validate_dataframe(dataframe)

    return dataframe


def apply_dataframe_types(
    dataframe: pd.DataFrame,
) -> None:
    """Apply stable Pandas data types to transformed columns."""

    integer_columns = [
        "app_id",
        "discount_percent",
        "metacritic_score",
        "recommendation_count",
        "current_players",
    ]

    boolean_columns = [
        "is_free",
        "coming_soon",
        "supports_windows",
        "supports_mac",
        "supports_linux",
    ]

    float_columns = [
        "price_pln",
        "initial_price_pln",
    ]

    for column in integer_columns:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        ).astype("Int64")

    for column in boolean_columns:
        dataframe[column] = dataframe[column].astype("boolean")

    for column in float_columns:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        ).astype("Float64")

    dataframe["release_date"] = pd.to_datetime(
        dataframe["release_date"],
        errors="coerce",
    )

    dataframe["snapshot_at"] = pd.to_datetime(
        dataframe["snapshot_at"],
        utc=True,
        errors="coerce",
    )


def validate_dataframe(
    dataframe: pd.DataFrame,
) -> None:
    """Validate the transformed Steam DataFrame."""

    required_columns = {
        "app_id",
        "name",
        "current_players",
        "snapshot_at",
    }

    missing_columns = required_columns.difference(
        dataframe.columns
    )

    if missing_columns:
        raise SteamTransformationError(
            "Transformed data is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    missing_app_ids = dataframe["app_id"].isna().sum()

    if missing_app_ids > 0:
        raise SteamTransformationError(
            f"Found {missing_app_ids} records without app_id."
        )

    duplicated_app_ids = dataframe["app_id"].duplicated().sum()

    if duplicated_app_ids > 0:
        raise SteamTransformationError(
            f"Found {duplicated_app_ids} duplicated app_id values."
        )

    missing_names = dataframe["name"].isna().sum()

    if missing_names > 0:
        LOGGER.warning(
            "Found %s records without a game name.",
            missing_names,
        )

    missing_player_counts = dataframe[
        "current_players"
    ].isna().sum()

    if missing_player_counts > 0:
        LOGGER.warning(
            "Found %s records without current player counts.",
            missing_player_counts,
        )


def save_processed_data(
    dataframe: pd.DataFrame,
    output_directory: Path = PROCESSED_DATA_DIRECTORY,
) -> Path:
    """Save transformed Steam data as a timestamped CSV file."""

    if dataframe.empty:
        raise SteamTransformationError(
            "Cannot save an empty DataFrame."
        )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        output_directory
        / f"steam_games_transformed_{timestamp}.csv"
    )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
        date_format="%Y-%m-%dT%H:%M:%SZ",
    )

    return output_path


def main() -> None:
    """Run the Steam transformation process."""

    configure_logging()

    LOGGER.info("Starting Steam data transformation")

    input_path = find_latest_raw_file()

    LOGGER.info(
        "Using raw input file: %s",
        input_path,
    )

    raw_document = load_raw_data(input_path)
    records = raw_document["records"]

    dataframe = transform_records(records)
    output_path = save_processed_data(dataframe)

    LOGGER.info(
        "Transformation finished: %s records, %s columns",
        len(dataframe),
        len(dataframe.columns),
    )

    LOGGER.info(
        "Processed data saved to: %s",
        output_path,
    )


if __name__ == "__main__":
    main()