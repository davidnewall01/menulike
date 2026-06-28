"""023 -- Template metadata tables + seed from TEMPLATE_CATALOG.

Three tables for admin-editable template metadata:
  - template_meta: one row per template look (linen/slate/olive)
  - tag_vocabulary: the managed set of allowed tag values
  - template_tag: join table (CASCADE both sides — removing a vocab
    tag or a template cleanly drops join rows)

Seeded from the existing TEMPLATE_CATALOG code constant values.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

# Seed data — mirrors the existing TEMPLATE_CATALOG dict exactly
_TEMPLATES = [
    ("linen", "Linen", "Warm and refined — perfect for trattorias, wine bars, and focused menus."),
    ("slate", "Slate", "Dark and dramatic — ideal for cocktail bars, steakhouses, and moody dining rooms."),
    ("olive", "Olive", "Fresh and inviting — great for brunch spots, garden cafes, and casual eateries."),
]

_TAGS = {
    "linen": ["warm", "refined", "cafe", "italian", "wine-bar"],
    "slate": ["dark", "dramatic", "cocktail-bar", "steakhouse", "modern"],
    "olive": ["fresh", "casual", "brunch", "garden", "inviting"],
}


def upgrade() -> None:
    # template_meta
    op.create_table(
        "template_meta",
        sa.Column("template_key", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("descriptor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # tag_vocabulary
    op.create_table(
        "tag_vocabulary",
        sa.Column(
            "tag_id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("value", sa.String(), nullable=False, unique=True),
    )

    # template_tag join
    op.create_table(
        "template_tag",
        sa.Column(
            "template_key",
            sa.String(),
            sa.ForeignKey("template_meta.template_key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tag_vocabulary.tag_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # --- Seed ---
    meta_table = sa.table(
        "template_meta",
        sa.column("template_key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("descriptor", sa.Text),
    )
    op.bulk_insert(meta_table, [
        {"template_key": k, "display_name": n, "descriptor": d}
        for k, n, d in _TEMPLATES
    ])

    # Collect unique tags across all templates
    all_tags = sorted({t for tags in _TAGS.values() for t in tags})
    vocab_table = sa.table(
        "tag_vocabulary",
        sa.column("tag_id", sa.Integer),
        sa.column("value", sa.String),
    )
    op.bulk_insert(vocab_table, [
        {"tag_id": i + 1, "value": v} for i, v in enumerate(all_tags)
    ])
    tag_id_map = {v: i + 1 for i, v in enumerate(all_tags)}

    join_table = sa.table(
        "template_tag",
        sa.column("template_key", sa.String),
        sa.column("tag_id", sa.Integer),
    )
    join_rows = []
    for tpl_key, tags in _TAGS.items():
        for tag in tags:
            join_rows.append({"template_key": tpl_key, "tag_id": tag_id_map[tag]})
    op.bulk_insert(join_table, join_rows)


def downgrade() -> None:
    op.drop_table("template_tag")
    op.drop_table("tag_vocabulary")
    op.drop_table("template_meta")
