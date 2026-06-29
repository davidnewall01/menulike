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

from app.services.exceptions import NoSiteInScope, OwnerNeedsSetup  # noqa: E402
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


@app.exception_handler(NoSiteInScope)
async def no_site_in_scope_handler(request: Request, exc: NoSiteInScope):
    """Redirect to admin dashboard when the act-as cookie is stale/missing.

    Happens when an internal_admin's session outlives the act-as cookie
    (e.g. server restart). Re-entering via the dashboard re-sets the cookie.
    """
    return RedirectResponse(url="/admin/", status_code=303)


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
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Public render error boundary — defence-in-depth.
#
# Catches unhandled exceptions on PUBLIC site routes so visitors see a clean
# error page instead of a raw 500 / stack trace. Logs the real exception
# server-side. Does NOT wrap admin/auth routes (those should surface errors
# to the developer during dev).
# ---------------------------------------------------------------------------

import logging

_public_error_logger = logging.getLogger("menulike.public_render")
_error_templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)


@app.middleware("http")
async def public_render_error_boundary(request: Request, call_next):
    """Catch template render errors on public routes only."""
    response = None
    try:
        response = await call_next(request)
    except Exception:
        # Only catch for public routes (not /admin, /setup, /health, /static)
        path = request.url.path
        if path.startswith(("/admin", "/setup", "/health", "/static")):
            raise  # Re-raise for admin/dev — don't blind debugging
        _public_error_logger.exception(
            "Public render error: %s %s", request.method, request.url
        )
        return HTMLResponse(
            content=(
                '<!DOCTYPE html><html><head><meta charset="utf-8">'
                "<title>Something went wrong</title>"
                '<style>body{font-family:system-ui;display:flex;align-items:center;'
                "justify-content:center;min-height:100vh;margin:0;background:#f5f0e8;"
                "color:#3e3528}div{text-align:center;max-width:400px;padding:40px}"
                "h1{font-size:24px;margin:0 0 12px}p{color:#6e665b;font-size:14px}</style>"
                "</head><body><div>"
                "<h1>Something went wrong</h1>"
                "<p>We're sorry — this page isn't loading right now. "
                "Please try again in a moment.</p>"
                "</div></body></html>"
            ),
            status_code=500,
        )
    return response


app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(public_router)
