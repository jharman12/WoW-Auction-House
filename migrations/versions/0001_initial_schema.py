"""Create the initial marketplace schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "npcs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("archetype", sa.String(length=120), nullable=True),
        sa.Column("is_buyer", sa.Boolean(), nullable=False),
        sa.Column("is_seller", sa.Boolean(), nullable=False),
        sa.Column("preferences_json", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.String(length=120), nullable=False),
        sa.Column("owner_type", sa.String(length=10), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=True),
        sa.Column("npc_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column("asking_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("owner_type IN ('PLAYER', 'NPC')", name="ck_listings_owner_type"),
        sa.CheckConstraint("status IN ('ACTIVE', 'SOLD', 'EXPIRED', 'CANCELLED')", name="ck_listings_status"),
        sa.CheckConstraint(
            "(owner_type = 'PLAYER' AND character_id IS NOT NULL AND npc_id IS NULL) OR "
            "(owner_type = 'NPC' AND npc_id IS NOT NULL AND character_id IS NULL)",
            name="ck_listings_owner_reference",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_listings_quantity_positive"),
        sa.CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_listings_remaining_quantity",
        ),
        sa.CheckConstraint("asking_price > 0", name="ck_listings_asking_price_positive"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["npc_id"], ["npcs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listings_status_item", "listings", ["status", "item_id"])
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=120), nullable=False),
        sa.Column("seller_type", sa.String(length=10), nullable=False),
        sa.Column("seller_character_id", sa.String(length=64), nullable=True),
        sa.Column("seller_npc_id", sa.Integer(), nullable=True),
        sa.Column("buyer_type", sa.String(length=10), nullable=False),
        sa.Column("buyer_character_id", sa.String(length=64), nullable=True),
        sa.Column("buyer_npc_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("player_sale_proceeds", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.CheckConstraint("seller_type IN ('PLAYER', 'NPC')", name="ck_transactions_seller_type"),
        sa.CheckConstraint("buyer_type IN ('PLAYER', 'NPC')", name="ck_transactions_buyer_type"),
        sa.CheckConstraint(
            "(seller_type = 'PLAYER' AND seller_character_id IS NOT NULL AND seller_npc_id IS NULL) OR "
            "(seller_type = 'NPC' AND seller_npc_id IS NOT NULL AND seller_character_id IS NULL)",
            name="ck_transactions_seller_reference",
        ),
        sa.CheckConstraint(
            "(buyer_type = 'PLAYER' AND buyer_character_id IS NOT NULL AND buyer_npc_id IS NULL) OR "
            "(buyer_type = 'NPC' AND buyer_npc_id IS NOT NULL AND buyer_character_id IS NULL)",
            name="ck_transactions_buyer_reference",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
        sa.CheckConstraint("unit_price > 0 AND total_price > 0", name="ck_transactions_price_positive"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["seller_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["seller_npc_id"], ["npcs.id"]),
        sa.ForeignKeyConstraint(["buyer_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["buyer_npc_id"], ["npcs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_created_at", "transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_transactions_created_at", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_listings_status_item", table_name="listings")
    op.drop_table("listings")
    op.drop_table("settings")
    op.drop_table("npcs")
    op.drop_table("characters")