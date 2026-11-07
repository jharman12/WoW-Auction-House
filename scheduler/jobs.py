import logging
from collections.abc import Sequence

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from services.catalog_service import CatalogItem
from services.economy_service import snapshot_market_history, update_market_prices


logger = logging.getLogger(__name__)


def _update_prices(
    session_factory: sessionmaker[Session],
    items: Sequence[CatalogItem],
    settings: Settings,
) -> None:
    try:
        updated = update_market_prices(session_factory, items, settings, record_history=False)
        logger.info("Scheduled economy update completed for %s items", len(updated))
    except Exception:
        logger.exception("Scheduled economy update failed")


def _snapshot_history(session_factory: sessionmaker[Session]) -> None:
    try:
        count = snapshot_market_history(session_factory)
        logger.info("Scheduled market history snapshot recorded for %s items", count)
    except Exception:
        logger.exception("Scheduled market history snapshot failed")


def create_economy_scheduler(
    session_factory: sessionmaker[Session],
    items: Sequence[CatalogItem],
    settings: Settings,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        timezone="UTC",
        executors={"default": {"type": "threadpool", "max_workers": 1}},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
    )
    scheduler.add_job(
        _update_prices,
        trigger="interval",
        minutes=settings.economy_update_interval_minutes,
        id="economy-price-update",
        name="Update market prices",
        args=[session_factory, list(items), settings],
        replace_existing=True,
    )
    scheduler.add_job(
        _snapshot_history,
        trigger="interval",
        minutes=settings.market_history_interval_minutes,
        id="market-history-snapshot",
        name="Record market price history",
        args=[session_factory],
        replace_existing=True,
    )
    return scheduler