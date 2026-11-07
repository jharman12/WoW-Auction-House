import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from database.models import Character, Listing, NPC, Transaction
from services.catalog_service import CatalogItem
from services.listing_service import (
    ListingError,
    ListingNotActiveError,
    ListingNotFoundError,
    expire_listings,
)


logger = logging.getLogger(__name__)
MAX_TRANSACTION_TOTAL = Decimal("9999999999.99")
PLAYER_SALE_LIMIT = 100
RECENT_TRANSACTION_LIMIT = 100


class PurchaseConflictError(ListingNotActiveError):
    """Raised when a concurrent operation has already changed the listing."""


class InvalidBuyerError(ListingError):
    """Raised when the buyer context is invalid or inactive."""


class BuyerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_type: Literal["PLAYER", "NPC"]
    character_id: str | None = None
    npc_id: int | None = None

    @model_validator(mode="after")
    def validate_owner_reference(self) -> "BuyerContext":
        if self.buyer_type == "PLAYER":
            if not self.character_id or self.npc_id is not None:
                raise ValueError("Player buyer context requires a character_id only")
        elif self.npc_id is None or self.character_id is not None:
            raise ValueError("NPC buyer context requires an npc_id only")
        return self


@dataclass(frozen=True)
class TransactionView:
    id: int
    listing_id: int
    item_id: str
    item_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    seller_type: str
    seller_name: str
    buyer_type: str
    buyer_name: str
    created_at: datetime
    player_sale_proceeds: Decimal | None


def _validate_purchase_price(value: Decimal) -> Decimal:
    try:
        price = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ListingError("The listing has an invalid asking price") from exc
    if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2:
        raise ListingError("The listing has an invalid asking price")
    return price


def _validate_buyer(session: Session, buyer: BuyerContext) -> str:
    if buyer.buyer_type == "PLAYER":
        character = session.get(Character, buyer.character_id)
        if character is None or not character.active:
            raise InvalidBuyerError("Select an active campaign character to purchase this listing")
        return character.name

    npc = session.get(NPC, buyer.npc_id)
    if npc is None or not npc.active or not npc.is_buyer:
        raise InvalidBuyerError("Select an active NPC buyer")
    return npc.name


def purchase_listing(
    session_factory: sessionmaker[Session],
    listing_id: int,
    buyer: BuyerContext,
    now: datetime | None = None,
) -> Transaction:
    current_time = now or datetime.now(UTC)
    current_time = current_time.replace(tzinfo=UTC) if current_time.tzinfo is None else current_time.astimezone(UTC)
    expire_listings(session_factory, current_time)

    with session_factory.begin() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise ListingNotFoundError(f"Listing {listing_id} was not found")
        if listing.status != "ACTIVE":
            raise ListingNotActiveError(f"Listing {listing_id} is not active")
        if listing.expires_at is not None:
            expires_at = listing.expires_at.replace(tzinfo=UTC) if listing.expires_at.tzinfo is None else listing.expires_at
            if expires_at <= current_time:
                raise ListingNotActiveError("The listing has expired and cannot be purchased")
        if listing.quantity <= 0 or listing.remaining_quantity != listing.quantity:
            raise ListingError("The listing quantity is invalid or has already been partially purchased")
        if listing.owner_type not in ("PLAYER", "NPC") or not listing.item_id:
            raise ListingError("The listing owner or item reference is invalid")

        unit_price = _validate_purchase_price(listing.asking_price)
        quantity = listing.remaining_quantity
        total_price = unit_price * quantity
        if total_price > MAX_TRANSACTION_TOTAL:
            raise ListingError("The total purchase price exceeds the supported range")

        buyer_name = _validate_buyer(session, buyer)
        if buyer.buyer_type == listing.owner_type:
            if buyer.buyer_type == "PLAYER" and buyer.character_id == listing.character_id:
                raise InvalidBuyerError("A character cannot purchase its own listing")
            if buyer.buyer_type == "NPC" and buyer.npc_id == listing.npc_id:
                raise InvalidBuyerError("An NPC cannot purchase its own listing")

        seller_character_id = listing.character_id if listing.owner_type == "PLAYER" else None
        seller_npc_id = listing.npc_id if listing.owner_type == "NPC" else None
        proceeds = total_price if listing.owner_type == "PLAYER" else None

        result = session.execute(
            update(Listing)
            .where(
                Listing.id == listing_id,
                Listing.status == "ACTIVE",
                Listing.remaining_quantity == listing.quantity,
                or_(Listing.expires_at.is_(None), Listing.expires_at > current_time),
            )
            .values(status="SOLD", remaining_quantity=0, sold_at=current_time)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise PurchaseConflictError(f"Listing {listing_id} was changed by another operation")

        transaction = Transaction(
            listing_id=listing.id,
            item_id=listing.item_id,
            seller_type=listing.owner_type,
            seller_character_id=seller_character_id,
            seller_npc_id=seller_npc_id,
            buyer_type=buyer.buyer_type,
            buyer_character_id=buyer.character_id,
            buyer_npc_id=buyer.npc_id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            created_at=current_time,
            player_sale_proceeds=proceeds,
        )
        session.add(transaction)
        session.flush()

    logger.info(
        "Recorded transaction %s for listing %s (%s gold)",
        transaction.id,
        listing_id,
        total_price,
    )
    return transaction


def _transaction_views(
    session: Session,
    transactions: list[Transaction],
    items_by_id: dict[str, CatalogItem],
) -> list[TransactionView]:
    character_ids = {
        identifier
        for transaction in transactions
        for identifier in (transaction.seller_character_id, transaction.buyer_character_id)
        if identifier is not None
    }
    npc_ids = {
        identifier
        for transaction in transactions
        for identifier in (transaction.seller_npc_id, transaction.buyer_npc_id)
        if identifier is not None
    }
    characters = {
        character.id: character.name
        for character in session.scalars(select(Character).where(Character.id.in_(character_ids))).all()
    } if character_ids else {}
    npcs = {
        npc.id: npc.name
        for npc in session.scalars(select(NPC).where(NPC.id.in_(npc_ids))).all()
    } if npc_ids else {}

    views = []
    for transaction in transactions:
        item = items_by_id.get(transaction.item_id)
        item_name = item.name if item else transaction.item_id
        seller_name = (
            characters.get(transaction.seller_character_id, "Campaign character")
            if transaction.seller_type == "PLAYER"
            else npcs.get(transaction.seller_npc_id, "Marketplace NPC")
        )
        buyer_name = (
            characters.get(transaction.buyer_character_id, "Campaign character")
            if transaction.buyer_type == "PLAYER"
            else npcs.get(transaction.buyer_npc_id, "Marketplace NPC")
        )
        views.append(
            TransactionView(
                id=transaction.id,
                listing_id=transaction.listing_id,
                item_id=transaction.item_id,
                item_name=item_name,
                quantity=transaction.quantity,
                unit_price=transaction.unit_price,
                total_price=transaction.total_price,
                seller_type=transaction.seller_type,
                seller_name=seller_name,
                buyer_type=transaction.buyer_type,
                buyer_name=buyer_name,
                created_at=transaction.created_at,
                player_sale_proceeds=transaction.player_sale_proceeds,
            )
        )
    return views


def get_character_sales(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    character_id: str,
    limit: int = PLAYER_SALE_LIMIT,
) -> list[TransactionView]:
    with session_factory() as session:
        transactions = session.scalars(
            select(Transaction)
            .where(Transaction.seller_type == "PLAYER", Transaction.seller_character_id == character_id)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .limit(min(max(1, limit), PLAYER_SALE_LIMIT))
        ).all()
        return _transaction_views(session, list(transactions), items_by_id)


def get_recent_transactions(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    limit: int = RECENT_TRANSACTION_LIMIT,
) -> list[TransactionView]:
    with session_factory() as session:
        transactions = session.scalars(
            select(Transaction)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .limit(min(max(1, limit), RECENT_TRANSACTION_LIMIT))
        ).all()
        return _transaction_views(session, list(transactions), items_by_id)