"""x

Revision ID: 0f93628573f7
Revises: fb67ac07623d
Create Date: 2025-11-30 19:31:41.373709

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f93628573f7"
down_revision: Union[str, Sequence[str], None] = "fb67ac07623d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Ensure NOW() defaults applied

    # USERS
    op.alter_column(
        "users",
        "created_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "users",
        "updated_at",
        server_default=sa.text("NOW()"),
        server_onupdate=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # ORDERS
    op.alter_column(
        "orders",
        "created_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "orders",
        "updated_at",
        server_default=sa.text("NOW()"),
        server_onupdate=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # TRADES
    op.alter_column(
        "trades",
        "executed_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # TRANSACTIONS
    op.alter_column(
        "transactions",
        "created_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade():
    # Remove server defaults (revert to None)
    # Note: You may add Python-side defaults back manually if desired.

    # USERS
    op.alter_column(
        "users",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )
    op.alter_column(
        "users",
        "updated_at",
        server_default=None,
        server_onupdate=None,
        existing_type=sa.DateTime(timezone=True),
    )

    # ORDERS
    op.alter_column(
        "orders",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )
    op.alter_column(
        "orders",
        "updated_at",
        server_default=None,
        server_onupdate=None,
        existing_type=sa.DateTime(timezone=True),
    )

    # TRADES
    op.alter_column(
        "trades",
        "executed_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )

    # TRANSACTIONS
    op.alter_column(
        "transactions",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )
