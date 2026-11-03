"""same-patient reference photo and three-way assessment"""

from alembic import op
import sqlalchemy as sa


revision = "20261104_0004"
down_revision = "20261014_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("reference_filename", sa.String(length=255), nullable=True))
    op.add_column("predictions", sa.Column("reference_status", sa.String(length=16), nullable=True))
    op.add_column("predictions", sa.Column("assessment", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("predictions", "assessment")
    op.drop_column("predictions", "reference_status")
    op.drop_column("predictions", "reference_filename")
