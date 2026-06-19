"""FastAPI application entrypoint."""

from dotenv import load_dotenv

# Load .env before any app imports read settings.
load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.web.admin import router as admin_router  # noqa: E402
from app.web.public import router as public_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup hooks go here in later phases.
    yield
    # Shutdown hooks go here in later phases.


app = FastAPI(title="menulike", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
app.include_router(admin_router)
app.include_router(public_router)
