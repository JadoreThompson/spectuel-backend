"""x

Revision ID: fb67ac07623d
Revises: f461fc47194c
Create Date: 2025-11-30 18:59:04.986646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb67ac07623d'
down_revision: Union[str, Sequence[str], None] = 'f461fc47194c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    # UUID columns whose server default should be updated:
    uuid_updates = [
        ("users", "user_id"),
        ("instruments", "instrument_id"),
        ("orders", "order_id"),
        ("trades", "trade_id"),
        ("transactions", "transaction_id"),
        ("engine_context_snapshots", "snapshot_id"),
        # Add if uncommented later:
        # ("engine_snapshots", "snapshot_id"),
    ]

    for table, col in uuid_updates:
        op.alter_column(
            table,
            col,
            server_default=sa.text("gen_random_uuid()"),
            existing_type=sa.UUID(),
        )


def downgrade():
    # Revert to no server default
    uuid_updates = [
        ("users", "user_id"),
        ("instruments", "instrument_id"),
        ("orders", "order_id"),
        ("trades", "trade_id"),
        ("transactions", "transaction_id"),
        ("engine_context_snapshots", "snapshot_id"),
        # ("engine_snapshots", "snapshot_id"),
    ]

    for table, col in uuid_updates:
        op.alter_column(
            table,
            col,
            server_default=None,
            existing_type=sa.dialects.postgresql.UUID(),
        )

