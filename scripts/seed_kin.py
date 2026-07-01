"""Seed "Kin" — a Crema-template cafe demo.

Idempotent: if a site with slug "kin" exists, it is deleted (cascade clears the
tree) before inserting fresh. Refuses to run unless ENVIRONMENT=development.

Pairs with Porto Azzurro to demo both hours-summary styles:
  - Porto (labelled)   -> "Lunch — Fri–Sun … / Dinner — Tue–Sun …"
  - Kin   (unlabelled) -> "Mon–Sat 9:00am – 5:00pm / Sun 9:00am – 12:00pm"

Usage:
    python -m scripts.seed_kin
"""

import asyncio
import sys
import uuid
from datetime import time
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

if settings.ENVIRONMENT != "development":
    print(f"FATAL: seed scripts are dev-only (ENVIRONMENT={settings.ENVIRONMENT})")
    sys.exit(1)
from app.models.location import Location  # noqa: E402
from app.models.menu import (  # noqa: E402
    Menu,
    MenuItem,
    MenuItemVariant,
    Section,
    Subsection,
)
from app.models.regular_hours import RegularHours  # noqa: E402
from app.models.site import Site  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _v(price: str, label: str | None = None, position: int = 10) -> MenuItemVariant:
    return MenuItemVariant(label=label, price=Decimal(price), position=position)


def _item(name, position, description=None, dietary_tags=None, featured=False, variants=None) -> MenuItem:
    return MenuItem(
        name=name, description=description, dietary_tags=dietary_tags or [],
        featured=featured, position=position, variants=variants or [],
    )


def build_site() -> Site:
    return Site(
        slug="kin",
        restaurant_name="Kin",
        template="crema",
        tagline="That cosy place with the garden",
        address_street="14A Stockton Street",
        address_suburb="Anna Bay",
        address_state="NSW",
        address_postcode="2316",
        address_country="Australia",
        latitude=Decimal("-32.780000"),
        longitude=Decimal("152.090000"),
        phone="0412 455 686",
        email="hello@kincafe.com",
        booking_url="https://kincafe.com/book",
        settings={},
        menus=[build_all_day_menu(), build_coffee_menu()],
    )


def build_location(site_id: uuid.UUID) -> Location:
    """Primary location with unlabelled all-day hours — demonstrates the
    day-collapse summary (Mon–Sat 9–5, Sun 9–12)."""
    def _h(day: int, open_hm: tuple[int, int], close_hm: tuple[int, int]) -> RegularHours:
        return RegularHours(
            site_id=site_id, day_of_week=day,
            open_time=time(*open_hm), close_time=time(*close_hm),
        )

    return Location(
        site_id=site_id,
        address_street="14A Stockton Street",
        address_suburb="Anna Bay",
        address_state="NSW",
        address_postcode="2316",
        latitude=Decimal("-32.780000"),
        longitude=Decimal("152.090000"),
        phone="0412 455 686",
        email="hello@kincafe.com",
        hours_display_mode="summary",
        regular_hours=[
            *[_h(d, (9, 0), (17, 0)) for d in range(6)],  # Mon–Sat 9–5
            _h(6, (9, 0), (12, 0)),                        # Sun 9–12
        ],
    )


def build_all_day_menu() -> Menu:
    return Menu(
        name="All Day",
        description="Brunch, from open till close.",
        availability_note="Served all day",
        position=10,
        sections=[
            Section(
                name="Brunch",
                position=10,
                subsections=[Subsection(name=None, position=10, items=[
                    _item("Smashed Avocado", 10,
                          description="Sourdough, whipped feta, chilli, lemon",
                          dietary_tags=["vegetarian"], variants=[_v("18.00")]),
                    _item("House Granola", 20,
                          description="Toasted oats, yoghurt, poached rhubarb",
                          dietary_tags=["vegetarian"], variants=[_v("14.00")]),
                    _item("The Big Kin", 30,
                          description="Eggs, bacon, chorizo, roast tomato, greens, toast",
                          featured=True, variants=[_v("24.00")]),
                    _item("Bacon & Egg Roll", 40,
                          description="Milk bun, fried egg, bacon, smoky relish",
                          variants=[_v("12.00")]),
                ])],
            ),
            Section(
                name="Toasties",
                position=20,
                subsections=[Subsection(name=None, position=10, items=[
                    _item("Ham & Cheese", 10, description="Leg ham, gruyère, dijon",
                          variants=[_v("12.00")]),
                    _item("Three Cheese", 20, description="Cheddar, gruyère, mozzarella",
                          dietary_tags=["vegetarian"], variants=[_v("13.00")]),
                ])],
            ),
        ],
    )


def build_coffee_menu() -> Menu:
    return Menu(
        name="Coffee & Drinks",
        availability_note="Available all day",
        position=20,
        sections=[
            Section(
                name="Coffee",
                position=10,
                subsections=[Subsection(name=None, position=10, items=[
                    _item("Espresso", 10, variants=[_v("4.00")]),
                    _item("Flat White", 20, variants=[_v("4.50")]),
                    _item("Latte", 30, variants=[_v("4.50")]),
                    _item("Chai Latte", 40, variants=[_v("5.00")]),
                ])],
            ),
            Section(
                name="Cold",
                position=20,
                subsections=[Subsection(name=None, position=10, items=[
                    _item("Iced Latte", 10, variants=[_v("6.00")]),
                    _item("Fresh Orange Juice", 20, variants=[_v("7.00")]),
                ])],
            ),
        ],
    )


async def main() -> None:
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(Site).where(Site.slug == "kin"))).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.flush()
            print("Deleted existing kin site.")

        site = build_site()
        session.add(site)
        await session.flush()  # assigns site.site_id

        location = build_location(site.site_id)
        session.add(location)
        await session.commit()

        print(f"Site: {site.restaurant_name} (id={site.site_id}, template={site.template})")
        print(f"  location: {location.address_suburb} · {len(location.regular_hours)} hours rows "
              f"(display={location.hours_display_mode})")
        print(f"  menus: {len(site.menus)}")


if __name__ == "__main__":
    asyncio.run(main())
