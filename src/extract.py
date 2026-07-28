from __future__ import annotations

import json
import logging
import time

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from requests import Response, Session
from requests.exceptions import RequestException

LOGGER = logging.getLogger(__name__)

STORE_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
CURRENT_PLAYERS_URL = (
    "https://api.steampowered.com/"
    "ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 1

APP_IDS = [
    730,      # Counter-Strike 2
    292030,   # The Witcher 3
    413150,   # Stardew Valley
    105600,   # Terraria
    1086940,  # Baldur's Gate 3
    1091500,  # Cyberpunk 2077
    1145360,  # Hades
    1245620,  # Elden Ring
]

class SteamExtractionError(RuntimeError):
    """Raised when Steam data cannot be extracted."""

def configure_logging() -> None:
    """Configure application logging"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

def create_http_session() -> Session:
    """Create an HTTP session with common request headers."""

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "steam-bi-pipeline/1.0",
        }

    )
    return session

def validate_response(response: Response) -> None:
    """Raise an exception for an unsuccessful HTTP response."""

    response.raise_for_status()

    content_type = response.headers.get("Content-Type","")

    if "application/json" not in content_type.lower():
        LOGGER.warning(
            "Response content type is not JSON: %s",
            content_type,
        )

def fetch_game_details(
        session: Session,
        app_id: int
) -> dict[str,Any] | None:
    """Fetch raw store details for on Steam application."""
    parameters = {
        "appids": app_id,
        "cc": "pl",
        "l": "english",
    }
    try:
        response = session.get(
            STORE_APP_DETAILS_URL,
            params=parameters,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        validate_response(response)

        payload: dict[str, Any] = response.json()
        application_payload = payload.get(str(app_id))

        if not application_payload:
            LOGGER.warning(
                "Store endpoint returned no payload for app_id=%s",
                app_id
            )
            return None
        if application_payload.get("success") is not True:
            LOGGER.warning(
                "Store endpoint reported failure for app_id=%s",
                app_id,
            )
            return None
        
        game_data = application_payload.get("data")

        if not isinstance(game_data, dict):
            LOGGER.warning(
                "Store endpoint returned invalid data for app_id=%s",
                app_id,
            )
            return None
        return game_data
    except RequestException as error:
        LOGGER.error(
            "Could not fetch game details for app_id=%s",
            app_id,
        )
        return None

def fetch_current_players(
        session: Session,
        app_id: int,
) -> dict[str, Any] | None:
    """Fetch current player count for a Steam application."""
    parameters = {
        "appid": app_id,
    }
    try:
        response = session.get(
            CURRENT_PLAYERS_URL,
            params=parameters,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        validate_response(response)

        payload: dict[str, Any] = response.json()
        player_count_payload = payload.get("response")

        if not isinstance(player_count_payload, dict):
            LOGGER.warning(
                "Current players endpoint returned invalid data for app_id=%s",
                app_id,
            )
            return None
        return player_count_payload
    except RequestException as error:
        LOGGER.error(
            "Could not fetch current players for app_id=%s",
            app_id,
        )
        return None
def extract_game(
    session: Session,
    app_id: int,
    snapshot_at: str,
) -> dict[str, Any]:
    """Extract all available raw data for one Steam application."""

    LOGGER.info("Extracting data for app_id=%s", app_id)

    store_data = fetch_game_details(session, app_id)
    current_players_data = fetch_current_players(session, app_id)

    return {
        "app_id": app_id,
        "snapshot_at": snapshot_at,
        "store_data": store_data,
        "current_players_data": current_players_data,
    }

def extract_games(
    app_ids: list[int],
) -> list[dict[str, Any]]:
    """Extract Steam data for multiple applications in one snapshot."""

    extracted_games: list[dict[str, Any]] = []
    snapshot_at = datetime.now(tz=UTC).isoformat()

    LOGGER.info("Created snapshot: %s", snapshot_at)

    with create_http_session() as session:
        for index, app_id in enumerate(app_ids):
            LOGGER.info(
                "Extracting game %d/%d: app_id=%s",
                index + 1,
                len(app_ids),
                app_id,
            )

            extracted_game = extract_game(
                session=session,
                app_id=app_id,
                snapshot_at=snapshot_at,
            )
            extracted_games.append(extracted_game)

            time.sleep(REQUEST_DELAY_SECONDS)

    return extracted_games

def save_raw_data(
        records: list[dict[str, Any]],
        output_directory: Path = RAW_DATA_DIRECTORY
) -> Path:
    """Save extracted raw data to a JSON file in the output directory."""

    if not records:
        raise SteamExtractionError("" \
        "Cannot save raw data because no records were extracted.")

    output_directory.mkdir(
        parents=True, 
        exist_ok=True
        )

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_file = output_directory / f"steam_raw_data_{timestamp}.json"

    document = {
        "metadata": {
            "source": "Steam Web API",
            "snapshot_at": records[0]["snapshot_at"],
            "record_count": len(records),
            "app_ids": [record["app_id"] for record in records],
        },
        "records": records,
    }
    with output_file.open(
        mode = "w",
        encoding="utf-8",
        ) as file:
        json.dump(
            document,
            file,
            ensure_ascii=False,
            indent=4
            )
        return output_file

def main() -> None:
    """Run the Steam extraction process."""

    configure_logging()
    LOGGER.info("Starting Steam data extraction")

    extracted_games = extract_games(app_ids=APP_IDS)

    successful_store_requests = sum(
        record["store_data"] is not None
        for record in extracted_games
    )
    successful_player_requests = sum(
        record["current_players_data"] is not None
        for record in extracted_games
    )

    if successful_store_requests == 0:
        raise SteamExtractionError(
            "No successful store requests were made. "
            "Check the logs for details."
        )
    output_file = save_raw_data(extracted_games)

    LOGGER.info(
    "Extraction completed successfully: "
    "store requests=%s/%s, player requests=%s/%s",
    successful_store_requests,
    len(APP_IDS),
    successful_player_requests,
    len(APP_IDS),
    )

    LOGGER.info("Saved raw data to %s", output_file)


if __name__ == "__main__":
    main()

