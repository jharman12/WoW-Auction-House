from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from config import PROJECT_ROOT
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from database.models import Character, Listing, NPC
from services.catalog_service import CatalogDataError, load_item_catalog
from services.category_taxonomy import load_category_filters, resolve_category_filter
from services.listing_service import (
    InvalidListingError,
    ListingNotActiveError,
    ListingOwnerError,
    NpcMarketSeed,
    cancel_listing,
    create_npc_listing,
    create_player_listing,
    expire_listings,
    get_marketplace,
    load_npc_market_seed,
    seed_npc_marketplace,
)


@pytest.fixture
def market_database(tmp_path: Path):
    database_path = tmp_path / "market.db"
    upgrade_database(database_path)
    engine = make_engine(database_path)
    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        session.add_all(
            [
                Character(id="mira-coppervale", name="Mira Coppervale", active=True),
                NPC(id=1, name="Test Merchant", archetype="Merchant", is_seller=True),
            ]
        )
    yield session_factory
    engine.dispose()


@pytest.fixture
def items_by_id():
    return {
        item.id: item
        for item in load_item_catalog(
            PROJECT_ROOT / "data" / "item_catalog.json",
            PROJECT_ROOT / "assets" / "images" / "items",
        )
    }


def test_player_and_npc_listings_share_marketplace(market_database, items_by_id) -> None:
    player_listing_id = create_player_listing(
        market_database, items_by_id, "mira-coppervale", "redleaf-tonic", 2, "14.50", 14
    )
    npc_listing_id = create_npc_listing(
        market_database, items_by_id, 1, "ironbound-shortsword", 1, 13, 14
    )

    result = get_marketplace(market_database, items_by_id, sort_by="name")

    assert result.total_count == 2
    assert {listing.id for listing in result.listings} == {player_listing_id, npc_listing_id}
    assert {listing.owner_type for listing in result.listings} == {"PLAYER", "NPC"}


def test_market_filters_search_and_sort(market_database, items_by_id) -> None:
    create_player_listing(market_database, items_by_id, "mira-coppervale", "redleaf-tonic", 2, 14, 14)
    create_npc_listing(market_database, items_by_id, 1, "ironbound-shortsword", 1, 13, 14)

    filtered = get_marketplace(market_database, items_by_id, search="herbal", category="consumable")
    ascending = get_marketplace(market_database, items_by_id, sort_by="price_asc")

    assert filtered.total_count == 1
    assert filtered.listings[0].item.id == "redleaf-tonic"
    assert [listing.asking_price for listing in ascending.listings] == [Decimal("13.00"), Decimal("14.00")]


def test_nested_weapon_filter_requires_the_selected_group_and_property(market_database, items_by_id) -> None:
    create_player_listing(market_database, items_by_id, "mira-coppervale", "ironbound-shortsword", 1, 10, 14)
    create_npc_listing(market_database, items_by_id, 1, "stormglass-spear", 1, 250, 14)
    taxonomy = load_category_filters(PROJECT_ROOT / "data" / "marketplace_filters.json")
    selection = resolve_category_filter(taxonomy, "weapons.simple-melee.thrown")

    results = get_marketplace(market_database, items_by_id, filter_selection=selection)

    assert selection is not None
    assert selection.categories == ("weapon",)
    assert selection.required_tags == ("weapon:simple_melee", "weapon:thrown")
    assert [listing.item.id for listing in results.listings] == ["stormglass-spear"]


def test_listing_validation_rejects_bad_owner_item_quantity_and_price(market_database, items_by_id) -> None:
    with pytest.raises(InvalidListingError, match="active campaign character"):
        create_player_listing(market_database, items_by_id, "missing-character", "redleaf-tonic", 1, 10, 14)
    with pytest.raises(InvalidListingError, match="enabled item"):
        create_player_listing(market_database, items_by_id, "mira-coppervale", "missing-item", 1, 10, 14)
    with pytest.raises(InvalidListingError, match="cannot be listed in a stack"):
        create_player_listing(market_database, items_by_id, "mira-coppervale", "ironbound-shortsword", 2, 10, 14)
    with pytest.raises(InvalidListingError, match="positive number"):
        create_player_listing(market_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, 0, 14)
    with pytest.raises(InvalidListingError, match="2 decimal places"):
        create_player_listing(market_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, "1.001", 14)


def test_cancel_is_owner_scoped_and_keeps_history(market_database, items_by_id) -> None:
    listing_id = create_player_listing(
        market_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, 10, 14
    )

    with pytest.raises(ListingOwnerError):
        cancel_listing(market_database, listing_id, character_id="someone-else")
    cancel_listing(market_database, listing_id, character_id="mira-coppervale")

    with market_database() as session:
        listing = session.get(Listing, listing_id)
        assert listing is not None
        assert listing.status == "CANCELLED"

    with pytest.raises(ListingNotActiveError):
        cancel_listing(market_database, listing_id, character_id="mira-coppervale")


def test_expired_listings_transition_out_of_market(market_database, items_by_id) -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    listing_id = create_player_listing(
        market_database,
        items_by_id,
        "mira-coppervale",
        "redleaf-tonic",
        1,
        10,
        1,
        now=created_at,
    )

    assert expire_listings(market_database, now=created_at + timedelta(days=2)) == 1
    assert get_marketplace(market_database, items_by_id).total_count == 0
    with market_database() as session:
        assert session.get(Listing, listing_id).status == "EXPIRED"


def test_npc_seed_is_idempotent_and_validated(market_database, items_by_id) -> None:
    seed = load_npc_market_seed(PROJECT_ROOT / "data" / "npc_market_seed.json")

    assert seed_npc_marketplace(market_database, seed, items_by_id, 14) == 7
    assert seed_npc_marketplace(market_database, seed, items_by_id, 14) == 0
    assert get_marketplace(market_database, items_by_id).total_count == 7


def test_invalid_npc_seed_file_is_reported(tmp_path: Path) -> None:
    seed_path = tmp_path / "bad-seed.json"
    seed_path.write_text('{"sellers": [{"name": "Broken"}]}', encoding="utf-8")

    with pytest.raises(CatalogDataError, match="Invalid NPC market seed"):
        load_npc_market_seed(seed_path)