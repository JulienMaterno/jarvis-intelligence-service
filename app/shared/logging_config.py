"""
Structured JSON logging configuration for Jarvis services.

Provides consistent JSON-formatted logging across all services with
correlation ID tracking for distributed request tracing.

Usage:
    from app.shared.logging_config import setup_logging, get_logger

    # At application startup (main.py):
    setup_logging(service_name="jarvis-intelligence-service")

    # In modules:
    logger = get_logger(__name__)
    logger.info("Processing request", extra={"user_id": "123", "action": "chat"})

Output format (JSON, one line per log):
    {
        "timestamp": "2026-01-28T10:30:00.123456Z",
        "level": "INFO",
        "logger": "jarvis.chat",
        "message": "Processing request",
        "service": "jarvis-intelligence-service",
        "correlation_id": "abc123",
        "user_id": "123",
        "action": "chat"
    }
"""

import logging
import sys
import os
from datetime import datetime, timezone
from typing import Optional
import json


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that injects correlation_id into log records.

    The correlation_id is retrieved from a context variable that should be
    set by the correlation middleware at the start of each request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to record if not present."""
        if not hasattr(record, "correlation_id"):
            # Try to get from context (set by middleware)
            from app.shared.correlation import get_correlation_id
            record.correlation_id = get_correlation_id() or "-"
        return True


class JSONFormatter(logging.Formatter):
    """
    Formats log records as JSON for structured logging.

    Includes standard fields (timestamp, level, message) plus any
    extra fields passed to the logger.
    """

    def __init__(self, service_name: str = "jarvis"):
        """
        Initialize the JSON formatter.

        Args:
            service_name: Name of the service for log identification
        """
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as a JSON string.

        Args:
            record: The log record to format

        Returns:
            JSON-formatted log string
        """
        # Build base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        # Add correlation ID
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id and correlation_id != "-":
            log_entry["correlation_id"] = correlation_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding standard logging attributes)
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "correlation_id", "message", "taskName",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                try:
                    # Ensure value is JSON serializable
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        return json.dumps(log_entry)


class HumanReadableFormatter(logging.Formatter):
    """
    Human-readable formatter for local development.

    Includes correlation ID in log messages for easier debugging.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format record with correlation ID prefix."""
        correlation_id = getattr(record, "correlation_id", "-")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build prefix
        prefix = f"{timestamp} [{record.levelname}] [{correlation_id}]"

        # Format message
        message = record.getMessage()

        # Add extra fields inline
        extra_parts = []
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "correlation_id", "message", "taskName",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                extra_parts.append(f"{key}={value}")

        if extra_parts:
            extras = " | " + ", ".join(extra_parts)
        else:
            extras = ""

        formatted = f"{prefix} {record.name}: {message}{extras}"

        # Add exception if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging(
    service_name: str,
    level: Optional[str] = None,
    json_output: Optional[bool] = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        service_name: Name of the service (e.g., "jarvis-intelligence-service")
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO
               or value from LOG_LEVEL environment variable.
        json_output: If True, output JSON logs. If False, human-readable.
                     Defaults to True in production (ENVIRONMENT != "development")
    """
    # Determine log level
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    log_level = getattr(logging, level, logging.INFO)

    # Determine output format
    if json_output is None:
        environment = os.getenv("ENVIRONMENT", "production").lower()
        json_output = environment != "development"

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Set formatter
    if json_output:
        formatter = JSONFormatter(service_name=service_name)
    else:
        formatter = HumanReadableFormatter()

    handler.setFormatter(formatter)

    # Add correlation ID filter
    correlation_filter = CorrelationIdFilter()
    handler.addFilter(correlation_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "google.auth",
        "google.auth.transport",
        "googleapiclient.discovery",
        "googleapiclient.discovery_cache",
        "anthropic",
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Log startup message
    startup_logger = logging.getLogger(f"{service_name}.startup")
    startup_logger.info(
        f"Logging configured",
        extra={
            "log_level": level,
            "json_output": json_output,
            "environment": os.getenv("ENVIRONMENT", "production"),
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    This is a convenience wrapper around logging.getLogger that ensures
    the correlation ID filter is applied.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    correlation_id: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Log a message with additional context fields.

    Args:
        logger: Logger instance
        level: Log level (e.g., logging.INFO)
        message: Log message
        correlation_id: Optional correlation ID override
        **kwargs: Additional fields to include in log
    """
    extra = dict(kwargs)
    if correlation_id:
        extra["correlation_id"] = correlation_id

    logger.log(level, message, extra=extra)
