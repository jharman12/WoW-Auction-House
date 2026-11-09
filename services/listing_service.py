import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from database.models import Character, Listing, NPC
from services.catalog_service import CatalogItem, CatalogDataError
from services.category_taxonomy import CategoryFilterSelection


logger = logging.getLogger(__name__)
MAX_LISTING_RESULTS = 5000
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100


class ListingError(ValueError):
    """Base error for listing operations."""


class InvalidListingError(ListingError):
    """Raised when listing input or its references are invalid."""


class ListingNotFoundError(ListingError):
    """Raised when a listing does not exist."""


class ListingNotActiveError(ListingError):
    """Raised when a listing cannot transition from its current state."""


class ListingOwnerError(ListingError):
    """Raised when the requested owner cannot manage a listing."""


class NpcSeedListing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)
    quantity: int = Field(ge=1)
    asking_price: Decimal = Field(gt=Decimal("0"))


class NpcPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_categories: list[str] = Field(default_factory=list)
    preferred_rarities: list[str] = Field(default_factory=list)
    buyer_purchase_probability: float = Field(default=0.25, ge=0, le=1)
    buyer_price_ceiling_multiplier: Decimal = Field(default=Decimal("1.2"), gt=0, le=Decimal("10"))
    buyer_budget_per_cycle: Decimal = Field(default=Decimal("250"), ge=0)
    seller_listing_probability: float = Field(default=0.3, ge=0, le=1)
    seller_price_spread: float = Field(default=0.15, ge=0, le=0.75)


class NpcSellerSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    archetype: str = Field(min_length=1, max_length=120)
    is_buyer: bool = True
    is_seller: bool = True
    preferences: NpcPreferences = Field(default_factory=NpcPreferences)
    listings: list[NpcSeedListing] = Field(min_length=1)


class NpcMarketSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sellers: list[NpcSellerSeed] = Field(min_length=1)


@dataclass(frozen=True)
class ListingView:
    id: int
    item: CatalogItem
    owner_type: Literal["PLAYER", "NPC"]
    owner_id: str | int | None
    owner_name: str
    quantity: int
    asking_price: Decimal
    status: str
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class MarketplacePage:
    listings: list[ListingView]
    total_count: int
    page: int
    page_size: int
    truncated: bool = False


def load_npc_market_seed(path: Path) -> NpcMarketSeed:
    try:
        return NpcMarketSeed.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogDataError(f"Could not read NPC market seed '{path}': {exc}") from exc
    except ValidationError as exc:
        raise CatalogDataError(f"Invalid NPC market seed '{path}':\n{exc}") from exc


def _validate_price(value: Decimal | int | float | str) -> Decimal:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidListingError("Asking price must be a positive number") from exc
    if not price.is_finite() or price <= 0:
        raise InvalidListingError("Asking price must be a positive number")
    if price.as_tuple().exponent < -2 or price >= Decimal("10000000000"):
        raise InvalidListingError("Asking price must fit in the supported gold range (up to 2 decimal places)")
    return price


def _validate_listing_inputs(
    item_id: str,
    quantity: int,
    asking_price: Decimal | int | float | str,
    items_by_id: dict[str, CatalogItem],
) -> tuple[CatalogItem, Decimal]:
    item = items_by_id.get(item_id)
    if item is None or not item.enabled:
        raise InvalidListingError("Select an enabled item from the catalog")
    if type(quantity) is not int or quantity < 1:
        raise InvalidListingError("Quantity must be a positive whole number")
    if not item.stackable and quantity != 1:
        raise InvalidListingError("This item cannot be listed in a stack")
    return item, _validate_price(asking_price)


def _create_listing(
    session: Session,
    item: CatalogItem,
    owner_type: Literal["PLAYER", "NPC"],
    quantity: int,
    asking_price: Decimal,
    expiration_days: int,
    now: datetime | None = None,
    character_id: str | None = None,
    npc_id: int | None = None,
) -> Listing:
    if expiration_days < 1:
        raise InvalidListingError("Listing expiration must be at least one day")
    created_at = now or datetime.now(UTC)
    listing = Listing(
        item_id=item.id,
        owner_type=owner_type,
        character_id=character_id,
        npc_id=npc_id,
        quantity=quantity,
        remaining_quantity=quantity,
        asking_price=asking_price,
        status="ACTIVE",
        created_at=created_at,
        expires_at=created_at + timedelta(days=expiration_days),
    )
    session.add(listing)
    session.flush()
    return listing


def create_player_listing(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    character_id: str,
    item_id: str,
    quantity: int,
    asking_price: Decimal | int | float | str,
    expiration_days: int,
    now: datetime | None = None,
) -> int:
    item, price = _validate_listing_inputs(item_id, quantity, asking_price, items_by_id)
    with session_factory.begin() as session:
        character = session.get(Character, character_id)
        if character is None or not character.active:
            raise InvalidListingError("Select an active campaign character")
        listing = _create_listing(
            session,
            item,
            "PLAYER",
            quantity,
            price,
            expiration_days,
            now=now,
            character_id=character_id,
        )
    logger.info("Created player listing %s for character %s", listing.id, character_id)
    return listing.id


def create_npc_listing(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    npc_id: int,
    item_id: str,
    quantity: int,
    asking_price: Decimal | int | float | str,
    expiration_days: int,
    now: datetime | None = None,
) -> int:
    item, price = _validate_listing_inputs(item_id, quantity, asking_price, items_by_id)
    with session_factory.begin() as session:
        npc = session.get(NPC, npc_id)
        if npc is None or not npc.active or not npc.is_seller:
            raise InvalidListingError("Select an active NPC seller")
        listing = _create_listing(
            session,
            item,
            "NPC",
            quantity,
            price,
            expiration_days,
            now=now,
            npc_id=npc_id,
        )
    logger.info("Created NPC listing %s for NPC %s", listing.id, npc_id)
    return listing.id


def seed_npc_marketplace(
    session_factory: sessionmaker[Session],
    seed: NpcMarketSeed,
    items_by_id: dict[str, CatalogItem],
    expiration_days: int,
) -> int:
    for seller in seed.sellers:
        for listing in seller.listings:
            item = items_by_id.get(listing.item_id)
            if item is None or not item.enabled:
                raise InvalidListingError(f"NPC seed references unavailable item '{listing.item_id}'")
            _validate_listing_inputs(listing.item_id, listing.quantity, listing.asking_price, items_by_id)

    created_count = 0
    with session_factory.begin() as session:
        for seller in seed.sellers:
            npc = session.scalar(select(NPC).where(NPC.name == seller.name))
            if npc is None:
                npc = NPC(name=seller.name, archetype=seller.archetype)
                session.add(npc)
                session.flush()
            npc.archetype = seller.archetype
            npc.is_buyer = seller.is_buyer
            npc.is_seller = seller.is_seller
            npc.preferences_json = json.dumps(
                seller.preferences.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )

            existing_listing_id = session.scalar(
                select(Listing.id).where(Listing.npc_id == npc.id).limit(1)
            )
            if existing_listing_id is not None:
                continue

            for listing_seed in seller.listings:
                _create_listing(
                    session,
                    items_by_id[listing_seed.item_id],
                    "NPC",
                    listing_seed.quantity,
                    listing_seed.asking_price,
                    expiration_days,
                    npc_id=npc.id,
                )
                created_count += 1
    if created_count:
        logger.info("Seeded %s NPC market listings", created_count)
    return created_count


def expire_listings(session_factory: sessionmaker[Session], now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    with session_factory.begin() as session:
        result = session.execute(
            update(Listing)
            .where(
                Listing.status == "ACTIVE",
                Listing.expires_at.is_not(None),
                Listing.expires_at <= current_time,
            )
            .values(status="EXPIRED")
        )
        expired_count = result.rowcount or 0
    if expired_count:
        logger.info("Expired %s listings", expired_count)
    return expired_count


def cancel_listing(
    session_factory: sessionmaker[Session],
    listing_id: int,
    character_id: str | None = None,
    allow_any_owner: bool = False,
) -> None:
    with session_factory.begin() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise ListingNotFoundError(f"Listing {listing_id} was not found")
        if listing.status != "ACTIVE":
            raise ListingNotActiveError(f"Listing {listing_id} is not active")
        if not allow_any_owner:
            if listing.owner_type != "PLAYER" or listing.character_id != character_id:
                raise ListingOwnerError("This character cannot cancel that listing")
        listing.status = "CANCELLED"
    logger.info("Cancelled listing %s", listing_id)


def _listing_views(
    session: Session,
    listings: list[Listing],
    items_by_id: dict[str, CatalogItem],
) -> list[ListingView]:
    character_ids = {listing.character_id for listing in listings if listing.character_id is not None}
    npc_ids = {listing.npc_id for listing in listings if listing.npc_id is not None}
    characters = {
        character.id: character.name
        for character in session.scalars(select(Character).where(Character.id.in_(character_ids))).all()
    } if character_ids else {}
    npcs = {
        npc.id: npc.name
        for npc in session.scalars(select(NPC).where(NPC.id.in_(npc_ids))).all()
    } if npc_ids else {}

    views = []
    for listing in listings:
        item = items_by_id.get(listing.item_id)
        if item is None:
            continue
        owner_name = (
            characters.get(listing.character_id, "Campaign character")
            if listing.owner_type == "PLAYER"
            else npcs.get(listing.npc_id, "Marketplace NPC")
        )
        views.append(
            ListingView(
                id=listing.id,
                item=item,
                owner_type=listing.owner_type,
                owner_id=listing.character_id if listing.owner_type == "PLAYER" else listing.npc_id,
                owner_name=owner_name,
                quantity=listing.remaining_quantity,
                asking_price=listing.asking_price,
                status=listing.status,
                created_at=listing.created_at,
                expires_at=listing.expires_at,
            )
        )
    return views


def get_marketplace(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    search: str = "",
    category: str = "all",
    rarity: str = "all",
    sort_by: str = "newest",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    filter_selection: CategoryFilterSelection | None = None,
) -> MarketplacePage:
    expire_listings(session_factory)
    page = max(1, page)
    page_size = min(MAX_PAGE_SIZE, max(1, page_size))
    allowed_sorts = {"price_asc", "price_desc", "name", "rarity", "oldest", "newest"}
    if sort_by not in allowed_sorts:
        sort_by = "newest"

    with session_factory() as session:
        rows = session.scalars(
            select(Listing)
            .where(Listing.status == "ACTIVE")
            .order_by(Listing.created_at.desc(), Listing.id.desc())
            .limit(MAX_LISTING_RESULTS)
        ).all()
        listings = _listing_views(session, list(rows), items_by_id)

    normalized_search = search.strip().casefold()
    filtered = [
        listing
        for listing in listings
        if (category == "all" or listing.item.category == category)
        and (
            filter_selection is None
            or not filter_selection.categories
            or listing.item.category in filter_selection.categories
        )
        and (
            filter_selection is None
            or all(tag in listing.item.tags for tag in filter_selection.required_tags)
        )
        and (rarity == "all" or listing.item.rarity == rarity)
        and (
            not normalized_search
            or normalized_search in listing.item.name.casefold()
            or normalized_search in listing.item.id.casefold()
            or any(normalized_search in tag.casefold() for tag in listing.item.tags)
        )
    ]

    rarity_order = {"common": 0, "uncommon": 1, "rare": 2, "very_rare": 3, "legendary": 4, "artifact": 5}
    if sort_by == "price_asc":
        filtered.sort(key=lambda listing: (listing.asking_price, listing.item.name.casefold()))
    elif sort_by == "price_desc":
        filtered.sort(key=lambda listing: (-listing.asking_price, listing.item.name.casefold()))
    elif sort_by == "name":
        filtered.sort(key=lambda listing: listing.item.name.casefold())
    elif sort_by == "rarity":
        filtered.sort(key=lambda listing: (rarity_order.get(listing.item.rarity, 6), listing.item.rarity, listing.item.name.casefold()))
    elif sort_by == "oldest":
        filtered.sort(key=lambda listing: (listing.created_at, listing.id))
    else:
        filtered.sort(key=lambda listing: (listing.created_at, listing.id), reverse=True)

    total_count = len(filtered)
    start = (page - 1) * page_size
    return MarketplacePage(
        listings=filtered[start : start + page_size],
        total_count=total_count,
        page=page,
        page_size=page_size,
        truncated=len(rows) == MAX_LISTING_RESULTS,
    )


def get_character_active_listings(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    character_id: str,
) -> list[ListingView]:
    expire_listings(session_factory)
    with session_factory() as session:
        rows = session.scalars(
            select(Listing)
            .where(Listing.status == "ACTIVE", Listing.owner_type == "PLAYER", Listing.character_id == character_id)
            .order_by(Listing.created_at.desc(), Listing.id.desc())
            .limit(MAX_LISTING_RESULTS)
        ).all()
        return _listing_views(session, list(rows), items_by_id)


def get_admin_active_listings(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
) -> list[ListingView]:
    expire_listings(session_factory)
    with session_factory() as session:
        rows = session.scalars(
            select(Listing)
            .where(Listing.status == "ACTIVE")
            .order_by(Listing.created_at.desc(), Listing.id.desc())
            .limit(MAX_LISTING_RESULTS)
        ).all()
        return _listing_views(session, list(rows), items_by_id)


def get_listing_view(
    session_factory: sessionmaker[Session],
    items_by_id: dict[str, CatalogItem],
    listing_id: int,
) -> ListingView | None:
    expire_listings(session_factory)
    with session_factory() as session:
        listing = session.get(Listing, listing_id)
        if listing is None or listing.status != "ACTIVE":
            return None
        return next(iter(_listing_views(session, [listing], items_by_id)), None)