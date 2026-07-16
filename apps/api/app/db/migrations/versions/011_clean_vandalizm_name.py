"""clean Vandalizm family name

Revision ID: 011
Revises: 010
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


OLD_SLUG = "vandalizm-by-album-art-archive"
NEW_SLUG = "vandalizm"


def upgrade() -> None:
    # This family is still queued. Keep its existing R2 object URLs, but expose a
    # professional display name and page slug. Deferred FK checks keep the parent
    # and localized rows consistent within the migration transaction.
    op.execute("PRAGMA defer_foreign_keys = ON")
    op.execute(
        f"""UPDATE font_registry
            SET slug = '{NEW_SLUG}', display_name = 'Vandalizm'
            WHERE slug = '{OLD_SLUG}'
              AND NOT EXISTS (SELECT 1 FROM font_registry WHERE slug = '{NEW_SLUG}')"""
    )
    op.execute(
        f"""UPDATE font_translations SET slug = '{NEW_SLUG}'
            WHERE slug = '{OLD_SLUG}'
              AND EXISTS (SELECT 1 FROM font_registry WHERE slug = '{NEW_SLUG}')"""
    )


def downgrade() -> None:
    op.execute("PRAGMA defer_foreign_keys = ON")
    op.execute(
        f"""UPDATE font_registry
            SET slug = '{OLD_SLUG}', display_name = 'Vandalizm By Album Art Archive'
            WHERE slug = '{NEW_SLUG}'
              AND NOT EXISTS (SELECT 1 FROM font_registry WHERE slug = '{OLD_SLUG}')"""
    )
    op.execute(
        f"""UPDATE font_translations SET slug = '{OLD_SLUG}'
            WHERE slug = '{NEW_SLUG}'
              AND EXISTS (SELECT 1 FROM font_registry WHERE slug = '{OLD_SLUG}')"""
    )
