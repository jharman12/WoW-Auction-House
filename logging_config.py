import logging
from pathlib import Path

from config import Settings


def configure_logging(settings: Settings) -> None:
    log_path: Path = settings.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )