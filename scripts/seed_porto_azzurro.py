"""Seed Porto Azzurro with representative content.

Idempotent: if a site with slug "portoazzurro" exists, it is deleted (cascade
clears the tree) before inserting fresh. Re-running always gives the same state.

Usage:
    python -m scripts.seed_porto_azzurro
"""

import asyncio
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.menu import (  # noqa: E402
    Menu,
    MenuItem,
    MenuItemVariant,
    Section,
    Subsection,
)
from app.models.site import Site  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _v(price: str, label: str | None = None, position: int = 10) -> MenuItemVariant:
    """Shorthand for a variant."""
    return MenuItemVariant(
        label=label,
        price=Decimal(price),
        position=position,
    )


def _item(
    name: str,
    position: int,
    description: str | None = None,
    dietary_tags: list | None = None,
    featured: bool = False,
    variants: list[MenuItemVariant] | None = None,
) -> MenuItem:
    """Shorthand for a menu item."""
    return MenuItem(
        name=name,
        description=description,
        dietary_tags=dietary_tags or [],
        featured=featured,
        position=position,
        variants=variants or [],
    )


def build_site() -> Site:
    return Site(
        slug="portoazzurro",
        restaurant_name="Porto Azzurro",
        tagline="Authentic Italian by the harbour",
        address_street="12 Wharf Road",
        address_suburb="Surry Hills",
        address_state="NSW",
        address_postcode="2010",
        address_country="Australia",
        latitude=Decimal("-33.886100"),
        longitude=Decimal("151.210300"),
        phone="(02) 9123 4567",
        email="hello@portoazzurro.com.au",
        booking_url="https://portoazzurro.com.au/book",
        order_url="https://portoazzurro.com.au/order",
        settings={},
        menus=[
            build_dinner_menu(),
            build_drinks_menu(),
        ],
    )


def build_dinner_menu() -> Menu:
    return Menu(
        name="Dinner",
        description="Our evening menu, crafted daily from seasonal produce.",
        availability_note="Served from 5:30 pm",
        position=10,
        sections=[
            # --- To Start ---
            Section(
                name="To Start",
                position=10,
                subsections=[
                    Subsection(
                        name="Bread",
                        position=10,
                        items=[
                            _item("Focaccia al Rosmarino", 10,
                                  description="House-baked rosemary focaccia with extra virgin olive oil",
                                  variants=[_v("8.00")]),
                            _item("Bruschetta Classica", 20,
                                  description="Grilled sourdough, vine tomatoes, basil, aged balsamic",
                                  variants=[_v("12.00")]),
                        ],
                    ),
                    Subsection(
                        name="Antipasti",
                        position=20,
                        items=[
                            _item("Arancini di Funghi", 10,
                                  description="Crispy risotto balls with wild mushroom and truffle mayo",
                                  dietary_tags=["vegetarian"],
                                  variants=[_v("16.00")]),
                            _item("Carpaccio di Manzo", 20,
                                  description="Thinly sliced beef, rocket, parmesan, lemon dressing",
                                  variants=[_v("19.00")]),
                        ],
                    ),
                ],
            ),
            # --- Pizza ---
            Section(
                name="Pizza",
                position=20,
                subsections=[
                    Subsection(
                        name=None,  # unnamed — headingless passthrough
                        position=10,
                        items=[
                            _item("Margherita", 10,
                                  description="San Marzano tomato, fior di latte, basil",
                                  variants=[
                                      _v("18.00", "Small", 10),
                                      _v("24.00", "Large", 20),
                                  ]),
                            _item("Diavola", 20,
                                  description="Spicy salami, roasted capsicum, chilli, mozzarella",
                                  featured=True,
                                  variants=[
                                      _v("20.00", "Small", 10),
                                      _v("26.00", "Large", 20),
                                  ]),
                            _item("Quattro Formaggi", 30,
                                  description="Mozzarella, gorgonzola, fontina, parmesan",
                                  dietary_tags=["vegetarian"],
                                  variants=[
                                      _v("19.00", "Small", 10),
                                      _v("25.00", "Large", 20),
                                  ]),
                        ],
                    ),
                ],
            ),
            # --- Mains ---
            Section(
                name="Mains",
                position=30,
                subsections=[
                    Subsection(
                        name=None,
                        position=10,
                        items=[
                            _item("Risotto al Nero di Seppia", 10,
                                  description="Squid ink risotto with prawns, calamari and lemon gremolata",
                                  variants=[_v("32.00")]),
                            _item("Pollo alla Parmigiana", 20,
                                  description="Crumbed chicken breast, napoli sauce, mozzarella, chips",
                                  variants=[_v("28.00")]),
                            _item("Linguine ai Frutti di Mare", 30,
                                  description="Prawns, mussels, clams, calamari in white wine and garlic",
                                  variants=[_v("34.00")]),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_drinks_menu() -> Menu:
    return Menu(
        name="Drinks",
        availability_note="Available all day",
        position=20,
        sections=[
            Section(
                name="Wine",
                position=10,
                subsections=[
                    Subsection(
                        name="Red",
                        position=10,
                        items=[
                            _item("Chianti Classico", 10,
                                  description="Tuscany, Italy",
                                  variants=[
                                      _v("14.00", "Glass", 10),
                                      _v("58.00", "Bottle", 20),
                                  ]),
                            _item("Nero d'Avola", 20,
                                  description="Sicily, Italy",
                                  variants=[
                                      _v("13.00", "Glass", 10),
                                      _v("52.00", "Bottle", 20),
                                  ]),
                        ],
                    ),
                    Subsection(
                        name="White",
                        position=20,
                        items=[
                            _item("Pinot Grigio", 10,
                                  description="Veneto, Italy",
                                  variants=[
                                      _v("13.00", "Glass", 10),
                                      _v("54.00", "Bottle", 20),
                                  ]),
                            _item("Vermentino", 20,
                                  description="Sardinia, Italy",
                                  variants=[
                                      _v("14.00", "Glass", 10),
                                      _v("56.00", "Bottle", 20),
                                  ]),
                        ],
                    ),
                ],
            ),
        ],
    )


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # Delete existing site if present (cascade clears the tree)
        result = await session.execute(
            select(Site).where(Site.slug == "portoazzurro")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.flush()
            print("Deleted existing portoazzurro site.")

        site = build_site()
        session.add(site)
        await session.commit()

        # Report counts
        print(f"Site: {site.restaurant_name} (id={site.site_id})")
        menu_count = len(site.menus)
        section_count = sum(len(m.sections) for m in site.menus)
        subsection_count = sum(
            len(s.subsections) for m in site.menus for s in m.sections
        )
        item_count = sum(
            len(sub.items)
            for m in site.menus
            for s in m.sections
            for sub in s.subsections
        )
        variant_count = sum(
            len(i.variants)
            for m in site.menus
            for s in m.sections
            for sub in s.subsections
            for i in sub.items
        )
        print(f"  menus: {menu_count}")
        print(f"  sections: {section_count}")
        print(f"  subsections: {subsection_count}")
        print(f"  menu_items: {item_count}")
        print(f"  menu_item_variants: {variant_count}")


if __name__ == "__main__":
    asyncio.run(main())
