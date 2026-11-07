import logging

from dash import Dash, dcc, html

from callbacks.navigation import register_navigation
from config import PROJECT_ROOT, Settings
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from layouts.pages import landing_page
from logging_config import configure_logging
from services.catalog_service import load_characters, load_item_catalog
from services.character_service import sync_characters


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or Settings()
    item_catalog = load_item_catalog(
        PROJECT_ROOT / "data" / "item_catalog.json",
        PROJECT_ROOT / "assets" / "images" / "items",
    )
    characters = load_characters(
        PROJECT_ROOT / "data" / "characters.json",
        PROJECT_ROOT / "assets" / "images" / "characters",
    )

    try:
        upgrade_database(settings.database_path)
        engine = make_engine(settings.database_path)
        try:
            sync_characters(characters, make_session_factory(engine))
        finally:
            engine.dispose()
    except Exception as exc:
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
    register_navigation(app, item_catalog, characters)
    return app


def main() -> None:
    settings = Settings()
    configure_logging(settings)
    logger.info("Starting auction house on %s:%s", settings.host, settings.port)
    logger.info("LAN clients can connect at http://<host-lan-ip>:%s", settings.port)

    try:
        app = create_app(settings)
        app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False)
    except OSError as exc:
        logger.error("Unable to start server on port %s: %s", settings.port, exc)
        raise SystemExit(1) from exc
    except Exception:
        logger.exception("Application startup failed")
        raise SystemExit(1) from None
    finally:
        logger.info("Auction house stopped")


if __name__ == "__main__":
    main()