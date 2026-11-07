from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from config import PROJECT_ROOT
from database.connection import make_engine


def upgrade_database(database_path: Path, engine: Engine | None = None) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = None
    database_engine = engine or make_engine(database_path)
    owns_engine = engine is None

    try:
        with database_engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
    finally:
        if owns_engine:
            database_engine.dispose()