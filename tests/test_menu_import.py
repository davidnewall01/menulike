"""Tests for commit_extracted_menu — building a draft menu tree from extraction JSON."""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.schemas.extraction import ExtractedMenu
from app.services import menu_service
from app.services.exceptions import NoSiteInScope
from app.services.menu_service import _parse_price
from tests.conftest import make_menu, make_site


# ---------------------------------------------------------------------------
# Porto Azzurro extraction fixture (realistic subset — 7 sections)
# ---------------------------------------------------------------------------

PORTO_EXTRACTION = {
    "menu_name": "Porto Azzurro",
    "menu_note": "All prices GST inclusive",
    "ignored": ["Allergy disclaimer"],
    "sections": [
        {
            "name": "ENTRÉE",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Bruschetta",
                            "description": "Toasted sourdough with tomato, basil, garlic",
                            "dietary_tags": ["V"],
                            "variants": [{"label": None, "price": "16.90"}],
                            "extras": [],
                        },
                        {
                            "name": "Arancini",
                            "description": "Crumbed risotto balls with napoli sauce",
                            "dietary_tags": ["V"],
                            "variants": [{"label": None, "price": "14.90"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "INSALATA",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Nostra Salad",
                            "description": "Mixed leaves, cherry tomato, cucumber, red onion",
                            "dietary_tags": ["V", "GF"],
                            "variants": [{"label": None, "price": "15.90"}],
                            "extras": [
                                {"label": "Chicken extra", "price": "6.00"},
                            ],
                        },
                    ],
                }
            ],
        },
        {
            "name": "PASTA",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Spaghetti Bolognese",
                            "description": "Traditional meat sauce",
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "24.90"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "PIZZAS",
            "note": "Gluten free base +$6 per pizza. NO HALF PIZZAS.",
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Margherita",
                            "description": "Tomato, mozzarella, basil",
                            "dietary_tags": ["V"],
                            "variants": [{"label": None, "price": "22.90"}],
                            "extras": [],
                        },
                        {
                            "name": "Pepperoni",
                            "description": "Tomato, mozzarella, pepperoni",
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "24.90"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "SIDES",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Garlic Bread",
                            "description": None,
                            "dietary_tags": ["V"],
                            "variants": [
                                {"label": "Plain", "price": "8.90"},
                                {"label": "With cheese", "price": "10.90"},
                            ],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "KIDS",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Kids Pasta",
                            "description": "Choice of bolognese or napoli",
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "12.90"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "DOLCI",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Tiramisu",
                            "description": "Classic Italian dessert",
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "14.90"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
    ],
}


def _auth_ctx(site):
    return AuthContext(
        user_id=uuid.uuid4(),
        email="test@test.dev",
        role="owner",
        site_id=site.site_id,
    )


async def _load_menu_tree(db: AsyncSession, menu_id: uuid.UUID) -> Menu:
    """Reload a menu with the full tree eagerly loaded."""
    result = await db.execute(
        select(Menu)
        .where(Menu.menu_id == menu_id)
        .options(
            selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants)
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# _parse_price unit tests
# ---------------------------------------------------------------------------


class TestParsePrice:
    def test_normal_price(self):
        assert _parse_price("16.90") == Decimal("16.90")

    def test_dollar_sign(self):
        assert _parse_price("$16.90") == Decimal("16.90")

    def test_whitespace(self):
        assert _parse_price("  $16.90  ") == Decimal("16.90")

    def test_none(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_unparseable(self):
        assert _parse_price("market price") is None

    def test_negative(self):
        assert _parse_price("-5.00") is None

    def test_zero(self):
        assert _parse_price("0.00") == Decimal("0.00")


# ---------------------------------------------------------------------------
# commit_extracted_menu integration tests
# ---------------------------------------------------------------------------


class TestCommitExtractedMenu:
    async def test_creates_unpublished_menu(self, db_session):
        site = await make_site(db_session, slug="import1", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        assert menu.menu_id is not None
        assert menu.name == "Porto Azzurro"
        assert menu.is_published is False
        assert menu.site_id == site.site_id

    async def test_seven_sections_correct_names_and_order(self, db_session):
        site = await make_site(db_session, slug="import2", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        assert len(menu.sections) == 7
        expected_names = [
            "ENTRÉE", "INSALATA", "PASTA", "PIZZAS", "SIDES", "KIDS", "DOLCI",
        ]
        actual_names = [s.name for s in menu.sections]
        assert actual_names == expected_names

    async def test_section_positions_sequential(self, db_session):
        site = await make_site(db_session, slug="import3", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        positions = [s.position for s in menu.sections]
        assert positions == [10, 20, 30, 40, 50, 60, 70]

    async def test_pizzas_section_note(self, db_session):
        site = await make_site(db_session, slug="import4", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        pizzas = [s for s in menu.sections if s.name == "PIZZAS"][0]
        assert pizzas.note == "Gluten free base +$6 per pizza. NO HALF PIZZAS."

    async def test_nostra_salad_extras(self, db_session):
        site = await make_site(db_session, slug="import5", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        insalata = [s for s in menu.sections if s.name == "INSALATA"][0]
        nostra = insalata.subsections[0].items[0]
        assert nostra.name == "Nostra Salad"
        assert nostra.extras == [{"label": "Chicken extra", "price": "6.00"}]

    async def test_variant_prices_parsed_to_decimal(self, db_session):
        site = await make_site(db_session, slug="import6", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        bruschetta = menu.sections[0].subsections[0].items[0]
        assert bruschetta.name == "Bruschetta"
        assert len(bruschetta.variants) == 1
        assert bruschetta.variants[0].price == Decimal("16.90")

    async def test_dietary_tags_preserved(self, db_session):
        site = await make_site(db_session, slug="import7", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        nostra = menu.sections[1].subsections[0].items[0]
        assert nostra.dietary_tags == ["V", "GF"]

    async def test_multiple_variants(self, db_session):
        site = await make_site(db_session, slug="import8", name="Import Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        sides = [s for s in menu.sections if s.name == "SIDES"][0]
        garlic_bread = sides.subsections[0].items[0]
        assert len(garlic_bread.variants) == 2
        assert garlic_bread.variants[0].label == "Plain"
        assert garlic_bread.variants[0].price == Decimal("8.90")
        assert garlic_bread.variants[1].label == "With cheese"
        assert garlic_bread.variants[1].price == Decimal("10.90")

    async def test_null_price_variant_skipped(self, db_session):
        """An item with a null-price variant should still be created, minus the variant."""
        site = await make_site(db_session, slug="import9", name="Import Site")
        data = {
            "menu_name": "Test",
            "sections": [{
                "name": "Sec",
                "subsections": [{
                    "name": None,
                    "items": [{
                        "name": "Mystery Dish",
                        "variants": [{"label": None, "price": None}],
                    }],
                }],
            }],
        }
        extracted = ExtractedMenu.model_validate(data)
        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()

        menu = await _load_menu_tree(db_session, menu.menu_id)
        item = menu.sections[0].subsections[0].items[0]
        assert item.name == "Mystery Dish"
        assert len(item.variants) == 0

    async def test_menu_position_after_existing(self, db_session):
        site = await make_site(db_session, slug="import10", name="Import Site")
        await make_menu(db_session, site, name="Existing", position=10)

        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)
        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site), extracted
        )
        await db_session.flush()
        assert menu.position == 20

    async def test_scoped_to_site(self, db_session):
        """Menu is created under auth_ctx.scoped_site_id, not some other site."""
        site_a = await make_site(db_session, slug="importa", name="Site A")
        site_b = await make_site(db_session, slug="importb", name="Site B")

        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)
        menu = await menu_service.commit_extracted_menu(
            db_session, _auth_ctx(site_a), extracted
        )
        await db_session.flush()

        assert menu.site_id == site_a.site_id
        assert menu.site_id != site_b.site_id

    async def test_no_site_in_scope_raises(self, db_session):
        auth = AuthContext(
            user_id=uuid.uuid4(),
            email="test@test.dev",
            role="owner",
            site_id=None,
        )
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)
        with pytest.raises(NoSiteInScope):
            await menu_service.commit_extracted_menu(db_session, auth, extracted)

    async def test_rollback_on_failure(self, db_session):
        """If the service raises during build, the menu is not flushed to DB.

        The coordinator wraps commit_extracted_menu in one commit. If the
        service raises, the coordinator never commits. We verify the error
        propagates and no menu row reaches the DB.
        """
        site = await make_site(db_session, slug="importfail", name="Fail Site")
        extracted = ExtractedMenu.model_validate(PORTO_EXTRACTION)

        original_flush = db_session.flush

        async def failing_flush(*args, **kwargs):
            raise RuntimeError("Simulated DB failure")

        with patch.object(db_session, "flush", side_effect=failing_flush):
            with pytest.raises(RuntimeError, match="Simulated DB failure"):
                await menu_service.commit_extracted_menu(
                    db_session, _auth_ctx(site), extracted
                )

        # The menu was db.add'd but never flushed — rollback clears it
        await db_session.rollback()

        result = await db_session.execute(
            select(Menu).where(
                Menu.site_id == site.site_id,
                Menu.name == "Porto Azzurro",
            )
        )
        assert result.scalar_one_or_none() is None
