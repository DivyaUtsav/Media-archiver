from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import Base, engine
from app.routers import artworks, knowledge_graph, queue
from app.services.enrichment_providers import provider_health_snapshot

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    if settings.provider_startup_checks:
        app.state.provider_health = provider_health_snapshot()
    else:
        app.state.provider_health = {
            "ready": True,
            "checks": {},
            "detail": "provider startup checks disabled",
        }
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/providers")
def health_providers() -> dict:
    cached = getattr(app.state, "provider_health", None)
    if cached:
        return cached
    return provider_health_snapshot()


app.include_router(artworks.router)
app.include_router(queue.router)
app.include_router(knowledge_graph.router)
