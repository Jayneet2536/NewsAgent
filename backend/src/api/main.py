"""FastAPI application factory for the NewsAgent REST API.

Launch with:
    uvicorn src.api.main:app --reload
or via the project root run.py:
    python run.py
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import settings
from .router import router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS origins
# ---------------------------------------------------------------------------

_frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
if _frontend_origin:
    _allow_origins = [_frontend_origin]
else:
    # DEV-ONLY FALLBACK — lock this down with FRONTEND_ORIGIN in production.
    logger.warning(
        "FRONTEND_ORIGIN env var is not set — CORS is open to all origins (*). "
        "Set FRONTEND_ORIGIN=https://your-frontend.example.com in production."
    )
    _allow_origins = ["*"]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "REST API wrapper around the NewsAgent LangGraph pipeline "
        "(planner → researcher → writer → verifier)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
