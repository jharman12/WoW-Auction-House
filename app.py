import logging

from dash import Dash, html

from config import Settings
from database.migrations import upgrade_database
from logging_config import configure_logging


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or Settings()
    try:
        upgrade_database(settings.database_path)
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize database at {settings.database_path}") from exc

    app = Dash(__name__, title="WoW Auction House")
    app.layout = html.Main(
        [
            html.P("D&D CAMPAIGN MARKETPLACE", className="eyebrow"),
            html.H1("Auction House"),
            html.P("Phase 0 foundation is running.", className="status"),
        ],
        className="page-shell",
    )
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