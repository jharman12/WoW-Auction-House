from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

import services.auction_service as auction_service
from config import PROJECT_ROOT
from database.connection import make_engine, make_session_factory
from database.migrations import upgrade_database
from database.models import Character, Listing, NPC, Transaction
from services.auction_service import (
    BuyerContext,
    InvalidBuyerError,
    PurchaseConflictError,
    get_character_sales,
    get_recent_transactions,
    purchase_listing,
)
from services.catalog_service import load_item_catalog
from services.listing_service import (
    ListingNotActiveError,
    create_npc_listing,
    create_player_listing,
)


@pytest.fixture
def auction_database(tmp_path: Path):
    database_path = tmp_path / "auction.db"
    upgrade_database(database_path)
    engine = make_engine(database_path)
    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        session.add_all(
            [
                Character(id="mira-coppervale", name="Mira Coppervale", active=True),
                Character(id="inactive-character", name="Inactive", active=False),
                NPC(id=1, name="Test Buyer", archetype="Buyer", is_buyer=True, is_seller=True),
                NPC(id=2, name="Seller Only", archetype="Seller", is_buyer=False, is_seller=True),
                NPC(id=3, name="Inactive Buyer", archetype="Buyer", is_buyer=True, active=False),
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


def test_npc_purchase_of_player_listing_records_proceeds(auction_database, items_by_id) -> None:
    listing_id = create_player_listing(
        auction_database,
        items_by_id,
        "mira-coppervale",
        "redleaf-tonic",
        2,
        "7.25",
        14,
    )

    transaction = purchase_listing(
        auction_database,
        listing_id,
        BuyerContext(buyer_type="NPC", npc_id=1),
    )

    assert transaction.seller_type == "PLAYER"
    assert transaction.seller_character_id == "mira-coppervale"
    assert transaction.buyer_type == "NPC"
    assert transaction.buyer_npc_id == 1
    assert transaction.item_id == "redleaf-tonic"
    assert transaction.quantity == 2
    assert transaction.unit_price == 7.25
    assert transaction.total_price == 14.50
    assert transaction.player_sale_proceeds == 14.50
    sales = get_character_sales(auction_database, items_by_id, "mira-coppervale")
    assert sales[0].item_name == "Redleaf Tonic"
    assert sales[0].player_sale_proceeds == 14.50
    assert "Mira Coppervale" == sales[0].seller_name

    with auction_database() as session:
        listing = session.get(Listing, listing_id)
        assert listing.status == "SOLD"
        assert listing.remaining_quantity == 0
        assert listing.sold_at is not None


def test_player_purchase_of_npc_listing_does_not_create_proceeds(auction_database, items_by_id) -> None:
    listing_id = create_npc_listing(
        auction_database,
        items_by_id,
        1,
        "witchlight-lantern",
        1,
        92,
        14,
    )

    transaction = purchase_listing(
        auction_database,
        listing_id,
        BuyerContext(buyer_type="PLAYER", character_id="mira-coppervale"),
    )

    assert transaction.seller_type == "NPC"
    assert transaction.seller_npc_id == 1
    assert transaction.buyer_type == "PLAYER"
    assert transaction.buyer_character_id == "mira-coppervale"
    assert transaction.player_sale_proceeds is None
    assert get_character_sales(auction_database, items_by_id, "mira-coppervale") == []


def test_npc_to_npc_purchase_is_not_player_proceeds(auction_database, items_by_id) -> None:
    listing_id = create_npc_listing(auction_database, items_by_id, 2, "moonstone-dust", 3, 10, 14)

    transaction = purchase_listing(
        auction_database,
        listing_id,
        BuyerContext(buyer_type="NPC", npc_id=1),
    )

    assert transaction.seller_type == "NPC"
    assert transaction.buyer_type == "NPC"
    assert transaction.player_sale_proceeds is None
    assert get_recent_transactions(auction_database, items_by_id)[0].item_name == "Moonstone Dust"


def test_listing_cannot_be_purchased_twice(auction_database, items_by_id) -> None:
    listing_id = create_player_listing(
        auction_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, 10, 14
    )
    buyer = BuyerContext(buyer_type="NPC", npc_id=1)
    purchase_listing(auction_database, listing_id, buyer)

    with pytest.raises(ListingNotActiveError):
        purchase_listing(auction_database, listing_id, buyer)

    with auction_database() as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1


def test_invalid_or_self_buyer_leaves_listing_active(auction_database, items_by_id) -> None:
    listing_id = create_player_listing(
        auction_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, 10, 14
    )

    with pytest.raises(InvalidBuyerError, match="own listing"):
        purchase_listing(
            auction_database,
            listing_id,
            BuyerContext(buyer_type="PLAYER", character_id="mira-coppervale"),
        )
    with pytest.raises(InvalidBuyerError, match="active NPC buyer"):
        purchase_listing(
            auction_database,
            listing_id,
            BuyerContext(buyer_type="NPC", npc_id=2),
        )
    with pytest.raises(InvalidBuyerError, match="active campaign character"):
        purchase_listing(
            auction_database,
            listing_id,
            BuyerContext(buyer_type="PLAYER", character_id="inactive-character"),
        )

    with auction_database() as session:
        assert session.get(Listing, listing_id).status == "ACTIVE"
        assert session.scalar(select(func.count(Transaction.id))) == 0


def test_expired_listing_is_not_purchased(auction_database, items_by_id) -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    listing_id = create_player_listing(
        auction_database,
        items_by_id,
        "mira-coppervale",
        "redleaf-tonic",
        1,
        10,
        1,
        now=created_at,
    )

    with pytest.raises(ListingNotActiveError, match="not active"):
        purchase_listing(
            auction_database,
            listing_id,
            BuyerContext(buyer_type="NPC", npc_id=1),
            now=created_at + timedelta(days=2),
        )

    with auction_database() as session:
        assert session.get(Listing, listing_id).status == "EXPIRED"
        assert session.scalar(select(func.count(Transaction.id))) == 0


def test_failed_transaction_write_rolls_back_listing_update(auction_database, items_by_id, monkeypatch) -> None:
    listing_id = create_player_listing(
        auction_database, items_by_id, "mira-coppervale", "redleaf-tonic", 1, 10, 14
    )

    def fail_transaction(**kwargs):
        raise RuntimeError("simulated transaction insert failure")

    monkeypatch.setattr(auction_service, "Transaction", fail_transaction)
    with pytest.raises(RuntimeError, match="simulated transaction insert failure"):
        purchase_listing(
            auction_database,
            listing_id,
            BuyerContext(buyer_type="NPC", npc_id=1),
        )

    with auction_database() as session:
        assert session.get(Listing, listing_id).status == "ACTIVE"
        assert session.scalar(select(func.count(Transaction.id))) == 0