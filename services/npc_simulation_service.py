import json
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from database.models import AppSetting, Listing, MarketPrice, NPC, utc_now
from services.auction_service import BuyerContext, purchase_listing
from services.catalog_service import CatalogItem
from services.listing_service import (
    ListingError,
    NpcPreferences,
    create_npc_listing,
    expire_listings,
)


logger = logging.getLogger(__name__)
SIMULATION_SETTINGS_KEY = "npc_simulation"
MAX_NPC_CANDIDATE_LISTINGS = 500
_CYCLE_LOCK = Lock()


class NpcSimulationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: int = Field(default=300, ge=30, le=86400)
    activity_intensity: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    max_active_listings: int = Field(default=100, ge=0, le=5000)
    max_transactions_per_cycle: int = Field(default=10, ge=0, le=100)
    max_new_listings_per_cycle: int = Field(default=5, ge=0, le=100)


@dataclass(frozen=True)
class NpcSimulationResult:
    listings_created: int = 0
    transactions_completed: int = 0
    skipped: bool = False
    disabled: bool = False


@dataclass(frozen=True)
class _ListingCandidate:
    id: int
    item_id: str
    owner_type: str
    npc_id: int | None
    quantity: int
    asking_price: Decimal


def default_npc_simulation_settings(settings: Settings) -> NpcSimulationSettings:
    return NpcSimulationSettings(
        enabled=settings.npc_simulation_enabled,
        interval_seconds=settings.npc_simulation_interval_seconds,
        activity_intensity=settings.npc_activity_intensity,
        max_active_listings=settings.max_npc_listings,
        max_transactions_per_cycle=settings.max_npc_transactions_per_cycle,
        max_new_listings_per_cycle=settings.max_npc_new_listings_per_cycle,
    )


def load_npc_simulation_settings(
    session_factory: sessionmaker[Session],
    defaults: NpcSimulationSettings,
) -> NpcSimulationSettings:
    with session_factory.begin() as session:
        stored = session.get(AppSetting, SIMULATION_SETTINGS_KEY)
        if stored is None:
            session.add(
                AppSetting(
                    key=SIMULATION_SETTINGS_KEY,
                    value=defaults.model_dump_json(),
                    updated_at=utc_now(),
                )
            )
            return defaults
        try:
            return NpcSimulationSettings.model_validate_json(stored.value)
        except ValidationError:
            logger.exception("Stored NPC simulation settings are invalid; restoring configured defaults")
            stored.value = defaults.model_dump_json()
            stored.updated_at = utc_now()
            return defaults


def save_npc_simulation_settings(
    session_factory: sessionmaker[Session],
    simulation_settings: NpcSimulationSettings,
) -> None:
    with session_factory.begin() as session:
        stored = session.get(AppSetting, SIMULATION_SETTINGS_KEY)
        if stored is None:
            stored = AppSetting(key=SIMULATION_SETTINGS_KEY, value=simulation_settings.model_dump_json())
            session.add(stored)
        else:
            stored.value = simulation_settings.model_dump_json()
            stored.updated_at = utc_now()
    logger.info(
        "Saved NPC simulation settings (enabled=%s, interval=%ss, intensity=%s)",
        simulation_settings.enabled,
        simulation_settings.interval_seconds,
        simulation_settings.activity_intensity,
    )


def _read_preferences(npc: NPC):
    try:
        return NpcPreferences.model_validate_json(npc.preferences_json or "{}")
    except ValidationError:
        logger.warning("NPC %s has invalid preferences; using default behavior", npc.id)
        return NpcPreferences()


def _item_matches_preferences(item: CatalogItem, preferences) -> bool:
    if preferences.preferred_categories and item.category not in preferences.preferred_categories:
        return False
    if preferences.preferred_rarities and item.rarity not in preferences.preferred_rarities:
        return False
    return True


def _price_for_npc_listing(
    item: CatalogItem,
    current_prices: dict[str, Decimal],
    spread: float,
    rng: random.Random,
) -> Decimal:
    market_price = current_prices.get(item.id, item.base_price)
    adjusted = market_price * Decimal(str(1 + rng.uniform(-spread, spread)))
    price = adjusted.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(Decimal("1"), price)


def run_npc_simulation_cycle(
    session_factory: sessionmaker[Session],
    items: list[CatalogItem],
    settings: Settings,
    simulation_settings: NpcSimulationSettings | None = None,
    *,
    manual: bool = False,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> NpcSimulationResult:
    if not _CYCLE_LOCK.acquire(blocking=False):
        logger.info("Skipping NPC simulation cycle because another cycle is running")
        return NpcSimulationResult(skipped=True)

    try:
        current_time = now or datetime.now(UTC)
        current_time = current_time.replace(tzinfo=UTC) if current_time.tzinfo is None else current_time.astimezone(UTC)
        active_settings = simulation_settings or load_npc_simulation_settings(
            session_factory,
            default_npc_simulation_settings(settings),
        )
        if not active_settings.enabled and not manual:
            return NpcSimulationResult(disabled=True)

        generator = rng or random.Random()
        enabled_items = [item for item in items if item.enabled]
        items_by_id = {item.id: item for item in enabled_items}
        if not enabled_items:
            return NpcSimulationResult()

        expire_listings(session_factory, current_time)
        with session_factory() as session:
            npcs = session.scalars(
                select(NPC).where(NPC.active.is_(True), or_(NPC.is_buyer.is_(True), NPC.is_seller.is_(True)))
            ).all()
            profiles = [(npc.id, npc.is_buyer, npc.is_seller, _read_preferences(npc)) for npc in npcs]
            active_npc_listing_count = session.scalar(
                select(func.count(Listing.id)).where(Listing.owner_type == "NPC", Listing.status == "ACTIVE")
            ) or 0
            current_prices = {
                item_id: price
                for item_id, price in session.execute(
                    select(MarketPrice.item_id, MarketPrice.market_price)
                ).all()
            }
            candidates = [
                _ListingCandidate(
                    id=listing.id,
                    item_id=listing.item_id,
                    owner_type=listing.owner_type,
                    npc_id=listing.npc_id,
                    quantity=listing.remaining_quantity,
                    asking_price=listing.asking_price,
                )
                for listing in session.scalars(
                    select(Listing)
                    .where(Listing.status == "ACTIVE", Listing.remaining_quantity > 0)
                    .order_by(Listing.created_at, Listing.id)
                    .limit(MAX_NPC_CANDIDATE_LISTINGS)
                ).all()
            ]

        intensity = float(active_settings.activity_intensity)
        active_cap = min(active_settings.max_active_listings, settings.max_npc_listings)
        listing_cycle_cap = min(active_settings.max_new_listings_per_cycle, settings.max_npc_new_listings_per_cycle)
        transaction_cap = min(active_settings.max_transactions_per_cycle, settings.max_npc_transactions_per_cycle)
        listing_slots = max(0, min(active_cap - int(active_npc_listing_count), listing_cycle_cap))
        listings_created = 0

        sellers = [profile for profile in profiles if profile[2] and profile[3].seller_listing_probability > 0]
        generator.shuffle(sellers)
        for npc_id, _is_buyer, _is_seller, preferences in sellers:
            if listings_created >= listing_slots:
                break
            if generator.random() >= preferences.seller_listing_probability * intensity:
                continue
            possible_items = [item for item in enabled_items if _item_matches_preferences(item, preferences)]
            if not possible_items:
                possible_items = enabled_items
            item = generator.choice(possible_items)
            quantity = generator.randint(1, 3) if item.stackable else 1
            asking_price = _price_for_npc_listing(
                item,
                current_prices,
                preferences.seller_price_spread,
                generator,
            )
            try:
                create_npc_listing(
                    session_factory,
                    items_by_id,
                    npc_id,
                    item.id,
                    quantity,
                    asking_price,
                    settings.default_listing_expiration_days,
                    now=current_time,
                )
                listings_created += 1
            except ListingError:
                logger.exception("NPC %s failed to create a simulated listing", npc_id)

        transactions_completed = 0
        buyers = [profile for profile in profiles if profile[1] and profile[3].buyer_purchase_probability > 0]
        generator.shuffle(buyers)
        generator.shuffle(candidates)
        for npc_id, _is_buyer, _is_seller, preferences in buyers:
            if transactions_completed >= transaction_cap:
                break
            remaining_budget = preferences.buyer_budget_per_cycle
            for candidate in candidates:
                if transactions_completed >= transaction_cap:
                    break
                item = items_by_id.get(candidate.item_id)
                if item is None or (candidate.owner_type == "NPC" and candidate.npc_id == npc_id):
                    continue
                if not _item_matches_preferences(item, preferences):
                    continue
                market_price = current_prices.get(item.id, item.base_price)
                if candidate.asking_price > market_price * preferences.buyer_price_ceiling_multiplier:
                    continue
                total_price = candidate.asking_price * candidate.quantity
                if total_price > remaining_budget:
                    continue
                probability = min(1.0, preferences.buyer_purchase_probability * intensity)
                if generator.random() >= probability:
                    continue
                try:
                    purchase_listing(
                        session_factory,
                        candidate.id,
                        BuyerContext(buyer_type="NPC", npc_id=npc_id),
                        now=current_time,
                    )
                except ListingError:
                    continue
                transactions_completed += 1
                remaining_budget -= total_price

        result = NpcSimulationResult(listings_created, transactions_completed)
        logger.info(
            "NPC simulation cycle completed: %s listings created, %s purchases recorded",
            result.listings_created,
            result.transactions_completed,
        )
        return result
    finally:
        _CYCLE_LOCK.release()