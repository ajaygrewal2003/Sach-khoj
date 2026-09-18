from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.routers import cases, review, submit
from app.schemas import HealthOut
from app.services.knowledge_base import get_knowledge_base
from app.services.seed import seed_known_false_claims


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    await init_db()
    get_knowledge_base().load()
    async with SessionLocal() as session:
        await seed_known_false_claims(session)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, description=settings.app_description, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(submit.router)
    app.include_router(cases.router)
    app.include_router(review.router)

    @app.get("/api/health", response_model=HealthOut)
    async def health() -> HealthOut:
        live = get_settings()
        return HealthOut(status="ok", llm_enabled=live.llm_enabled, app=live.app_name)

    return app


app = create_app()
