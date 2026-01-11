"""
Research Module - Web Search & Data Collection Services

This module provides a unified interface for:
1. LinkedIn research (via Bright Data)
2. Web search (via SERP API, Tavily, etc.)
3. Content scraping (via Bright Data, Firecrawl)

Architecture:
- BaseProvider: Abstract base class for all providers
- LinkedInProvider: LinkedIn-specific research (profiles, companies, jobs)
- WebSearchProvider: General web search (SERP, Tavily)
- ScraperProvider: Web content scraping

All providers are designed to be:
- Async-first for performance
- Cacheable to reduce API costs
- Tool-compatible for use in chat/agents
- LibreChat compatible for web UI

Usage:
    # Get service singleton
    from app.features.research import get_research_service
    service = get_research_service()
    
    # LinkedIn lookup
    result = await service.linkedin.execute("get_profile", {"url": "..."})
    
    # Web search
    result = await service.web_search.execute("search", {"query": "..."})
    
    # For chat tools integration
    from app.features.research import RESEARCH_TOOLS, handle_research_tool
"""

from .service import ResearchService, get_research_service
from .providers.base import BaseProvider, ProviderResult
from .providers.linkedin import LinkedInProvider
from .providers.web_search import WebSearchProvider
from .tools import RESEARCH_TOOLS, handle_research_tool, get_research_tool_names

__all__ = [
    "ResearchService",
    "get_research_service",
    "BaseProvider",
    "ProviderResult",
    "LinkedInProvider",
    "WebSearchProvider",
    "RESEARCH_TOOLS",
    "handle_research_tool",
    "get_research_tool_names",
]
