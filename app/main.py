import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from app.routes.convert import router
from app.services.cleanup import start_cleanup_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_cleanup_task()
    logging.info("Cleanup task started (auto-delete files > 12h)")
    yield
    # Shutdown


app = FastAPI(
    title="Audio Converter API",
    description="API pour convertir des fichiers audio",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/convert", tags=["Convert"])


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """Block search engines from crawling this API."""
    return PlainTextResponse(
        "User-agent: *\nDisallow: /",
        media_type="text/plain"
    )


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """Block search engines from crawling this API."""
    return PlainTextResponse(
        "User-agent: *\nDisallow: /",
        media_type="text/plain"
    )