from __future__ import annotations

import logging
import time

from src.extract import main as extract_main
from src.load_bigquery import main as load_bigquery_main
from src.transform import main as transform_main


LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure logging for the complete ETL pipeline."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    """Run the complete Steam ETL pipeline."""

    configure_logging()

    started_at = time.perf_counter()

    LOGGER.info("Starting Steam ETL pipeline")

    LOGGER.info("Step 1/3: Extracting Steam data")
    extract_main()

    LOGGER.info("Step 2/3: Transforming Steam data")
    transform_main()

    LOGGER.info("Step 3/3: Loading Steam data into BigQuery")
    load_bigquery_main()

    elapsed_seconds = time.perf_counter() - started_at

    LOGGER.info(
        "Steam ETL pipeline completed successfully in %.2f seconds",
        elapsed_seconds,
    )


if __name__ == "__main__":
    main()