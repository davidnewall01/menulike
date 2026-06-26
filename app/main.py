"""FastAPI application entrypoint."""

from dotenv import load_dotenv

# Load .env before any app imports read settings.
load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from app.services.exceptions import OwnerNeedsSetup  # noqa: E402
from app.web.tenancy import SiteNotPublished  # noqa: E402
from app.web.admin import router as admin_router  # noqa: E402
from app.web.auth import router as auth_router  # noqa: E402
from app.web.public import router as public_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup hooks go here in later phases.
    yield
    # Shutdown hooks go here in later phases.


app = FastAPI(title="menulike", lifespan=lifespan)


@app.exception_handler(OwnerNeedsSetup)
async def owner_needs_setup_handler(request: Request, exc: OwnerNeedsSetup):
    """Redirect owners without a site to the restaurant-naming step.

    Uses a real RedirectResponse — NOT HTTPException(303) which FastAPI
    renders as JSON and the browser doesn't follow.
    """
    return RedirectResponse(url="/setup/restaurant", status_code=303)


_coming_soon_templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)


@app.exception_handler(SiteNotPublished)
async def site_not_published_handler(request: Request, exc: SiteNotPublished):
    """Render a tasteful coming-soon page for unpublished sites.

    Returns 200 — the site exists, it's just not ready yet. A 404 would
    confuse owners sharing the link early and tell crawlers it doesn't exist.
    """
    return _coming_soon_templates.TemplateResponse(
        "public/linen/coming_soon.html",
        {"request": request, "restaurant_name": exc.restaurant_name},
        status_code=200,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "018"}


app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(public_router)
