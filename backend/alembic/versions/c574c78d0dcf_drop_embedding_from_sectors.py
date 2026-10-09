"""drop embedding from sectors

This column was Stage 3's copy of the sector vectors. LangChain keeps its own
copy in langchain_pg_embedding, which this migration does not touch.

The downgrade brings the column back EMPTY: nothing writes these vectors any
more, so there is nothing to restore. The vector extension stays, because
LangChain's tables need it.

Revision ID: c574c78d0dcf
Revises: 56e0971d2083
Create Date: 2026-10-09 14:49:38.438508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'c574c78d0dcf'
down_revision: Union[str, Sequence[str], None] = '56e0971d2083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("sectors", "embedding")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("sectors", sa.Column("embedding", Vector(dim=1024), nullable=True))
