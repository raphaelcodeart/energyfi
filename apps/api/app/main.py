"""FastAPI application entry point.

Modules, their models and their routers come from `app/modules/registry.py`.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.foundation.config import get_settings
from app.modules.registry import load_model_metadata, mount_routers

logger = logging.getLogger(__name__)

settings = get_settings()

# Must run before building the app: SQLAlchemy relationships need every
# module's tables registered on `Base.metadata`.
load_model_metadata()

app = FastAPI(
    title="SOSNET Platform API",
    version="0.1.0",
    description="Vedi /opt/sosnet/docs per architettura e regole di business.",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mount_routers(app)


@app.on_event("startup")
async def _ensure_storage_buckets() -> None:
    from app.foundation.storage import ensure_documents_bucket, ensure_media_bucket

    try:
        ensure_media_bucket()
        ensure_documents_bucket()
    except Exception:
        # Uploads are not core functionality: a MinIO hiccup at startup must
        # not take the whole API down.
        logger.exception(
            "Bucket media/documenti non verificati -- il caricamento di foto e documenti "
            "fallira' finche' non viene risolto"
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
async def readiness() -> dict[str, str]:
    from sqlalchemy import text

    from app.foundation.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
