"""Prevent a listing from being recorded as sold more than once.

Revision ID: 0002_unique_listing_transaction
Revises: 0001_initial_schema
"""
from alembic import op


revision = "0002_unique_listing_transaction"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.create_unique_constraint("uq_transactions_listing_id", ["listing_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("uq_transactions_listing_id", type_="unique")