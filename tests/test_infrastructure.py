from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from app import create_app
from config import Settings
from database.connection import make_engine, make_session_factory
from database.models import Character


def test_settings_validate_port_and_price_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(port=70000)

    with pytest.raises(ValidationError):
        Settings(minimum_price_multiplier=5, maximum_price_multiplier=2)


def test_app_runs_migrations_and_preserves_database(tmp_path: Path) -> None:
    database_path = tmp_path / "auction_house.db"
    settings = Settings(database_path=database_path, log_path=tmp_path / "app.log")

    app = create_app(settings)
    first_client = app.server.test_client()
    response = first_client.get("/")
    assert response.status_code == 200
    layout_response = first_client.get("/_dash-layout")
    assert layout_response.status_code == 200
    assert b'"Player"' in layout_response.data
    assert b'"DM"' in layout_response.data

    engine = make_engine(database_path)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        session.add(Character(id="test-character", name="Test Character"))
        session.commit()
    engine.dispose()

    create_app(settings)

    engine = make_engine(database_path)
    try:
        table_names = set(inspect(engine).get_table_names())
        assert {"characters", "npcs", "listings", "transactions", "settings"} <= table_names
        assert "player_gold" not in table_names
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            assert session.get(Character, "test-character").name == "Test Character"
    finally:
        engine.dispose()