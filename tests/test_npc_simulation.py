import json
import random
from decimal import Decimal
from pathlib import Path
from threading import Lock

import pytest
from sqlalchemy import func, select

import services.npc_simulation_service as npc_simulation_service
from config import PROJECT_ROOT, Settings
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from database.models import AppSetting, Character, Listing, NPC, Transaction
from services.auction_service import BuyerContext
from services.catalog_service import load_item_catalog
from services.listing_service import NpcPreferences, create_player_listing, load_npc_market_seed, seed_npc_marketplace
from services.npc_simulation_service import (
    NpcSimulationSettings,
    default_npc_simulation_settings,
    load_npc_simulation_settings,
    run_npc_simulation_cycle,
    save_npc_simulation_settings,
)


@pytest.fixture
def simulation_database(tmp_path: Path):
    database_path = tmp_path / "npc-simulation.db"
    upgrade_database(database_path)
    engine = make_engine(database_path)
    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        session.add_all(
            [
                Character(id="mira-coppervale", name="Mira Coppervale", active=True),
                NPC(
                    id=1,
                    name="Sure Buyer",
                    archetype="Collector",
                    is_buyer=True,
                    is_seller=False,
                    preferences_json=NpcPreferences(
                        preferred_categories=["consumable"],
                        buyer_purchase_probability=1,
                        buyer_price_ceiling_multiplier=2,
                        buyer_budget_per_cycle=Decimal("500"),
                        seller_listing_probability=0,
                    ).model_dump_json(),
                ),
                NPC(
                    id=2,
                    name="Certain Seller",
                    archetype="Provisioner",
                    is_buyer=False,
                    is_seller=True,
                    preferences_json=NpcPreferences(
                        preferred_categories=["weapon"],
                        buyer_purchase_probability=0,
                        seller_listing_probability=1,
                        seller_price_spread=0,
                    ).model_dump_json(),
                ),
                NPC(
                    id=3,
                    name="Certain Seller Two",
                    archetype="Provisioner",
                    is_buyer=False,
                    is_seller=True,
                    preferences_json=NpcPreferences(
                        preferred_categories=["armor"],
                        buyer_purchase_probability=0,
                        seller_listing_probability=1,
                        seller_price_spread=0,
                    ).model_dump_json(),
                ),
            ]
        )
    yield session_factory
    engine.dispose()


@pytest.fixture
def items():
    return load_item_catalog(
        PROJECT_ROOT / "data" / "item_catalog.json",
        PROJECT_ROOT / "assets" / "images" / "items",
    )


def test_sellers_generate_listings_within_cycle_and_active_caps(simulation_database, items) -> None:
    settings = Settings(max_npc_listings=3, max_npc_new_listings_per_cycle=2)
    simulation_settings = NpcSimulationSettings(
        enabled=True,
        activity_intensity=1,
        max_active_listings=3,
        max_new_listings_per_cycle=2,
        max_transactions_per_cycle=0,
    )

    result = run_npc_simulation_cycle(
        simulation_database,
        items,
        settings,
        simulation_settings,
        rng=random.Random(7),
    )

    assert result.listings_created == 2
    with simulation_database() as session:
        assert session.scalar(
            select(func.count(Listing.id)).where(Listing.owner_type == "NPC", Listing.status == "ACTIVE")
        ) == 2

    second_result = run_npc_simulation_cycle(
        simulation_database,
        items,
        settings,
        simulation_settings.model_copy(update={"max_active_listings": 2}),
        rng=random.Random(7),
    )
    assert second_result.listings_created == 0


def test_npc_buyer_purchases_player_listing_through_auction_service(simulation_database, items) -> None:
    items_by_id = {item.id: item for item in items}
    listing_id = create_player_listing(
        simulation_database,
        items_by_id,
        "mira-coppervale",
        "redleaf-tonic",
        2,
        12,
        14,
    )
    simulation_settings = NpcSimulationSettings(
        enabled=True,
        activity_intensity=1,
        max_active_listings=0,
        max_new_listings_per_cycle=0,
        max_transactions_per_cycle=1,
    )

    result = run_npc_simulation_cycle(
        simulation_database,
        items,
        Settings(max_npc_transactions_per_cycle=1),
        simulation_settings,
        rng=random.Random(11),
    )

    assert result.transactions_completed == 1
    with simulation_database() as session:
        listing = session.get(Listing, listing_id)
        transaction = session.scalar(select(Transaction).where(Transaction.listing_id == listing_id))
        assert listing.status == "SOLD"
        assert transaction is not None
        assert transaction.buyer_type == "NPC"
        assert transaction.buyer_npc_id == 1
        assert transaction.player_sale_proceeds == 24


def test_transaction_cap_is_enforced(simulation_database, items) -> None:
    items_by_id = {item.id: item for item in items}
    listing_ids = [
        create_player_listing(
            simulation_database,
            items_by_id,
            "mira-coppervale",
            "redleaf-tonic",
            1,
            12,
            14,
        )
        for _ in range(3)
    ]
    simulation_settings = NpcSimulationSettings(
        enabled=True,
        activity_intensity=1,
        max_active_listings=0,
        max_new_listings_per_cycle=0,
        max_transactions_per_cycle=1,
    )

    result = run_npc_simulation_cycle(
        simulation_database,
        items,
        Settings(max_npc_transactions_per_cycle=1),
        simulation_settings,
        rng=random.Random(5),
    )

    assert result.transactions_completed == 1
    with simulation_database() as session:
        sold_count = session.scalar(
            select(func.count(Listing.id)).where(Listing.id.in_(listing_ids), Listing.status == "SOLD")
        )
        assert sold_count == 1


def test_disabled_and_overlapping_cycles_do_no_work(simulation_database, items, monkeypatch) -> None:
    disabled = NpcSimulationSettings(
        enabled=False,
        activity_intensity=1,
        max_active_listings=10,
        max_new_listings_per_cycle=10,
        max_transactions_per_cycle=10,
    )
    assert run_npc_simulation_cycle(simulation_database, items, Settings(), disabled).disabled

    lock = Lock()
    lock.acquire()
    monkeypatch.setattr(npc_simulation_service, "_CYCLE_LOCK", lock)
    try:
        result = run_npc_simulation_cycle(
            simulation_database,
            items,
            Settings(),
            disabled.model_copy(update={"enabled": True}),
        )
        assert result.skipped
    finally:
        lock.release()


def test_simulation_settings_persist_and_seed_preferences_are_stored(simulation_database, items) -> None:
    defaults = default_npc_simulation_settings(Settings())
    loaded_defaults = load_npc_simulation_settings(simulation_database, defaults)
    changed = loaded_defaults.model_copy(update={"enabled": False, "interval_seconds": 900})
    save_npc_simulation_settings(simulation_database, changed)

    assert load_npc_simulation_settings(simulation_database, defaults) == changed

    seed = load_npc_market_seed(PROJECT_ROOT / "data" / "npc_market_seed.json")
    seed_npc_marketplace(
        simulation_database,
        seed,
        {item.id: item for item in items},
        14,
    )
    with simulation_database() as session:
        seeded_npc = session.scalar(select(NPC).where(NPC.name == "Mara's Wayfarer Goods"))
        assert seeded_npc is not None
        stored_preferences = json.loads(seeded_npc.preferences_json)
        assert stored_preferences["preferred_categories"] == ["adventuring_gear", "consumable"]