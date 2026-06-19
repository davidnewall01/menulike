"""Public site routes — rendered via Host-header tenant resolution."""

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
    return templates.TemplateResponse(
        "public/site.html",
        {"request": request, "site": site},
    )
