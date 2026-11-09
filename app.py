import logging

from dash import Dash, dcc, html

from callbacks.navigation import register_navigation
from callbacks.marketplace import register_marketplace_callbacks
from callbacks.simulation import register_simulation_callbacks
from config import PROJECT_ROOT, Settings
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from layouts.pages import landing_page
from logging_config import configure_logging
from scheduler.jobs import create_economy_scheduler
from services.category_taxonomy import load_category_filters
from services.catalog_service import load_application_catalog, load_characters
from services.character_service import sync_characters
from services.economy_service import ensure_initial_market_prices
from services.listing_service import load_npc_market_seed, seed_npc_marketplace
from services.npc_simulation_service import (
    default_npc_simulation_settings,
    load_npc_simulation_settings,
)


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or Settings()
    item_catalog = load_application_catalog(
        PROJECT_ROOT / "data" / "item_catalog.json",
        settings.additional_catalog_path,
        PROJECT_ROOT / "assets" / "images" / "items",
    )
    characters = load_characters(
        PROJECT_ROOT / "data" / "characters.json",
        PROJECT_ROOT / "assets" / "images" / "characters",
    )
    category_filters = load_category_filters(PROJECT_ROOT / "data" / "marketplace_filters.json")
    npc_market_seed = load_npc_market_seed(PROJECT_ROOT / "data" / "npc_market_seed.json")
    items_by_id = {item.id: item for item in item_catalog}

    try:
        upgrade_database(settings.database_path)
        engine = make_engine(settings.database_path)
        session_factory = make_session_factory(engine)
        sync_characters(characters, session_factory)
        seed_npc_marketplace(
            session_factory,
            npc_market_seed,
            items_by_id,
            settings.default_listing_expiration_days,
        )
        ensure_initial_market_prices(session_factory, item_catalog, settings)
        simulation_settings = load_npc_simulation_settings(
            session_factory,
            default_npc_simulation_settings(settings),
        )
    except Exception as exc:
        if "engine" in locals():
            engine.dispose()
        raise RuntimeError(f"Unable to initialize database at {settings.database_path}") from exc

    app = Dash(
        __name__,
        title="The Gilded Ledger",
        assets_folder=str(PROJECT_ROOT / "assets"),
        suppress_callback_exceptions=True,
    )
    app.layout = html.Div(
        [
            dcc.Location(id="url", refresh=False),
            html.Div(landing_page(), id="page-content"),
        ]
    )
    scheduler = create_economy_scheduler(session_factory, item_catalog, settings, simulation_settings)
    register_navigation(
        app,
        item_catalog,
        category_filters,
        characters,
        settings.marketplace_poll_interval_ms,
        simulation_settings,
    )
    register_marketplace_callbacks(app, item_catalog, category_filters, session_factory, settings)
    register_simulation_callbacks(app, session_factory, item_catalog, settings, scheduler)
    app.server.config["AUCTION_HOUSE_ITEMS"] = item_catalog
    app.server.config["AUCTION_HOUSE_SESSION_FACTORY"] = session_factory
    app.server.config["AUCTION_HOUSE_SETTINGS"] = settings
    app.server.config["AUCTION_HOUSE_SIMULATION_SETTINGS"] = simulation_settings
    app.server.config["AUCTION_HOUSE_SCHEDULER"] = scheduler
    return app


def main() -> None:
    settings = Settings()
    configure_logging(settings)
    logger.info("Starting auction house on %s:%s", settings.host, settings.port)
    logger.info("LAN clients can connect at http://<host-lan-ip>:%s", settings.port)

    scheduler = None
    try:
        app = create_app(settings)
        scheduler = app.server.config["AUCTION_HOUSE_SCHEDULER"]
        scheduler.start()
        app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False)
    except OSError as exc:
        logger.error("Unable to start server on port %s: %s", settings.port, exc)
        raise SystemExit(1) from exc
    except Exception:
        logger.exception("Application startup failed")
        raise SystemExit(1) from None
    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Auction house stopped")


if __name__ == "__main__":
    main()