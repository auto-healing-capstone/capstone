"""add peak_yhat to predictions

Revision ID: a1b2c3d4e5f6
Revises: c3f8a2d1e905
Create Date: 2026-05-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c3f8a2d1e905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("peak_yhat", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("predictions", "peak_yhat")
