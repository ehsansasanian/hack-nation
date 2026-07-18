"""FastAPI application entry point.

Run with: ``uv run uvicorn app.main:app --reload``
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications, founders, pipeline, query, sourcing, thesis
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="The VC Brain", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(pipeline.router)
app.include_router(query.router)
app.include_router(thesis.router)
app.include_router(sourcing.router)
app.include_router(founders.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
