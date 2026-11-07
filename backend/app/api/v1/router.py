from fastapi import APIRouter

router = APIRouter()


@router.get("/status", tags=["system"])
def status() -> dict[str, str]:
    return {"status": "ok", "phase": "foundation"}

from app.api.v1.papers import router as papers_router
router.include_router(papers_router)

from app.api.v1.graph import router as graph_router
router.include_router(graph_router)

from app.api.v1.embeddings import router as embeddings_router
router.include_router(embeddings_router)

from app.api.v1.collections import router as collections_router
router.include_router(collections_router)

from app.api.v1.experiments import router as experiments_router
router.include_router(experiments_router)

from app.api.v1.analyses import router as analyses_router
router.include_router(analyses_router)
