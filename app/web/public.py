"""Public site routes — rendered via Host-header tenant resolution."""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.content.resolver import resolve_site_view
from app.db.session import get_db
from app.models.site import Site
from app.services import image_role_service
from app.services.storage import public_url as storage_public_url
from app.web.template_resolver import page_path, resolve_template
from app.web.tenancy import resolve_tenant

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    site: Site = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
):
    template = resolve_template(site.template)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="public",
        storage_url=storage_public_url,
    )
    return templates.TemplateResponse(
        page_path(template, "home"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            "render_mode": "public",
        },
    )


@router.get("/menu", response_class=HTMLResponse)
async def menu(request: Request, site: Site = Depends(resolve_tenant), db: AsyncSession = Depends(get_db)):
    template = resolve_template(site.template)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="public",
        storage_url=storage_public_url,
    )
    return templates.TemplateResponse(
        page_path(template, "menu"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            "render_mode": "public",
        },
    )


@router.get("/gallery", response_class=HTMLResponse)
async def gallery(
    request: Request,
    site: Site = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
):
    template = resolve_template(site.template)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="public",
        storage_url=storage_public_url,
    )
    # No gallery photos → redirect home (gallery reappears when photos are added)
    if view.gallery.fields["photos"].source != "real":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        page_path(template, "gallery"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            "render_mode": "public",
        },
    )


@router.get("/our-story", response_class=HTMLResponse)
async def our_story(request: Request, site: Site = Depends(resolve_tenant), db: AsyncSession = Depends(get_db)):
    template = resolve_template(site.template)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="public",
        storage_url=storage_public_url,
    )
    return templates.TemplateResponse(
        page_path(template, "our_story"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            "render_mode": "public",
        },
    )


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.get("/visit", response_class=HTMLResponse)
async def visit(request: Request, site: Site = Depends(resolve_tenant), db: AsyncSession = Depends(get_db)):
    template = resolve_template(site.template)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="public",
        storage_url=storage_public_url,
    )
    # Group hours from the default (first) location
    location = site.locations[0] if site.locations else None
    hours_by_day: dict[int, list] = {}
    if location:
        for h in location.regular_hours:
            hours_by_day.setdefault(h.day_of_week, []).append(h)
    # Filter exceptions: active + upcoming only (end_date >= today)
    today = date.today()
    active_exceptions = [
        exc for exc in (location.hours_exceptions if location else [])
        if exc.end_date >= today
    ]
    return templates.TemplateResponse(
        page_path(template, "visit"),
        {
            "request": request,
            "site": site,
            "view": view,
            "hours_by_day": hours_by_day,
            "day_names": _DAY_NAMES,
            "hours_exceptions": active_exceptions,
            "storage_url": storage_public_url,
            "render_mode": "public",
        },
    )
