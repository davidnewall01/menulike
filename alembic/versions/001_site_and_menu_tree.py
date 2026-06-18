"""site and menu tree

Revision ID: 001
Revises:
Create Date: 2026-06-18 13:20:56.556794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- site --
    op.create_table(
        "site",
        sa.Column("site_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("restaurant_name", sa.String, nullable=False),
        sa.Column("tagline", sa.String, nullable=True),
        sa.Column("hero_heading", sa.String, nullable=True),
        sa.Column("hero_subheading", sa.String, nullable=True),
        sa.Column("about_story", sa.Text, nullable=True),
        sa.Column("address_street", sa.String, nullable=True),
        sa.Column("address_suburb", sa.String, nullable=True),
        sa.Column("address_state", sa.String, nullable=True),
        sa.Column("address_postcode", sa.String, nullable=True),
        sa.Column("address_country", sa.String, nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("booking_url", sa.String, nullable=True),
        sa.Column("order_url", sa.String, nullable=True),
        sa.Column("meta_title", sa.String, nullable=True),
        sa.Column("meta_description", sa.String, nullable=True),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_site_slug", "site", ["slug"], unique=True)

    # -- menus --
    op.create_table(
        "menus",
        sa.Column("menu_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("availability_note", sa.String, nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_menus_site_id", "menus", ["site_id"])

    # -- sections --
    op.create_table(
        "sections",
        sa.Column("section_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "menu_id",
            UUID(as_uuid=True),
            sa.ForeignKey("menus.menu_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sections_menu_id", "sections", ["menu_id"])

    # -- subsections --
    op.create_table(
        "subsections",
        sa.Column("subsection_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sections.section_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subsections_section_id", "subsections", ["section_id"])

    # -- menu_items --
    op.create_table(
        "menu_items",
        sa.Column("menu_item_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subsection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subsections.subsection_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("dietary_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("featured", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_menu_items_subsection_id", "menu_items", ["subsection_id"])

    # -- menu_item_variants --
    op.create_table(
        "menu_item_variants",
        sa.Column("menu_item_variant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "menu_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("menu_items.menu_item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_menu_item_variants_menu_item_id", "menu_item_variants", ["menu_item_id"])


def downgrade() -> None:
    op.drop_table("menu_item_variants")
    op.drop_table("menu_items")
    op.drop_table("subsections")
    op.drop_table("sections")
    op.drop_table("menus")
    op.drop_table("site")
