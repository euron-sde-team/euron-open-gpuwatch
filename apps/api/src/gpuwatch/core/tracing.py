"""OpenTelemetry tracing. Spans are created through the OTel API everywhere; they cost
nothing until OTEL_ENABLED=true installs an SDK provider with an OTLP exporter, configured
by the standard OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_SERVICE_NAME variables."""

from __future__ import annotations

import logging

from opentelemetry import trace

from gpuwatch import __version__
from gpuwatch.core.config import Settings

tracer = trace.get_tracer("gpuwatch", __version__)
log = logging.getLogger("gpuwatch.tracing")
_configured = False


def configure_tracing(settings: Settings, service: str = "gpuwatch-api") -> None:
    global _configured
    if not settings.otel_enabled or _configured:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": service, "service.version": __version__})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True
    log.info("OpenTelemetry tracing enabled")
