"""
Shared OpenAI client for Intelligence Service.

Centralizes OpenAI API access for embeddings, TTS, and future features.
"""

import os
import logging
from functools import lru_cache

from openai import AsyncOpenAI

logger = logging.getLogger("Jarvis.Intelligence.OpenAI")


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """
    Get the singleton OpenAI async client.

    Uses lru_cache to ensure only one client instance exists.

    Returns:
        AsyncOpenAI client instance

    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = AsyncOpenAI(api_key=api_key)
    logger.info("OpenAI client initialized")
    return client


async def get_client() -> AsyncOpenAI:
    """
    Async-friendly wrapper to get the OpenAI client.

    Returns:
        AsyncOpenAI client instance
    """
    return get_openai_client()
