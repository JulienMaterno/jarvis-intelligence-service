"""
Logging utilities for safe logging of user data and sensitive information.
"""
import re
from typing import Any, Dict, List


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
