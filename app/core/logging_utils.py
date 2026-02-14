"""
Logging utilities for safe logging of user data and sensitive information.

Includes:
- PII/secret redaction for safe logging
- Structured cost logging for AI API calls
"""
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional


# Sensitive keys that should be redacted in logs
SENSITIVE_KEYS = [
    "api_key", "token", "password", "secret", "auth",
    "email", "phone", "ssn", "credit_card",
    "linkedin_url", "access_token", "refresh_token",
    "bearer", "authorization"
]


def sanitize_for_logging(data: Any, max_len: int = 100) -> Any:
    """
    Sanitize data for safe logging - redacts PII and secrets.

    Args:
        data: The data to sanitize (can be dict, list, str, or other types)
        max_len: Maximum length for string values before truncation

    Returns:
        Sanitized version of the data safe for logging
    """
    if data is None:
        return "None"

    # Handle dictionaries - recursively sanitize values
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            # Check if key is sensitive
            if any(sensitive in k.lower() for sensitive in SENSITIVE_KEYS):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = sanitize_for_logging(v, max_len)
        return sanitized

    # Handle lists - recursively sanitize elements
    if isinstance(data, list):
        return [sanitize_for_logging(item, max_len) for item in data]

    # Handle strings - remove control characters and truncate
    if isinstance(data, str):
        # Remove control characters and newlines for single-line logging
        cleaned = re.sub(r'[\x00-\x1F\x7F]', '', data)
        # Truncate if too long
        if len(cleaned) > max_len:
            return cleaned[:max_len] + "..."
        return cleaned

    # For other types (int, float, bool, etc.), convert to string and sanitize
    return sanitize_for_logging(str(data), max_len)


def redact_emails(text: str) -> str:
    """
    Redact email addresses from text.

    Args:
        text: The text to redact emails from

    Returns:
        Text with emails replaced with [EMAIL_REDACTED]
    """
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.sub(email_pattern, '[EMAIL_REDACTED]', text)


def redact_phone_numbers(text: str) -> str:
    """
    Redact phone numbers from text.

    Args:
        text: The text to redact phone numbers from

    Returns:
        Text with phone numbers replaced with [PHONE_REDACTED]
    """
    # Match common phone number patterns (US and international)
    phone_patterns = [
        r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',  # International
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
    ]

    result = text
    for pattern in phone_patterns:
        result = re.sub(pattern, '[PHONE_REDACTED]', result)

    return result


def sanitize_log_message(message: str) -> str:
    """
    Sanitize a log message by redacting PII.

    Args:
        message: The log message to sanitize

    Returns:
        Sanitized message safe for logging
    """
    message = redact_emails(message)
    message = redact_phone_numbers(message)
    # Remove control characters
    message = re.sub(r'[\x00-\x1F\x7F]', '', message)
    return message


# =============================================================================
# STRUCTURED COST LOGGING
# =============================================================================

_cost_logger = logging.getLogger("Jarvis.Cost")


def log_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: Optional[int] = None,
    tool_calls: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    savings_usd: float = 0.0,
    endpoint: str = "unknown",
    client_type: str = "unknown",
    conversation_id: Optional[str] = None,
) -> None:
    """
    Log a structured cost event for an LLM API call.

    This produces a single JSON log line that can be parsed by
    log aggregation systems for cost tracking dashboards.

    Args:
        model: Model identifier (e.g., 'claude-haiku-4-5-20251001')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_usd: Total cost in USD
        duration_ms: Request duration in milliseconds
        tool_calls: Number of tool calls made
        cache_creation_tokens: Prompt caching write tokens
        cache_read_tokens: Prompt caching read tokens
        savings_usd: Cost saved via prompt caching
        endpoint: API endpoint that triggered this call
        client_type: Client type ('telegram', 'web', 'internal')
        conversation_id: Optional conversation identifier
    """
    event = {
        "event": "llm_cost",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": round(cost_usd, 6),
        "tool_calls": tool_calls,
        "endpoint": endpoint,
        "client_type": client_type,
    }

    if duration_ms is not None:
        event["duration_ms"] = duration_ms

    if cache_creation_tokens > 0:
        event["cache_creation_tokens"] = cache_creation_tokens

    if cache_read_tokens > 0:
        event["cache_read_tokens"] = cache_read_tokens

    if savings_usd > 0:
        event["savings_usd"] = round(savings_usd, 6)

    if conversation_id:
        event["conversation_id"] = conversation_id

    _cost_logger.info("LLM_COST %s", json.dumps(event))
