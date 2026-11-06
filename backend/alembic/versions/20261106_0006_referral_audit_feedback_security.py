"""referral follow-up, consent, audit log, result feedback, invites, MFA, password reset"""

from alembic import op
import sqlalchemy as sa


revision = "20261106_0006"
down_revision = "20261106_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("password_reset_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_reset_expires", sa.DateTime(), nullable=True))
    op.add_column("predictions", sa.Column("follow_up", sa.String(length=24), nullable=True))
    op.add_column("predictions", sa.Column("follow_up_note", sa.Text(), nullable=True))
    op.add_column("predictions", sa.Column("follow_up_at", sa.DateTime(), nullable=True))
    op.add_column("predictions", sa.Column("consent_at", sa.DateTime(), nullable=True))
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_prediction_id", "audit_events", ["prediction_id"])
    op.create_table(
        "result_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(),
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("actual_diagnosis", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_result_feedback_prediction_id", "result_feedback", ["prediction_id"])
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("invites")
    op.drop_index("ix_result_feedback_prediction_id", table_name="result_feedback")
    op.drop_table("result_feedback")
    op.drop_index("ix_audit_events_prediction_id", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")
    for col in ("consent_at", "follow_up_at", "follow_up_note", "follow_up"):
        op.drop_column("predictions", col)
    for col in ("password_reset_expires", "password_reset_hash", "mfa_enabled", "mfa_secret"):
        op.drop_column("users", col)
