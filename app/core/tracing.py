"""
OpenTelemetry Distributed Tracing Configuration.

This module provides centralized tracing configuration for the Intelligence Service.
It sets up OpenTelemetry with:
- TracerProvider with the service name
- BatchSpanProcessor for efficient span export
- Console exporter for development (easily switchable to OTLP for production)
- Environment variable control (OTEL_ENABLED=true/false)

Usage:
    from app.core.tracing import setup_tracing, get_tracer, instrument_app

    # In main.py lifespan or startup
    setup_tracing()

    # Instrument FastAPI app
    instrument_app(app)

    # Get a tracer for custom spans
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")
        # ... do work

Environment Variables:
    OTEL_ENABLED: Set to "true" to enable tracing (default: false)
    OTEL_SERVICE_NAME: Override service name (default: jarvis-intelligence-service)
    OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint for production (optional)
"""

import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.trace import Tracer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logger = logging.getLogger("Jarvis.Tracing")

# Default service name
DEFAULT_SERVICE_NAME = "jarvis-intelligence-service"

# Global state
_tracer_provider: Optional[TracerProvider] = None
_is_initialized = False


def is_tracing_enabled() -> bool:
    """
    Check if OpenTelemetry tracing is enabled via environment variable.

    Returns:
        True if OTEL_ENABLED is set to "true" (case-insensitive), False otherwise.
    """
    return os.getenv("OTEL_ENABLED", "false").lower() == "true"


def setup_tracing(service_name: Optional[str] = None) -> Optional[TracerProvider]:
    """
    Initialize OpenTelemetry tracing with TracerProvider and span processor.

    This function sets up:
    - A TracerProvider with the service name as a resource attribute
    - A BatchSpanProcessor for efficient span batching
    - ConsoleSpanExporter for development visibility (can switch to OTLP later)

    If OTEL_ENABLED is not "true", this function returns None and does nothing.

    Args:
        service_name: Optional override for the service name.
                     Defaults to OTEL_SERVICE_NAME env var or DEFAULT_SERVICE_NAME.

    Returns:
        The configured TracerProvider, or None if tracing is disabled.
    """
    global _tracer_provider, _is_initialized

    if _is_initialized:
        logger.debug("Tracing already initialized, skipping")
        return _tracer_provider

    if not is_tracing_enabled():
        logger.info("OpenTelemetry tracing is disabled (set OTEL_ENABLED=true to enable)")
        _is_initialized = True
        return None

    # Determine service name
    effective_service_name = (
        service_name
        or os.getenv("OTEL_SERVICE_NAME")
        or DEFAULT_SERVICE_NAME
    )

    # Create resource with service name
    resource = Resource.create({
        SERVICE_NAME: effective_service_name
    })

    # Create TracerProvider
    _tracer_provider = TracerProvider(resource=resource)

    # Add BatchSpanProcessor with ConsoleSpanExporter for development
    # In production, replace ConsoleSpanExporter with OTLPSpanExporter:
    # from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    # exporter = OTLPSpanExporter(endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            logger.info(f"Using OTLP exporter with endpoint: {otlp_endpoint}")
        except ImportError:
            logger.warning("OTLP exporter requested but grpc dependencies not installed, falling back to console")
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()
        logger.info("Using Console exporter for trace output")

    span_processor = BatchSpanProcessor(exporter)
    _tracer_provider.add_span_processor(span_processor)

    # Set as global TracerProvider
    trace.set_tracer_provider(_tracer_provider)

    _is_initialized = True
    logger.info(f"OpenTelemetry tracing initialized for service: {effective_service_name}")

    return _tracer_provider


def get_tracer(name: str) -> Tracer:
    """
    Get a tracer instance for creating custom spans.

    Args:
        name: The name for the tracer, typically __name__ of the module.

    Returns:
        A Tracer instance. If tracing is disabled, returns a no-op tracer.

    Example:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("process_transcript") as span:
            span.set_attribute("transcript_id", transcript_id)
            # ... processing logic
    """
    return trace.get_tracer(name)


def instrument_app(app) -> None:
    """
    Instrument a FastAPI application with OpenTelemetry.

    This adds automatic tracing for all incoming HTTP requests,
    capturing method, path, status code, and timing.

    Args:
        app: The FastAPI application instance to instrument.
    """
    if not is_tracing_enabled():
        logger.debug("Tracing disabled, skipping FastAPI instrumentation")
        return

    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumentation enabled")


def instrument_httpx() -> None:
    """
    Instrument httpx client for outbound HTTP request tracing.

    This automatically adds trace context propagation to outbound
    requests, enabling distributed tracing across services.
    """
    if not is_tracing_enabled():
        logger.debug("Tracing disabled, skipping httpx instrumentation")
        return

    HTTPXClientInstrumentor().instrument()
    logger.info("httpx instrumentation enabled")


def shutdown_tracing() -> None:
    """
    Shutdown the tracing provider and flush any remaining spans.

    Should be called during application shutdown to ensure
    all spans are properly exported.
    """
    global _tracer_provider, _is_initialized

    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        logger.info("OpenTelemetry tracing shut down")

    _tracer_provider = None
    _is_initialized = False


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID if available.

    Useful for correlating logs with traces or including
    trace ID in error responses.

    Returns:
        The current trace ID as a hex string, or None if no active span.
    """
    span = trace.get_current_span()
    if span is None:
        return None

    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None

    return format(span_context.trace_id, "032x")


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID if available.

    Returns:
        The current span ID as a hex string, or None if no active span.
    """
    span = trace.get_current_span()
    if span is None:
        return None

    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None

    return format(span_context.span_id, "016x")
