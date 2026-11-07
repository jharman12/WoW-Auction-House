import json
from pathlib import Path

from app import create_app
from config import PROJECT_ROOT, Settings


def test_player_and_dm_navigation_flows(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "auction_house.db", log_path=tmp_path / "app.log")
    app = create_app(settings)
    client = app.server.test_client()

    landing = client.get("/_dash-layout")
    assert landing.status_code == 200
    assert b'"Player"' in landing.data
    assert b'"DM"' in landing.data

    def navigate(pathname: str) -> str:
        response = client.post(
            "/_dash-update-component",
            json={
                "output": "page-content.children",
                "outputs": {"id": "page-content", "property": "children"},
                "inputs": [{"id": "url", "property": "pathname", "value": pathname}],
                "state": [],
                "changedPropIds": ["url.pathname"],
            },
        )
        assert response.status_code == 200
        return json.dumps(response.get_json())

    character_selection = navigate("/characters")
    assert "Choose your character" in character_selection
    assert "/player/mira-coppervale" in character_selection

    player_marketplace = navigate("/player/mira-coppervale")
    assert "Marketplace" in player_marketplace
    assert "MIRA COPPERVALE" in player_marketplace

    dm_dashboard = navigate("/dm")
    assert "DM Dashboard" in dm_dashboard
    assert "8" in dm_dashboard


def test_unknown_character_does_not_open_player_view(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "auction_house.db", log_path=tmp_path / "app.log")
    app = create_app(settings)
    client = app.server.test_client()

    response = client.post(
        "/_dash-update-component",
        json={
            "output": "page-content.children",
            "outputs": {"id": "page-content", "property": "children"},
            "inputs": [{"id": "url", "property": "pathname", "value": "/player/not-a-character"}],
            "state": [],
            "changedPropIds": ["url.pathname"],
        },
    )

    assert response.status_code == 200
    assert "404" in response.get_data(as_text=True)