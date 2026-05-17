"""add group a metric and incident enums

Revision ID: c3f8a2d1e905
Revises: 6aa45ceda9ec
Create Date: 2026-05-05

"""

from alembic import op

revision = "c3f8a2d1e905"
down_revision = "6aa45ceda9ec"
branch_labels = None
depends_on = None

NEW_METRIC_VALUES = [
    "MEMORY_LEAK",
    "FD_RATIO",
    "LT_MEMORY",
    "LT_DISK",
]

NEW_INCIDENT_VALUES = [
    "MEMORY_LEAK",
    "FD_EXHAUSTION",
]


def upgrade() -> None:
    for v in NEW_METRIC_VALUES:
        op.execute(f"ALTER TYPE metrictypeenum ADD VALUE IF NOT EXISTS '{v}'")
    for v in NEW_INCIDENT_VALUES:
        op.execute(f"ALTER TYPE incidenttypeenum ADD VALUE IF NOT EXISTS '{v}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without type recreation.
    pass
