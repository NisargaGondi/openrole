"""OpenRole FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openrole.api.routes import activity, contacts, dashboard, integrations, jobs, network, pipeline, scout, settings
from openrole.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenRole API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(network.router, prefix="/api")
app.include_router(scout.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(activity.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "openrole-api"}
