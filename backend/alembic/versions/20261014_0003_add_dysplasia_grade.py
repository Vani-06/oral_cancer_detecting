"""store the predicted dysplasia grade with each prediction"""

from alembic import op
import sqlalchemy as sa


revision = "20261014_0003"
down_revision = "20260827_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("dysplasia_grade", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("predictions", "dysplasia_grade")
