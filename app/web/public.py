"""Public site routes — rendered via Host-header tenant resolution."""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

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
    return templates.TemplateResponse(
        page_path(template, "home"),
        {
            "request": request,
            "site": site,
            "role_images": role_images,
            "storage_url": storage_public_url,
        },
    )


@router.get("/menu", response_class=HTMLResponse)
async def menu(request: Request, site: Site = Depends(resolve_tenant)):
    template = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path(template, "menu"),
        {"request": request, "site": site},
    )


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.get("/visit", response_class=HTMLResponse)
async def visit(request: Request, site: Site = Depends(resolve_tenant)):
    template = resolve_template(site.template)
    # Group eager-loaded regular_hours by day
    hours_by_day: dict[int, list] = {}
    for h in site.regular_hours:
        hours_by_day.setdefault(h.day_of_week, []).append(h)
    # Filter exceptions: active + upcoming only (end_date >= today)
    today = date.today()
    active_exceptions = [
        exc for exc in site.hours_exceptions
        if exc.end_date >= today
    ]
    return templates.TemplateResponse(
        page_path(template, "visit"),
        {
            "request": request,
            "site": site,
            "hours_by_day": hours_by_day,
            "day_names": _DAY_NAMES,
            "hours_exceptions": active_exceptions,
        },
    )
