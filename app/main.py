"""FastAPI application entrypoint."""

from dotenv import load_dotenv

# Load .env before any app imports read settings.
load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.services.exceptions import OwnerNeedsSetup  # noqa: E402
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(public_router)
