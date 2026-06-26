"""018 -- Custom domains table for arbitrary-host tenant resolution.

Maps external domains (e.g. portoazzurro.com.au) to sites. The domain
column is globally unique (the load-bearing security control: one tenant
per domain, ever). A partial unique index enforces at-most-one primary
domain per site at the DB level.

Revision ID: 018
Revises: 017
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_domain",
        sa.Column(
            "custom_domain_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("domain", sa.String, nullable=False, unique=True, index=True),
        sa.Column(
            "is_primary", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column(
            "status", sa.String, nullable=False, server_default="active"
        ),
        sa.Column("approximated_id", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # At most one primary domain per site, enforced at DB level.
    op.create_index(
        "ix_custom_domain_one_primary_per_site",
        "custom_domain",
        ["site_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_custom_domain_one_primary_per_site", table_name="custom_domain")
    op.drop_table("custom_domain")
