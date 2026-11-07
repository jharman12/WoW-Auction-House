from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from database.models import Listing, MarketHistory, MarketPrice, Transaction
from services.catalog_service import CatalogItem
from services.listing_service import expire_listings


@dataclass(frozen=True)
class PriceCalculation:
    market_price: Decimal
    raw_price: Decimal
    supply_multiplier: Decimal
    demand_multiplier: Decimal
    combined_multiplier: Decimal


@dataclass(frozen=True)
class MarketPriceView:
    item_id: str
    item_name: str
    base_price: Decimal
    market_price: Decimal
    active_supply: int
    recent_quantity_sold: int
    recorded_at: datetime


@dataclass(frozen=True)
class MarketHistoryPoint:
    market_price: Decimal
    active_supply: int
    recent_quantity_sold: int
    recorded_at: datetime


def _clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return min(max(value, minimum), maximum)


def _round_within_bounds(value: Decimal, increment: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    rounded = (value / increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * increment
    if rounded < lower:
        rounded = (lower / increment).quantize(Decimal("1"), rounding=ROUND_CEILING) * increment
    if rounded > upper:
        rounded = (upper / increment).quantize(Decimal("1"), rounding=ROUND_FLOOR) * increment
    return _clamp(rounded, lower, upper)


def calculate_market_price(
    base_price: Decimal,
    active_supply: int,
    recent_quantity_sold: int,
    previous_market_price: Decimal | None,
    settings: Settings,
) -> PriceCalculation:
    base_price = Decimal(base_price)
    if not base_price.is_finite() or base_price <= 0:
        raise ValueError("base_price must be a positive finite amount")
    if active_supply < 0 or recent_quantity_sold < 0:
        raise ValueError("supply and demand quantities cannot be negative")

    minimum_multiplier = Decimal(str(settings.minimum_price_multiplier))
    maximum_multiplier = Decimal(str(settings.maximum_price_multiplier))
    target_supply = Decimal(settings.economy_target_supply_quantity)
    supply_floor = target_supply / maximum_multiplier
    supply_multiplier = _clamp(
        target_supply / max(Decimal(active_supply), supply_floor),
        minimum_multiplier,
        maximum_multiplier,
    )

    target_demand = Decimal(settings.economy_target_demand_quantity)
    demand_multiplier = _clamp(
        (Decimal("1") + Decimal(recent_quantity_sold) / target_demand) / Decimal("2"),
        minimum_multiplier,
        maximum_multiplier,
    )
    combined_multiplier = _clamp(
        supply_multiplier * demand_multiplier,
        minimum_multiplier,
        maximum_multiplier,
    )

    maximum_price = base_price * maximum_multiplier
    minimum_price = min(
        maximum_price,
        max(base_price * minimum_multiplier, settings.economy_minimum_price_gp),
    )
    raw_price = _clamp(base_price * combined_multiplier, minimum_price, maximum_price)

    if previous_market_price is None:
        market_price = _round_within_bounds(
            raw_price,
            settings.economy_price_rounding_increment,
            minimum_price,
            maximum_price,
        )
    else:
        previous = Decimal(previous_market_price)
        if not previous.is_finite() or previous <= 0:
            raise ValueError("previous_market_price must be positive and finite")
        smoothing = settings.economy_smoothing_factor
        smoothed_price = previous + (raw_price - previous) * smoothing
        change_fraction = Decimal(str(settings.max_price_change_percent)) / Decimal("100")
        lower = max(minimum_price, previous * (Decimal("1") - change_fraction))
        upper = min(maximum_price, previous * (Decimal("1") + change_fraction))
        if lower > upper:
            lower = upper
        market_price = _round_within_bounds(
            _clamp(smoothed_price, lower, upper),
            settings.economy_price_rounding_increment,
            lower,
            upper,
        )

    return PriceCalculation(
        market_price=market_price,
        raw_price=raw_price,
        supply_multiplier=supply_multiplier,
        demand_multiplier=demand_multiplier,
        combined_multiplier=combined_multiplier,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def update_market_prices(
    session_factory: sessionmaker[Session],
    items: Sequence[CatalogItem],
    settings: Settings,
    now: datetime | None = None,
    record_history: bool = True,
) -> list[MarketPriceView]:
    recorded_at = _utc(now or datetime.now(UTC))
    expire_listings(session_factory, recorded_at)
    demand_since = recorded_at - timedelta(hours=settings.economy_demand_window_hours)
    item_ids = [item.id for item in items]
    if not item_ids:
        return []

    with session_factory() as session:
        supply_rows = session.execute(
            select(Listing.item_id, func.sum(Listing.remaining_quantity))
            .where(Listing.status == "ACTIVE", Listing.item_id.in_(item_ids))
            .group_by(Listing.item_id)
        ).all()
        demand_rows = session.execute(
            select(Transaction.item_id, func.sum(Transaction.quantity))
            .where(Transaction.item_id.in_(item_ids), Transaction.created_at >= demand_since)
            .group_by(Transaction.item_id)
        ).all()
        current_rows = session.scalars(select(MarketPrice).where(MarketPrice.item_id.in_(item_ids))).all()

    supply_by_item = {item_id: int(quantity or 0) for item_id, quantity in supply_rows}
    demand_by_item = {item_id: int(quantity or 0) for item_id, quantity in demand_rows}
    current_by_item = {row.item_id: row for row in current_rows}

    views: list[MarketPriceView] = []
    with session_factory.begin() as session:
        for item in items:
            active_supply = supply_by_item.get(item.id, 0)
            recent_quantity_sold = demand_by_item.get(item.id, 0)
            previous = current_by_item.get(item.id)
            calculation = calculate_market_price(
                item.base_price,
                active_supply,
                recent_quantity_sold,
                previous.market_price if previous else None,
                settings,
            )
            if previous is None:
                current = MarketPrice(
                    item_id=item.id,
                    market_price=calculation.market_price,
                    active_supply=active_supply,
                    recent_quantity_sold=recent_quantity_sold,
                    recorded_at=recorded_at,
                )
                session.add(current)
            else:
                current = session.get(MarketPrice, item.id)
                assert current is not None
                current.market_price = calculation.market_price
                current.active_supply = active_supply
                current.recent_quantity_sold = recent_quantity_sold
                current.recorded_at = recorded_at

            if record_history:
                session.add(
                    MarketHistory(
                        item_id=item.id,
                        market_price=calculation.market_price,
                        active_supply=active_supply,
                        recent_quantity_sold=recent_quantity_sold,
                        recorded_at=recorded_at,
                    )
                )
            views.append(
                MarketPriceView(
                    item_id=item.id,
                    item_name=item.name,
                    base_price=item.base_price,
                    market_price=calculation.market_price,
                    active_supply=active_supply,
                    recent_quantity_sold=recent_quantity_sold,
                    recorded_at=recorded_at,
                )
            )
    return views


def snapshot_market_history(
    session_factory: sessionmaker[Session],
    now: datetime | None = None,
) -> int:
    recorded_at = _utc(now or datetime.now(UTC))
    with session_factory.begin() as session:
        current_prices = session.scalars(select(MarketPrice).order_by(MarketPrice.item_id)).all()
        session.add_all(
            [
                MarketHistory(
                    item_id=current.item_id,
                    market_price=current.market_price,
                    active_supply=current.active_supply,
                    recent_quantity_sold=current.recent_quantity_sold,
                    recorded_at=recorded_at,
                )
                for current in current_prices
            ]
        )
    return len(current_prices)


def ensure_initial_market_prices(
    session_factory: sessionmaker[Session],
    items: Sequence[CatalogItem],
    settings: Settings,
) -> list[MarketPriceView]:
    with session_factory() as session:
        existing_ids = set(session.scalars(select(MarketPrice.item_id)).all())
    missing_items = [item for item in items if item.id not in existing_ids]
    return update_market_prices(session_factory, missing_items, settings) if missing_items else []


def get_current_market_prices(
    session_factory: sessionmaker[Session],
    items: Sequence[CatalogItem],
) -> list[MarketPriceView]:
    item_by_id = {item.id: item for item in items}
    with session_factory() as session:
        current_rows = session.scalars(
            select(MarketPrice).order_by(MarketPrice.item_id)
        ).all()
    return [
        MarketPriceView(
            item_id=row.item_id,
            item_name=item_by_id[row.item_id].name if row.item_id in item_by_id else row.item_id,
            base_price=item_by_id[row.item_id].base_price if row.item_id in item_by_id else row.market_price,
            market_price=row.market_price,
            active_supply=row.active_supply,
            recent_quantity_sold=row.recent_quantity_sold,
            recorded_at=row.recorded_at,
        )
        for row in current_rows
    ]


def get_market_history(
    session_factory: sessionmaker[Session],
    item_id: str,
    limit: int = 120,
) -> list[MarketHistoryPoint]:
    with session_factory() as session:
        rows = session.scalars(
            select(MarketHistory)
            .where(MarketHistory.item_id == item_id)
            .order_by(MarketHistory.recorded_at.desc(), MarketHistory.id.desc())
            .limit(min(max(1, limit), 1000))
        ).all()
    return [
        MarketHistoryPoint(
            market_price=row.market_price,
            active_supply=row.active_supply,
            recent_quantity_sold=row.recent_quantity_sold,
            recorded_at=row.recorded_at,
        )
        for row in reversed(rows)
    ]