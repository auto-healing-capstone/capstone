"""rename approved_at_by to reviewed_at_by

Revision ID: 6aa45ceda9ec
Revises: b093a147e92c
Create Date: 2026-05-02 12:00:17.411905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6aa45ceda9ec'
down_revision: Union[str, Sequence[str], None] = 'b093a147e92c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('recovery_actions', 'approved_at', new_column_name='reviewed_at')
    op.alter_column('recovery_actions', 'approved_by', new_column_name='reviewed_by')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('recovery_actions', 'reviewed_at', new_column_name='approved_at')
    op.alter_column('recovery_actions', 'reviewed_by', new_column_name='approved_by')
