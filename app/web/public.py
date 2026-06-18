"""Public site routes — rendered via Host-header tenant resolution."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.models.site import Site
from app.web.tenancy import resolve_tenant

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, site: Site = Depends(resolve_tenant)):
    return templates.TemplateResponse(
        "public/site.html",
        {"request": request, "site": site},
    )
