"""record which models and thresholds produced each analysis"""

from alembic import op
import sqlalchemy as sa


revision = "20261106_0005"
down_revision = "20261104_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("model_version", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("predictions", "model_version")
