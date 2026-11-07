from datetime import timedelta

from config import PROJECT_ROOT, Settings
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from scheduler.jobs import create_economy_scheduler
from services.catalog_service import load_item_catalog
from services.npc_simulation_service import NpcSimulationSettings


def test_economy_jobs_use_configured_intervals(tmp_path) -> None:
    database_path = tmp_path / "scheduler.db"
    upgrade_database(database_path)
    engine = make_engine(database_path)
    settings = Settings(
        database_path=database_path,
        economy_update_interval_minutes=17,
        market_history_interval_minutes=29,
    )
    items = load_item_catalog(
        PROJECT_ROOT / "data" / "item_catalog.json",
        PROJECT_ROOT / "assets" / "images" / "items",
    )

    npc_settings = NpcSimulationSettings(enabled=True, interval_seconds=720)
    scheduler = create_economy_scheduler(
        make_session_factory(engine),
        items,
        settings,
        npc_settings,
    )
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert jobs["economy-price-update"].trigger.interval == timedelta(minutes=17)
    assert jobs["market-history-snapshot"].trigger.interval == timedelta(minutes=29)
    assert jobs["npc-simulation-cycle"].trigger.interval == timedelta(seconds=720)
    assert scheduler._job_defaults["max_instances"] == 1
    engine.dispose()