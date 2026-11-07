from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NPC(Base):
    __tablename__ = "npcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    archetype: Mapped[str | None] = mapped_column(String(120))
    is_buyer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_seller: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    preferences_json: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("owner_type IN ('PLAYER', 'NPC')", name="ck_listings_owner_type"),
        CheckConstraint("status IN ('ACTIVE', 'SOLD', 'EXPIRED', 'CANCELLED')", name="ck_listings_status"),
        CheckConstraint(
            "(owner_type = 'PLAYER' AND character_id IS NOT NULL AND npc_id IS NULL) OR "
            "(owner_type = 'NPC' AND npc_id IS NOT NULL AND character_id IS NULL)",
            name="ck_listings_owner_reference",
        ),
        CheckConstraint("quantity > 0", name="ck_listings_quantity_positive"),
        CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_listings_remaining_quantity",
        ),
        CheckConstraint("asking_price > 0", name="ck_listings_asking_price_positive"),
        Index("ix_listings_status_item", "status", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(10), nullable=False)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    npc_id: Mapped[int | None] = mapped_column(ForeignKey("npcs.id"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    asking_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("seller_type IN ('PLAYER', 'NPC')", name="ck_transactions_seller_type"),
        CheckConstraint("buyer_type IN ('PLAYER', 'NPC')", name="ck_transactions_buyer_type"),
        CheckConstraint(
            "(seller_type = 'PLAYER' AND seller_character_id IS NOT NULL AND seller_npc_id IS NULL) OR "
            "(seller_type = 'NPC' AND seller_npc_id IS NOT NULL AND seller_character_id IS NULL)",
            name="ck_transactions_seller_reference",
        ),
        CheckConstraint(
            "(buyer_type = 'PLAYER' AND buyer_character_id IS NOT NULL AND buyer_npc_id IS NULL) OR "
            "(buyer_type = 'NPC' AND buyer_npc_id IS NOT NULL AND buyer_character_id IS NULL)",
            name="ck_transactions_buyer_reference",
        ),
        CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
        CheckConstraint("unit_price > 0 AND total_price > 0", name="ck_transactions_price_positive"),
        UniqueConstraint("listing_id", name="uq_transactions_listing_id"),
        Index("ix_transactions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(String(120), nullable=False)
    seller_type: Mapped[str] = mapped_column(String(10), nullable=False)
    seller_character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    seller_npc_id: Mapped[int | None] = mapped_column(ForeignKey("npcs.id"))
    buyer_type: Mapped[str] = mapped_column(String(10), nullable=False)
    buyer_character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    buyer_npc_id: Mapped[int | None] = mapped_column(ForeignKey("npcs.id"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    player_sale_proceeds: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class AppSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)