from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Process liveness only; this endpoint does not test database connectivity."""
    return {"status": "ok"}


@app.on_event("startup")
def recover_interrupted_ingestions():
    # A single request can perform at most ten 15-second lookups with bounded retries.
    # Only expire runs older than an hour, leaving recent requests owned by other processes alone.
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from app.db.session import SessionLocal
    from app.models.paper import IngestionRun, CollectionJob
    try:
        with SessionLocal() as db:
            db.execute(update(IngestionRun).where(IngestionRun.status=='running',IngestionRun.created_at < datetime.now(timezone.utc)-timedelta(hours=1)).values(status='interrupted',error='The ingestion process was interrupted; retry the selected papers.'))
            db.execute(update(CollectionJob).where(CollectionJob.status=='running',CollectionJob.updated_at < datetime.now(timezone.utc)-timedelta(minutes=10)).values(status='interrupted',error='Interrupted collection; resume from the last checkpoint.'))
            db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Could not recover interrupted ingestion runs')
