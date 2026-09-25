"""FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from legacydoc_core.db import dispose_engine, init_engine
from legacydoc_core.errors import LegacyDocError, ValidationError
from legacydoc_core.settings import Settings, get_settings

from legacydoc_api.ratelimit import RateLimitMiddleware
from legacydoc_api.routers import admin, auth, documents, jobs, meta, projects

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_engine(resolved)
        logger.info("API iniciada no ambiente %s.", resolved.environment)
        try:
            yield
        finally:
            await dispose_engine()

    app = FastAPI(
        title="Legacy Doc API",
        version="2.0.0",
        description=(
            "Documentacao automatica multi-linguagem com orquestracao "
            "multi-agente e multi-provedor."
        ),
        lifespan=lifespan,
        root_path=resolved.api_root_path,
    )
    app.state.settings = resolved

    if resolved.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware, settings=resolved)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    _register_exception_handlers(app, resolved)

    for module in (auth, projects, jobs, documents, meta, admin):
        app.include_router(module.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "2.0.0"}

    return app


def _register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    """Map domain errors to HTTP in one consistent shape."""

    @app.exception_handler(LegacyDocError)
    async def handle_domain_error(_: Request, exc: LegacyDocError) -> JSONResponse:
        if exc.http_status >= 500:
            logger.exception("Erro de dominio: %s", exc.message)

        headers = {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None

        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.code, "message": exc.message, "details": exc.details},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=ValidationError.http_status,
            content={
                "error": "validation_error",
                "message": "Corpo da requisicao invalido.",
                "details": {"errors": exc.errors()[:10]},
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erro nao tratado.")

        message = (
            "Erro interno. Tente novamente."
            if settings.is_production
            else f"{type(exc).__name__}: {exc}"
        )

        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": message, "details": {}},
        )


app = None


def get_app() -> FastAPI:
    """Factory for `uvicorn legacydoc_api.main:get_app --factory`."""
    return create_app()
