"""
Web Search Provider - Multi-API Web Search

Supports multiple web search backends:
- Tavily (default) - AI-optimized search
- SERP API - Google search results
- Brave Search - Privacy-focused
- Bing Search - Microsoft API

Features:
- Unified interface across providers
- Automatic fallback between providers
- Result caching to reduce costs
- Content extraction from URLs
"""

import os
import logging
import httpx
from typing import Any, Dict, List, Optional
from enum import Enum

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger("Jarvis.Research.WebSearch")


class SearchBackend(Enum):
    """Available web search backends."""
    TAVILY = "tavily"
    SERP = "serp"
    BRAVE = "brave"
    BING = "bing"


# API configurations
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERP_API_KEY = os.getenv("SERP_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BING_API_KEY = os.getenv("BING_API_KEY", "")

# API endpoints
TAVILY_URL = "https://api.tavily.com/search"
SERP_URL = "https://serpapi.com/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
BING_URL = "https://api.bing.microsoft.com/v7.0/search"


class WebSearchProvider(BaseProvider):
    """
    Multi-backend web search provider.
    
    Provides unified interface to multiple search APIs with:
    - Automatic backend selection based on configured APIs
    - Fallback to alternative backends on failure
    - Result normalization across providers
    """
    
    def __init__(
        self,
        preferred_backend: Optional[SearchBackend] = None,
        tavily_key: Optional[str] = None,
        serp_key: Optional[str] = None,
        brave_key: Optional[str] = None,
        bing_key: Optional[str] = None
    ):
        self.tavily_key = tavily_key or TAVILY_API_KEY
        self.serp_key = serp_key or SERP_API_KEY
        self.brave_key = brave_key or BRAVE_API_KEY
        self.bing_key = bing_key or BING_API_KEY
        
        # Determine preferred backend
        if preferred_backend:
            self._preferred = preferred_backend
        elif self.tavily_key:
            self._preferred = SearchBackend.TAVILY
        elif self.serp_key:
            self._preferred = SearchBackend.SERP
        elif self.brave_key:
            self._preferred = SearchBackend.BRAVE
        elif self.bing_key:
            self._preferred = SearchBackend.BING
        else:
            self._preferred = None
        
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def is_configured(self) -> bool:
        """Check if any search API is configured."""
        return any([self.tavily_key, self.serp_key, self.brave_key, self.bing_key])
    
    @property
    def available_backends(self) -> List[SearchBackend]:
        """List of configured backends."""
        backends = []
        if self.tavily_key:
            backends.append(SearchBackend.TAVILY)
        if self.serp_key:
            backends.append(SearchBackend.SERP)
        if self.brave_key:
            backends.append(SearchBackend.BRAVE)
        if self.bing_key:
            backends.append(SearchBackend.BING)
        return backends
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _execute(self, operation: str, params: Dict[str, Any]) -> ProviderResult:
        """Execute web search operation."""
        
        if not self.is_configured:
            return ProviderResult.failure(
                "No web search API configured. Set TAVILY_API_KEY, SERP_API_KEY, BRAVE_API_KEY, or BING_API_KEY."
            )
        
        handlers = {
            "search": self._search,
            "search_news": self._search_news,
            "extract_content": self._extract_content,
        }
        
        handler = handlers.get(operation)
        if not handler:
            return ProviderResult.failure(f"Unknown operation: {operation}")
        
        return await handler(params)
    
    async def _search(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Execute web search query.
        
        Params:
            query: Search query string
            num_results: Number of results (default 10)
            include_domains: Only search these domains (optional)
            exclude_domains: Exclude these domains (optional)
            search_depth: 'basic' or 'advanced' (Tavily-specific)
        """
        query = params.get("query")
        if not query:
            return ProviderResult.failure("Missing required parameter: query")
        
        num_results = params.get("num_results", 10)
        
        # Try backends in order of preference
        backends_to_try = [self._preferred] if self._preferred else []
        backends_to_try.extend([b for b in self.available_backends if b != self._preferred])
        
        last_error = None
        for backend in backends_to_try:
            try:
                if backend == SearchBackend.TAVILY:
                    result = await self._search_tavily(query, num_results, params)
                elif backend == SearchBackend.SERP:
                    result = await self._search_serp(query, num_results, params)
                elif backend == SearchBackend.BRAVE:
                    result = await self._search_brave(query, num_results, params)
                elif backend == SearchBackend.BING:
                    result = await self._search_bing(query, num_results, params)
                else:
                    continue
                
                if result.is_success:
                    result.metadata["backend"] = backend.value
                    return result
                else:
                    last_error = result.error
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Search with {backend.value} failed: {e}")
                continue
        
        return ProviderResult.failure(f"All search backends failed. Last error: {last_error}")
    
    async def _search_tavily(
        self,
        query: str,
        num_results: int,
        params: Dict[str, Any]
    ) -> ProviderResult:
        """Search using Tavily API."""
        client = await self._get_client()
        
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "max_results": num_results,
            "search_depth": params.get("search_depth", "basic"),
            "include_answer": params.get("include_answer", True),
            "include_raw_content": params.get("include_raw_content", False),
        }
        
        if params.get("include_domains"):
            payload["include_domains"] = params["include_domains"]
        if params.get("exclude_domains"):
            payload["exclude_domains"] = params["exclude_domains"]
        
        response = await client.post(TAVILY_URL, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            # Normalize results
            results = self._normalize_tavily_results(data)
            return ProviderResult.success(results, raw_response=data)
        else:
            return ProviderResult.failure(f"Tavily error: {response.status_code}")
    
    async def _search_serp(
        self,
        query: str,
        num_results: int,
        params: Dict[str, Any]
    ) -> ProviderResult:
        """Search using SERP API (Google)."""
        client = await self._get_client()
        
        payload = {
            "api_key": self.serp_key,
            "q": query,
            "num": num_results,
            "engine": "google",
        }
        
        response = await client.get(SERP_URL, params=payload)
        
        if response.status_code == 200:
            data = response.json()
            results = self._normalize_serp_results(data)
            return ProviderResult.success(results, raw_response=data)
        else:
            return ProviderResult.failure(f"SERP error: {response.status_code}")
    
    async def _search_brave(
        self,
        query: str,
        num_results: int,
        params: Dict[str, Any]
    ) -> ProviderResult:
        """Search using Brave Search API."""
        client = await self._get_client()
        
        headers = {"X-Subscription-Token": self.brave_key}
        payload = {"q": query, "count": num_results}
        
        response = await client.get(BRAVE_URL, params=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            results = self._normalize_brave_results(data)
            return ProviderResult.success(results, raw_response=data)
        else:
            return ProviderResult.failure(f"Brave error: {response.status_code}")
    
    async def _search_bing(
        self,
        query: str,
        num_results: int,
        params: Dict[str, Any]
    ) -> ProviderResult:
        """Search using Bing Search API."""
        client = await self._get_client()
        
        headers = {"Ocp-Apim-Subscription-Key": self.bing_key}
        payload = {"q": query, "count": num_results}
        
        response = await client.get(BING_URL, params=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            results = self._normalize_bing_results(data)
            return ProviderResult.success(results, raw_response=data)
        else:
            return ProviderResult.failure(f"Bing error: {response.status_code}")
    
    # ==========================================================================
    # Result Normalization
    # ==========================================================================
    
    def _normalize_tavily_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize Tavily results to common format."""
        return {
            "answer": data.get("answer"),
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content"),
                    "score": r.get("score"),
                    "published_date": r.get("published_date"),
                }
                for r in data.get("results", [])
            ],
            "query": data.get("query"),
        }
    
    def _normalize_serp_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize SERP API results to common format."""
        organic = data.get("organic_results", [])
        return {
            "answer": None,  # SERP doesn't provide AI answer
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("link"),
                    "snippet": r.get("snippet"),
                    "score": r.get("position"),
                    "published_date": r.get("date"),
                }
                for r in organic
            ],
            "query": data.get("search_parameters", {}).get("q"),
        }
    
    def _normalize_brave_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize Brave Search results to common format."""
        web = data.get("web", {}).get("results", [])
        return {
            "answer": None,
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("description"),
                    "score": None,
                    "published_date": r.get("age"),
                }
                for r in web
            ],
            "query": data.get("query", {}).get("original"),
        }
    
    def _normalize_bing_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize Bing Search results to common format."""
        web = data.get("webPages", {}).get("value", [])
        return {
            "answer": None,
            "results": [
                {
                    "title": r.get("name"),
                    "url": r.get("url"),
                    "snippet": r.get("snippet"),
                    "score": None,
                    "published_date": r.get("dateLastCrawled"),
                }
                for r in web
            ],
            "query": data.get("queryContext", {}).get("originalQuery"),
        }
    
    async def _search_news(self, params: Dict[str, Any]) -> ProviderResult:
        """Search news articles."""
        # For now, use regular search with news-focused params
        params["search_depth"] = "advanced"
        return await self._search(params)
    
    async def _extract_content(self, params: Dict[str, Any]) -> ProviderResult:
        """Extract content from a URL."""
        url = params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: url")
        
        # TODO: Implement content extraction via Bright Data or other service
        return ProviderResult.failure("Content extraction not yet implemented")
    
    # ==========================================================================
    # Tool Definitions
    # ==========================================================================
    
    def get_operations(self) -> List[Dict[str, Any]]:
        """Return available web search operations."""
        return [
            {
                "name": "search",
                "description": "Search the web for information. Returns relevant web pages with snippets.",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default 10)",
                        "default": 10
                    },
                    "include_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only search these domains (optional)"
                    },
                    "exclude_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exclude these domains (optional)"
                    }
                },
                "required": ["query"]
            },
            {
                "name": "search_news",
                "description": "Search for news articles.",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "News search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            },
            {
                "name": "extract_content",
                "description": "Extract main content from a web page URL.",
                "parameters": {
                    "url": {
                        "type": "string",
                        "description": "URL to extract content from"
                    }
                },
                "required": ["url"]
            }
        ]
