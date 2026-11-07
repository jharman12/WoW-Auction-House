import json
from pathlib import Path

from sqlalchemy import select

from app import create_app
from config import Settings
from database.connection import make_engine
from database.models import Listing


def _callback_targets(app, callback_key: str) -> dict[str, str] | list[dict[str, str]]:
    output = app.callback_map[callback_key]["output"]
    outputs = output if isinstance(output, list) else [output]
    targets = [
        {"id": item.component_id, "property": item.component_property}
        for item in outputs
    ]
    return targets if isinstance(output, list) else targets[0]


def _run_callback(client, app, callback_key, input_values, state_values, changed_property_ids):
    callback = app.callback_map[callback_key]
    inputs = [
        {
            "id": component["id"],
            "property": component["property"],
            "value": input_values[(component["id"], component["property"])],
        }
        for component in callback["inputs"]
    ]
    states = [
        {
            "id": component["id"],
            "property": component["property"],
            "value": state_values[(component["id"], component["property"])],
        }
        for component in callback["state"]
    ]
    return client.post(
        "/_dash-update-component",
        json={
            "output": callback_key,
            "outputs": _callback_targets(app, callback_key),
            "inputs": inputs,
            "state": states,
            "changedPropIds": changed_property_ids,
        },
    )


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


def test_player_listing_is_visible_filterable_and_cancellable(tmp_path: Path) -> None:
    database_path = tmp_path / "auction_house.db"
    settings = Settings(database_path=database_path, log_path=tmp_path / "app.log")
    app = create_app(settings)
    client = app.server.test_client()
    mutation_key = next(key for key in app.callback_map if "listing-feedback.children" in key)
    mutation_inputs = {
        ("create-listing", "n_clicks"): 1,
        ('{"listing_id":["ALL"],"type":"cancel-listing"}', "n_clicks"): [],
    }
    mutation_states = {
        ("url", "pathname"): "/player/mira-coppervale",
        ("listing-item", "value"): "redleaf-tonic",
        ("listing-quantity", "value"): 2,
        ("listing-price", "value"): 12.5,
        ("listing-refresh-token", "data"): 0,
    }

    created = _run_callback(client, app, mutation_key, mutation_inputs, mutation_states, ["create-listing.n_clicks"])

    assert created.status_code == 200
    assert "Listing posted to the shared market." in created.get_data(as_text=True)

    engine = make_engine(database_path)
    try:
        with engine.connect() as connection:
            listing_id = connection.execute(
                select(Listing.id).where(Listing.owner_type == "PLAYER")
            ).scalar_one()
    finally:
        engine.dispose()

    market_key = next(key for key in app.callback_map if "market-listings.children" in key)
    market_inputs = {
        ("market-search", "value"): "",
        ("market-category", "value"): "all",
        ("market-rarity", "value"): "all",
        ("market-sort", "value"): "name",
        ("market-poll", "n_intervals"): 0,
        ("listing-refresh-token", "data"): 1,
        ("market-previous", "n_clicks"): 0,
        ("market-next", "n_clicks"): 0,
    }
    market_states = {("url", "pathname"): "/player/mira-coppervale", ("listing-page", "data"): 1}
    market = _run_callback(client, app, market_key, market_inputs, market_states, ["market-search.value"])

    assert market.status_code == 200
    market_content = json.dumps(market.get_json())
    assert "Redleaf Tonic" in market_content
    assert "Ironbound Shortsword" in market_content
    assert "Mira Coppervale" in market_content
    assert "Mara's Wayfarer Goods" in market_content

    details_key = next(key for key in app.callback_map if "listing-details.children" in key)
    details_input_id = '{"listing_id":["ALL"],"type":"inspect-listing"}'
    listing_details = _run_callback(
        client,
        app,
        details_key,
        {(details_input_id, "n_clicks"): [1]},
        {},
        [json.dumps({"type": "inspect-listing", "listing_id": listing_id}, separators=(",", ":")) + ".n_clicks"],
    )
    assert listing_details.status_code == 200
    details_content = json.dumps(listing_details.get_json())
    assert "A sharp herbal drink" in details_content
    assert "Uses" in details_content

    market_inputs[("market-category", "value")] = "consumable"
    filtered = _run_callback(client, app, market_key, market_inputs, market_states, ["market-category.value"])
    filtered_content = json.dumps(filtered.get_json())
    assert "Redleaf Tonic" in filtered_content
    assert "Ironbound Shortsword" not in filtered_content

    cancel_input_id = '{"listing_id":["ALL"],"type":"cancel-listing"}'
    mutation_inputs[("create-listing", "n_clicks")] = 0
    mutation_inputs[(cancel_input_id, "n_clicks")] = [1]
    mutation_states[("listing-refresh-token", "data")] = 1
    trigger_id = json.dumps({"type": "cancel-listing", "listing_id": listing_id}, separators=(",", ":"))
    cancelled = _run_callback(
        client,
        app,
        mutation_key,
        mutation_inputs,
        mutation_states,
        [f"{trigger_id}.n_clicks"],
    )

    assert cancelled.status_code == 200
    assert "Listing cancelled." in cancelled.get_data(as_text=True)

    with engine.connect() as connection:
        npc_listing_id = connection.execute(
            select(Listing.id).where(Listing.owner_type == "NPC").limit(1)
        ).scalar_one()
    mutation_inputs[("create-listing", "n_clicks")] = 0
    mutation_inputs[(cancel_input_id, "n_clicks")] = [1]
    mutation_states[("url", "pathname")] = "/dm"
    mutation_states[("listing-refresh-token", "data")] = 2
    dm_cancellation = _run_callback(
        client,
        app,
        mutation_key,
        mutation_inputs,
        mutation_states,
        [json.dumps({"type": "cancel-listing", "listing_id": npc_listing_id}, separators=(",", ":")) + ".n_clicks"],
    )
    assert dm_cancellation.status_code == 200
    assert "Listing cancelled." in dm_cancellation.get_data(as_text=True)
    engine.dispose()