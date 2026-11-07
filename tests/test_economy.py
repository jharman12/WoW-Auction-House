from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from config import PROJECT_ROOT, Settings
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from database.models import Character, Listing, MarketHistory, MarketPrice
from services.auction_service import BuyerContext, purchase_listing
from services.catalog_service import load_item_catalog
from services.economy_service import (
    calculate_market_price,
    ensure_initial_market_prices,
    get_current_market_prices,
    get_market_history,
    snapshot_market_history,
    update_market_prices,
)
from services.listing_service import create_player_listing


@pytest.fixture
def items():
    return load_item_catalog(
        PROJECT_ROOT / "data" / "item_catalog.json",
        PROJECT_ROOT / "assets" / "images" / "items",
    )


@pytest.fixture
def economy_database(tmp_path: Path):
    database_path = tmp_path / "economy.db"
    upgrade_database(database_path)
    engine = make_engine(database_path)
    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        session.add_all(
            [
                Character(id="mira-coppervale", name="Mira Coppervale", active=True),
                Character(id="buyer-character", name="Buyer Character", active=True),
            ]
        )
    yield session_factory
    engine.dispose()


def test_supply_increase_lowers_price_all_else_equal() -> None:
    settings = Settings()
    prices = [
        calculate_market_price(Decimal("100"), supply, 5, None, settings).market_price
        for supply in (5, 10, 20)
    ]

    assert prices[0] > prices[1] > prices[2]


def test_demand_increase_raises_price_all_else_equal() -> None:
    settings = Settings()
    prices = [
        calculate_market_price(Decimal("100"), 10, sold, None, settings).market_price
        for sold in (0, 5, 10)
    ]

    assert prices[0] < prices[1] < prices[2]


def test_price_multiplier_and_minimum_floor_are_bounded() -> None:
    settings = Settings(economy_minimum_price_gp=Decimal("3"))
    low = calculate_market_price(Decimal("10"), 1000, 0, None, settings)
    high = calculate_market_price(Decimal("10"), 0, 1000, None, settings)

    assert low.market_price >= Decimal("3")
    assert low.combined_multiplier >= Decimal("0.25")
    assert high.market_price <= Decimal("40")
    assert high.combined_multiplier <= Decimal("4")


def test_smoothing_change_limit_and_gold_rounding_are_deterministic() -> None:
    settings = Settings(max_price_change_percent=10, economy_smoothing_factor=Decimal("1"))
    result = calculate_market_price(Decimal("100"), 1, 100, Decimal("100"), settings)
    repeated = calculate_market_price(Decimal("100"), 1, 100, Decimal("100"), settings)

    assert result.market_price == Decimal("110")
    assert result.market_price == repeated.market_price


def test_initial_market_price_uses_configured_rounding() -> None:
    settings = Settings(economy_target_supply_quantity=10, economy_target_demand_quantity=5)
    result = calculate_market_price(Decimal("10.5"), 10, 5, None, settings)

    assert result.market_price == Decimal("11")


def test_invalid_supply_and_demand_are_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_market_price(Decimal("10"), -1, 0, None, Settings())
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_market_price(Decimal("10"), 0, -1, None, Settings())


def test_updates_measure_supply_recent_demand_and_persist_history(economy_database, items) -> None:
    items_by_id = {item.id: item for item in items}
    tonic = items_by_id["redleaf-tonic"]
    now = datetime(2026, 8, 1, tzinfo=UTC)
    listing_id = create_player_listing(
        economy_database,
        items_by_id,
        "mira-coppervale",
        tonic.id,
        3,
        20,
        30,
        now=now,
    )
    purchase_listing(
        economy_database,
        listing_id,
        BuyerContext(buyer_type="PLAYER", character_id="buyer-character"),
        now=now + timedelta(hours=1),
    )
    old_listing_id = create_player_listing(
        economy_database,
        items_by_id,
        "mira-coppervale",
        tonic.id,
        1,
        20,
        30,
        now=now - timedelta(days=3),
    )
    purchase_listing(
        economy_database,
        old_listing_id,
        BuyerContext(buyer_type="PLAYER", character_id="buyer-character"),
        now=now - timedelta(days=2),
    )
    settings = Settings(economy_demand_window_hours=24)

    first_update = update_market_prices(economy_database, items, settings, now=now + timedelta(hours=2))
    tonic_view = next(view for view in first_update if view.item_id == tonic.id)
    assert tonic_view.active_supply == 0
    assert tonic_view.recent_quantity_sold == 3

    second_update = update_market_prices(economy_database, items, settings, now=now + timedelta(hours=3))
    tonic_price = next(view.market_price for view in second_update if view.item_id == tonic.id)
    history = get_market_history(economy_database, tonic.id)
    current = {view.item_id: view for view in get_current_market_prices(economy_database, items)}

    assert tonic_price == current[tonic.id].market_price
    assert len(history) == 2
    assert history[0].recent_quantity_sold == 3
    assert history[-1].market_price == tonic_price


def test_initial_prices_are_seeded_once_and_expired_stock_is_excluded(economy_database, items) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    items_by_id = {item.id: item for item in items}
    create_player_listing(
        economy_database,
        items_by_id,
        "mira-coppervale",
        "redleaf-tonic",
        4,
        20,
        1,
        now=now - timedelta(days=2),
    )

    initialized = ensure_initial_market_prices(economy_database, items, Settings())
    repeated = ensure_initial_market_prices(economy_database, items, Settings())
    tonic_view = next(view for view in initialized if view.item_id == "redleaf-tonic")

    assert tonic_view.active_supply == 0
    assert repeated == []
    with economy_database() as session:
        assert session.scalar(select(MarketPrice.item_id).where(MarketPrice.item_id == "redleaf-tonic"))
        assert session.scalar(select(MarketHistory.id).where(MarketHistory.item_id == "redleaf-tonic"))


def test_scheduled_price_refresh_and_history_snapshot_are_separate(economy_database, items) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    ensure_initial_market_prices(economy_database, items, Settings())
    refresh = update_market_prices(
        economy_database,
        items,
        Settings(),
        now=now + timedelta(hours=1),
        record_history=False,
    )

    with economy_database() as session:
        history_before_snapshot = session.scalar(
            select(func.count(MarketHistory.id)).where(MarketHistory.item_id == "redleaf-tonic")
        )

    snapshot_count = snapshot_market_history(economy_database, now=now + timedelta(hours=2))

    with economy_database() as session:
        history_after_snapshot = session.scalar(
            select(func.count(MarketHistory.id)).where(MarketHistory.item_id == "redleaf-tonic")
        )
        current_price = session.get(MarketPrice, "redleaf-tonic")

    assert len(refresh) == len(items)
    assert history_before_snapshot == 1
    assert snapshot_count == len(items)
    assert history_after_snapshot == 2
    assert current_price is not None
    assert current_price.recorded_at.replace(tzinfo=UTC) == now + timedelta(hours=1)