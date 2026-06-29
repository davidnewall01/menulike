"""025 -- Register Crema template.

Warm, rustic, casual cafe template. Split-layout front page with
section-grid menu selector. Incomplete (front page only) — is_available=false.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

# Template metadata
_KEY = "crema"
_NAME = "Crema"
_DESCRIPTOR = (
    "Warm and rustic — built for neighbourhood cafes, brunch spots, "
    "and casual eateries with photo-forward menus."
)
_TAGS = ["warm", "rustic", "cafe", "casual", "brunch", "photo-forward"]


def upgrade() -> None:
    # Insert template_meta row
    op.execute(
        sa.text(
            "INSERT INTO template_meta (template_key, display_name, descriptor, is_available) "
            "VALUES (:key, :name, :desc, false)"
        ).bindparams(key=_KEY, name=_NAME, desc=_DESCRIPTOR)
    )

    # Fix autoincrement sequence (023 bulk-inserted with explicit IDs)
    op.execute(sa.text(
        "SELECT setval('tag_vocabulary_tag_id_seq', "
        "(SELECT COALESCE(MAX(tag_id), 0) FROM tag_vocabulary))"
    ))

    # Ensure tags exist and associate them
    for tag_name in _TAGS:
        # Insert tag if not exists
        op.execute(
            sa.text(
                "INSERT INTO tag_vocabulary (value) VALUES (:val) "
                "ON CONFLICT (value) DO NOTHING"
            ).bindparams(val=tag_name)
        )
        # Link tag to template
        op.execute(
            sa.text(
                "INSERT INTO template_tag (template_key, tag_id) "
                "SELECT :key, tag_id FROM tag_vocabulary WHERE value = :val"
            ).bindparams(key=_KEY, val=tag_name)
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM template_tag WHERE template_key = :key").bindparams(key=_KEY)
    )
    op.execute(
        sa.text("DELETE FROM template_meta WHERE template_key = :key").bindparams(key=_KEY)
    )
