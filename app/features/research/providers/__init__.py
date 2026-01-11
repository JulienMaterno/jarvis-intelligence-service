"""
Research Providers Package

Available providers:
- LinkedInProvider: LinkedIn profile/company research via Bright Data
- WebSearchProvider: Multi-backend web search (Tavily, SERP, Brave, Bing)
"""

from .base import BaseProvider, ProviderResult, ProviderStatus
from .linkedin import LinkedInProvider
from .web_search import WebSearchProvider, SearchBackend

__all__ = [
    "BaseProvider",
    "ProviderResult",
    "ProviderStatus",
    "LinkedInProvider",
    "WebSearchProvider",
    "SearchBackend",
]
