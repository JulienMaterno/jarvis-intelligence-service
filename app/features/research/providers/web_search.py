"""
Web Search Provider - Brave Search API

Uses Brave Search for general web queries.
Brave is privacy-focused, high-quality, and cost-effective.

Sign up: https://brave.com/search/api/
Pricing: Free tier (2000 queries/month), then ~$3/1000 queries

RATE LIMIT: 1 request per second on free tier
"""

import os
import logging
import asyncio
import time
import httpx
from typing import Any, Dict, List, Optional

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger("Jarvis.Research.WebSearch")


# API configuration
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"

# Rate limiting: 1 request per second
_last_request_time: float = 0.0
_rate_limit_lock = asyncio.Lock()


class WebSearchProvider(BaseProvider):
    """
    Web search provider using Brave Search API.
    
    Features:
    - General web search
    - News search
    - Result snippets and URLs
    - Built-in rate limiting (1 req/sec)
    
    Cost: ~$0.003 per query (after free tier)
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or BRAVE_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def is_configured(self) -> bool:
        """Check if Brave API key is configured."""
        return bool(self.api_key)
    
    async def _rate_limit(self):
        """Ensure we don't exceed 1 request per second."""
        global _last_request_time
        async with _rate_limit_lock:
            now = time.time()
            elapsed = now - _last_request_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _last_request_time = time.time()
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "X-Subscription-Token": self.api_key,
                    "Accept": "application/json"
                }
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _execute(self, operation: str, params: Dict[str, Any]) -> ProviderResult:
        """Execute web search operation."""
        
        if not self.is_configured:
            return ProviderResult.failure(
                "Brave Search API not configured. Set BRAVE_API_KEY environment variable.\n"
                "Sign up at: https://brave.com/search/api/"
            )
        
        handlers = {
            "search": self._search,
            "search_news": self._search_news,
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
            num_results: Number of results (default 10, max 20)
            country: Country code for localized results (e.g., 'US', 'DE', 'VN')
            freshness: Filter by age ('pd'=past day, 'pw'=past week, 'pm'=past month)
        """
        query = params.get("query")
        if not query:
            return ProviderResult.failure("Missing required parameter: query")
        
        num_results = min(params.get("num_results", 10), 20)
        
        # Rate limit: 1 request per second
        await self._rate_limit()
        
        client = await self._get_client()
        
        request_params = {
            "q": query,
            "count": num_results,
        }
        
        # Optional filters
        if params.get("country"):
            request_params["country"] = params["country"]
        if params.get("freshness"):
            request_params["freshness"] = params["freshness"]
        
        try:
            response = await client.get(BRAVE_URL, params=request_params)
            
            if response.status_code == 200:
                data = response.json()
                results = self._normalize_results(data)
                return ProviderResult.success(results, raw_response=data)
            elif response.status_code == 401:
                return ProviderResult.failure("Invalid Brave API key")
            elif response.status_code == 429:
                return ProviderResult(
                    status=ProviderStatus.RATE_LIMITED,
                    error="Rate limited. Check your Brave API quota."
                )
            else:
                return ProviderResult.failure(f"Brave API error: {response.status_code}")
                
        except httpx.TimeoutException:
            return ProviderResult(
                status=ProviderStatus.TIMEOUT,
                error="Search request timed out"
            )
        except Exception as e:
            return ProviderResult.failure(str(e))
    
    async def _search_news(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Search for news articles.
        
        Params:
            query: News search query
            num_results: Number of results (default 10, max 20)
            freshness: Filter by age ('pd'=past day, 'pw'=past week, 'pm'=past month)
        """
        query = params.get("query")
        if not query:
            return ProviderResult.failure("Missing required parameter: query")
        
        num_results = min(params.get("num_results", 10), 20)
        
        # Rate limit: 1 request per second
        await self._rate_limit()
        
        client = await self._get_client()
        
        request_params = {
            "q": query,
            "count": num_results,
        }
        
        if params.get("freshness"):
            request_params["freshness"] = params["freshness"]
        
        try:
            response = await client.get(BRAVE_NEWS_URL, params=request_params)
            
            if response.status_code == 200:
                data = response.json()
                results = self._normalize_news_results(data)
                return ProviderResult.success(results, raw_response=data)
            else:
                return ProviderResult.failure(f"Brave News API error: {response.status_code}")
                
        except Exception as e:
            return ProviderResult.failure(str(e))
    
    def _normalize_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize Brave Search results to common format."""
        web = data.get("web", {}).get("results", [])
        return {
            "query": data.get("query", {}).get("original"),
            "total_results": data.get("web", {}).get("total_results"),
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("description"),
                    "published_date": r.get("age"),
                    "source": r.get("meta_url", {}).get("hostname"),
                }
                for r in web
            ]
        }
    
    def _normalize_news_results(self, data: Dict) -> Dict[str, Any]:
        """Normalize Brave News results."""
        results = data.get("results", [])
        return {
            "query": data.get("query", {}).get("original"),
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("description"),
                    "published_date": r.get("age"),
                    "source": r.get("meta_url", {}).get("hostname"),
                    "thumbnail": r.get("thumbnail", {}).get("src"),
                }
                for r in results
            ]
        }
    
    def get_operations(self) -> List[Dict[str, Any]]:
        """Return available web search operations."""
        return [
            {
                "name": "search",
                "description": "Search the web for information using Brave Search.",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default 10, max 20)",
                        "default": 10
                    },
                    "country": {
                        "type": "string",
                        "description": "Country code for localized results (e.g., 'US', 'DE', 'VN')"
                    },
                    "freshness": {
                        "type": "string",
                        "description": "Filter by age: 'pd'=past day, 'pw'=past week, 'pm'=past month"
                    }
                },
                "required": ["query"]
            },
            {
                "name": "search_news",
                "description": "Search for news articles using Brave News.",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "News search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default 10, max 20)",
                        "default": 10
                    },
                    "freshness": {
                        "type": "string",
                        "description": "Filter by age: 'pd'=past day, 'pw'=past week, 'pm'=past month"
                    }
                },
                "required": ["query"]
            }
        ]
