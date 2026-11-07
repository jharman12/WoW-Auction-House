"""Add current market prices and price history.

Revision ID: 0003_market_prices_and_history
Revises: 0002_unique_listing_transaction
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_market_prices_and_history"
down_revision = "0002_unique_listing_transaction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_prices",
        sa.Column("item_id", sa.String(length=120), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("active_supply", sa.Integer(), nullable=False),
        sa.Column("recent_quantity_sold", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market_price > 0", name="ck_market_prices_positive"),
        sa.CheckConstraint("active_supply >= 0", name="ck_market_prices_supply_nonnegative"),
        sa.CheckConstraint("recent_quantity_sold >= 0", name="ck_market_prices_demand_nonnegative"),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.create_table(
        "market_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.String(length=120), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("active_supply", sa.Integer(), nullable=False),
        sa.Column("recent_quantity_sold", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market_price > 0", name="ck_market_history_price_positive"),
        sa.CheckConstraint("active_supply >= 0", name="ck_market_history_supply_nonnegative"),
        sa.CheckConstraint("recent_quantity_sold >= 0", name="ck_market_history_demand_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_history_item_recorded",
        "market_history",
        ["item_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_history_item_recorded", table_name="market_history")
    op.drop_table("market_history")
    op.drop_table("market_prices")