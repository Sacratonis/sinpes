"""clean usage labels from public font names

Revision ID: 012
Revises: 011
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


RENAMES = (
    ("bright-melody-personal-use-only", "bright-melody", "Bright Melody", "Bright Melody Personal Use Only"),
    ("gigxa-free-personal-use", "gigxa", "Gigxa", "Gigxa Free Personal Use"),
    ("gosna-trial", "gosna", "Gosna", "Gosna TRIAL"),
    ("konexy-personal-use", "konexy", "Konexy", "Konexy Personal Use"),
    ("ktf-rublena-trial", "ktf-rublena", "KTF Rublena", "KTF Rublena Trial"),
    ("stainger-personal-use", "stainger", "Stainger", "Stainger Personal Use"),
)


def upgrade() -> None:
    # Keep every font. Only remove source-site usage labels from public names and slugs.
    op.execute("PRAGMA defer_foreign_keys = ON")
    for old_slug, new_slug, display_name, _old_display_name in RENAMES:
        op.execute(
            f"""UPDATE font_registry
                SET slug = '{new_slug}', display_name = '{display_name}'
                WHERE slug = '{old_slug}'
                  AND NOT EXISTS (SELECT 1 FROM font_registry WHERE slug = '{new_slug}')"""
        )
        op.execute(
            f"""UPDATE font_translations SET slug = '{new_slug}'
                WHERE slug = '{old_slug}'
                  AND EXISTS (SELECT 1 FROM font_registry WHERE slug = '{new_slug}')"""
        )


def downgrade() -> None:
    op.execute("PRAGMA defer_foreign_keys = ON")
    for old_slug, new_slug, _display_name, old_display_name in reversed(RENAMES):
        op.execute(
            f"""UPDATE font_registry
                SET slug = '{old_slug}', display_name = '{old_display_name}'
                WHERE slug = '{new_slug}'
                  AND NOT EXISTS (SELECT 1 FROM font_registry WHERE slug = '{old_slug}')"""
        )
        op.execute(
            f"""UPDATE font_translations SET slug = '{old_slug}'
                WHERE slug = '{new_slug}'
                  AND EXISTS (SELECT 1 FROM font_registry WHERE slug = '{old_slug}')"""
        )
