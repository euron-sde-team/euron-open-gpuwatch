"""Application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from gpuwatch import __version__
from gpuwatch.alerts.router import router as alerts_router
from gpuwatch.audit.router import router as audit_router
from gpuwatch.auth.router import router as auth_router
from gpuwatch.core.config import Settings, get_settings
from gpuwatch.core.container import Container
from gpuwatch.core.db import import_all_models
from gpuwatch.core.errors import install_error_handlers
from gpuwatch.core.logs import configure_logging
from gpuwatch.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from gpuwatch.core.tracing import configure_tracing
from gpuwatch.costs.router import router as costs_router
from gpuwatch.fleet.router import router as fleet_router
from gpuwatch.inference.router import router as inference_router
from gpuwatch.ingest.router import router as ingest_router
from gpuwatch.insights.router import router as insights_router
from gpuwatch.keys.router import router as keys_router
from gpuwatch.overview.router import router as overview_router
from gpuwatch.system.router import router as system_router
from gpuwatch.telemetry.router import router as telemetry_router
from gpuwatch.users.router import router as users_router

DESCRIPTION = """
Self-hosted GPU monitoring and cost intelligence. Agents on your GPU machines send NVIDIA
metrics (NVML or an existing DCGM exporter), processes and inference server metrics; GPUWatch
keeps the history, attributes every GPU-hour to a workload or to idle, finds waste and
slowdowns, and alerts by email or webhook. It observes and recommends; it never starts or
stops anything on your machines.

* `/ingest/v1/*`: the agent contract (enrolment token, then a host token).
* `/api/v1/*`: the dashboard API. Authenticate with a session token
  (`POST /api/v1/auth/login`) or, for read-only automation, an API key
  (`Authorization: Bearer gwk_...`).
* `/metrics`: Prometheus metrics, including one gauge per GPU for the whole fleet.
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    import_all_models()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or Container.build(settings)
        try:
            yield
        finally:
            if container is None:
                await app.state.container.close()

    app = FastAPI(
        title="Euron Open GPUWatch",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        separate_input_output_schemas=False,
    )
    install_error_handlers(app)
    for router in (
        ingest_router,
        auth_router,
        users_router,
        keys_router,
        overview_router,
        fleet_router,
        telemetry_router,
        costs_router,
        insights_router,
        alerts_router,
        inference_router,
        audit_router,
        system_router,
    ):
        app.include_router(router)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-gpuwatch-csrf", "x-request-id"],
        expose_headers=["x-request-id", "retry-after", "content-disposition"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    return app
