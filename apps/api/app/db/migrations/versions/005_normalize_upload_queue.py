"""normalize upload queue

Revision ID: 005
Revises: 004
"""

from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {
        row[1]
        for row in connection.exec_driver_sql("PRAGMA table_info(upload_queue)").fetchall()
    }
    if "attempts" not in columns:
        op.execute("ALTER TABLE upload_queue ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
    if "last_error" not in columns:
        op.execute("ALTER TABLE upload_queue ADD COLUMN last_error TEXT")
    if "failed" not in columns:
        op.execute("ALTER TABLE upload_queue ADD COLUMN failed BOOLEAN NOT NULL DEFAULT 0")


def downgrade() -> None:
    pass
