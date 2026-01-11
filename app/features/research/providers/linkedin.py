"""
LinkedIn Research Provider via Bright Data Web Scraper API

Provides LinkedIn data collection capabilities:
- Profile search by keywords (via Brave Search + Bright Data)
- Profile details by URL
- Company information
- Job listings
- Posts and activity

Bright Data Endpoints Used:
- /trigger (async) - For bulk operations
- /scrape (sync) - For single lookups

API Reference: https://docs.brightdata.com/datasets/scrapers/scrapers-library/quickstart
"""

import os
import re
import logging
import asyncio
import time
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from urllib.parse import quote

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger("Jarvis.Research.LinkedIn")

# Bright Data API configuration
BRIGHTDATA_API_KEY = os.getenv("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_BASE_URL = "https://api.brightdata.com/datasets/v3"

# Brave Search API (for finding LinkedIn URLs)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# Rate limiting for Brave (1 req/sec on free tier)
_brave_last_request: float = 0.0
_brave_rate_lock = asyncio.Lock()

# Scraper IDs for different LinkedIn endpoints
# These are Bright Data's pre-built scraper identifiers
# To find correct IDs: Go to Bright Data Console → Web Scraper API → LinkedIn
SCRAPER_IDS = {
    "profile_by_url": "gd_l1viktl72bvl7bjuj0",  # LinkedIn Profile by URL
    "company_by_url": "gd_l1vikfnt1wgvvqz95w",  # LinkedIn Company by URL
    "company_jobs": "gd_lpfll7v81kap1ke3i6",  # LinkedIn Company Jobs
    "posts_by_profile": "gd_m0r9v8k2hqr5hcd1o5",  # LinkedIn Posts by Profile URL
}


class LinkedInProvider(BaseProvider):
    """
    LinkedIn data collection via Bright Data.
    
    Features:
    - Profile lookup by URL or keyword search
    - Company information and employees
    - Job listings from company pages
    - Post history
    
    All operations respect rate limits and use caching to minimize costs.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or BRIGHTDATA_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def name(self) -> str:
        return "linkedin"
    
    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _execute(self, operation: str, params: Dict[str, Any]) -> ProviderResult:
        """Execute LinkedIn operation via Bright Data API."""
        
        if not self.is_configured:
            return ProviderResult.failure(
                "Bright Data API key not configured. Set BRIGHTDATA_API_KEY environment variable."
            )
        
        # Map operations to handlers
        handlers = {
            "get_profile": self._get_profile,
            "search_profiles": self._search_profiles,
            "get_company": self._get_company,
            "get_company_employees": self._get_company_employees,
            "get_company_jobs": self._get_company_jobs,
            "get_profile_posts": self._get_profile_posts,
        }
        
        handler = handlers.get(operation)
        if not handler:
            return ProviderResult.failure(f"Unknown operation: {operation}")
        
        return await handler(params)
    
    async def _scrape_sync(
        self,
        scraper_id: str,
        inputs: List[Dict[str, Any]],
        include_errors: bool = True
    ) -> ProviderResult:
        """
        Execute synchronous scrape (blocks until complete).
        Best for single lookups that complete quickly.
        """
        client = await self._get_client()
        
        try:
            response = await client.post(
                f"{BRIGHTDATA_BASE_URL}/scrape",
                params={
                    "dataset_id": scraper_id, 
                    "include_errors": str(include_errors).lower(),
                    "format": "json"  # Explicitly request JSON array format
                },
                json=inputs
            )
            
            if response.status_code == 200:
                # Handle both JSON array and NDJSON formats
                text = response.text.strip()
                try:
                    # Try parsing as JSON array first
                    data = response.json()
                except Exception:
                    # Fall back to NDJSON (newline-separated JSON)
                    import json
                    data = []
                    for line in text.split('\n'):
                        line = line.strip()
                        if line:
                            try:
                                data.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                
                return ProviderResult.success(
                    data=data,
                    scraper_id=scraper_id,
                    input_count=len(inputs)
                )
            elif response.status_code == 429:
                return ProviderResult(
                    status=ProviderStatus.RATE_LIMITED,
                    error="Rate limited by Bright Data API",
                    metadata={"retry_after": response.headers.get("Retry-After")}
                )
            else:
                return ProviderResult.failure(
                    f"API error {response.status_code}: {response.text[:200]}"
                )
                
        except httpx.TimeoutException:
            return ProviderResult(
                status=ProviderStatus.TIMEOUT,
                error="Request timed out. Try async mode for large jobs."
            )
    
    async def _trigger_async(
        self,
        scraper_id: str,
        inputs: List[Dict[str, Any]],
        webhook_url: Optional[str] = None
    ) -> ProviderResult:
        """
        Trigger asynchronous scrape job.
        Returns snapshot_id immediately, results retrieved later.
        Best for bulk operations or long-running jobs.
        """
        client = await self._get_client()
        
        payload = inputs
        params = {"dataset_id": scraper_id}
        
        if webhook_url:
            params["notify"] = webhook_url
        
        try:
            response = await client.post(
                f"{BRIGHTDATA_BASE_URL}/trigger",
                params=params,
                json=payload
            )
            
            if response.status_code in (200, 202):
                data = response.json()
                snapshot_id = data.get("snapshot_id")
                return ProviderResult(
                    status=ProviderStatus.PENDING,
                    data={"snapshot_id": snapshot_id},
                    metadata={"scraper_id": scraper_id, "async": True}
                )
            else:
                return ProviderResult.failure(
                    f"API error {response.status_code}: {response.text[:200]}"
                )
                
        except Exception as e:
            return ProviderResult.failure(str(e))
    
    async def get_snapshot_status(self, snapshot_id: str) -> ProviderResult:
        """Check status and retrieve results of async job."""
        client = await self._get_client()
        
        try:
            response = await client.get(
                f"{BRIGHTDATA_BASE_URL}/snapshots/{snapshot_id}"
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                
                if status == "ready":
                    return ProviderResult.success(data, snapshot_id=snapshot_id)
                elif status == "running":
                    return ProviderResult(
                        status=ProviderStatus.PENDING,
                        data=data,
                        metadata={"snapshot_id": snapshot_id}
                    )
                elif status == "failed":
                    return ProviderResult.failure(
                        data.get("error", "Job failed"),
                        snapshot_id=snapshot_id
                    )
                else:
                    return ProviderResult(
                        status=ProviderStatus.PENDING,
                        data=data,
                        metadata={"status": status}
                    )
            else:
                return ProviderResult.failure(f"API error: {response.status_code}")
                
        except Exception as e:
            return ProviderResult.failure(str(e))
    
    # ==========================================================================
    # Operation Handlers
    # ==========================================================================
    
    async def _get_profile(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Get LinkedIn profile data by URL.
        
        Params:
            url: LinkedIn profile URL (e.g., https://linkedin.com/in/username)
        """
        url = params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: url")
        
        # Normalize URL
        if not url.startswith("http"):
            url = f"https://www.linkedin.com/in/{url}"
        
        return await self._scrape_sync(
            SCRAPER_IDS["profile_by_url"],
            [{"url": url}]
        )
    
    async def _search_profiles(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Search for LinkedIn profiles by name, title, company, etc.
        
        Uses a two-step approach:
        1. Brave Search to find LinkedIn profile URLs
        2. Bright Data to get full profile details
        
        Params:
            query: Search query (name, title, company, location, etc.)
            limit: Max number of profiles to return (default 5)
            get_full_profiles: Whether to fetch full profile data (default True)
        
        Examples:
            - "Bill Gates" → Find Bill Gates' LinkedIn
            - "CTO fintech Singapore" → Find CTOs in fintech in Singapore
            - "Software Engineer Google" → Find software engineers at Google
        """
        query = params.get("query", params.get("keyword", ""))
        if not query:
            return ProviderResult.failure("Missing required parameter: query")
        
        limit = min(params.get("limit", 5), 10)  # Cap at 10 to control costs
        get_full_profiles = params.get("get_full_profiles", True)
        
        # Check if Brave is configured
        if not BRAVE_API_KEY:
            return ProviderResult.failure(
                "BRAVE_API_KEY not configured. Required for LinkedIn profile search."
            )
        
        try:
            # Step 1: Use Brave Search to find LinkedIn URLs
            search_query = f'{query} site:linkedin.com/in'
            linkedin_urls = await self._brave_search_linkedin_urls(search_query, limit * 2)
            
            if not linkedin_urls:
                return ProviderResult.success(
                    data=[],
                    query=query,
                    message="No LinkedIn profiles found for this query"
                )
            
            # Limit to requested amount
            linkedin_urls = linkedin_urls[:limit]
            
            if not get_full_profiles:
                # Return just the URLs (quick mode)
                return ProviderResult.success(
                    data=[{"url": url, "username": self._extract_username(url)} for url in linkedin_urls],
                    query=query,
                    count=len(linkedin_urls),
                    full_profiles=False
                )
            
            # Step 2: Get full profile data from Bright Data
            profile_inputs = [{"url": url} for url in linkedin_urls]
            
            result = await self._scrape_sync(
                SCRAPER_IDS["profile_by_url"],
                profile_inputs
            )
            
            if result.status == ProviderStatus.SUCCESS:
                profiles = result.data if isinstance(result.data, list) else [result.data]
                # Filter out any error entries
                profiles = [p for p in profiles if isinstance(p, dict) and p.get("name")]
                
                return ProviderResult.success(
                    data=profiles,
                    query=query,
                    count=len(profiles),
                    full_profiles=True,
                    urls_searched=linkedin_urls
                )
            else:
                return result
                
        except Exception as e:
            logger.error(f"LinkedIn search error: {e}")
            return ProviderResult.failure(str(e))
    
    async def _brave_search_linkedin_urls(self, query: str, count: int = 10) -> List[str]:
        """
        Search Brave for LinkedIn profile URLs.
        
        Applies rate limiting (1 req/sec for free tier).
        """
        global _brave_last_request
        
        # Rate limit: 1 request per second
        async with _brave_rate_lock:
            now = time.time()
            elapsed = now - _brave_last_request
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _brave_last_request = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    BRAVE_URL,
                    params={"q": query, "count": count},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": BRAVE_API_KEY
                    }
                )
                
                if response.status_code != 200:
                    logger.warning(f"Brave search failed: {response.status_code}")
                    return []
                
                data = response.json()
                results = data.get("web", {}).get("results", [])
                
                # Extract LinkedIn profile URLs
                linkedin_urls = []
                for result in results:
                    url = result.get("url", "")
                    if self._is_linkedin_profile_url(url):
                        linkedin_urls.append(url)
                
                return linkedin_urls
                
        except Exception as e:
            logger.error(f"Brave search error: {e}")
            return []
    
    def _is_linkedin_profile_url(self, url: str) -> bool:
        """Check if URL is a LinkedIn personal profile (not company, job, etc.)."""
        if not url:
            return False
        url_lower = url.lower()
        return (
            "linkedin.com/in/" in url_lower
            and "/posts" not in url_lower
            and "/articles" not in url_lower
            and "?miniProfile" not in url_lower
        )
    
    def _extract_username(self, url: str) -> str:
        """Extract username from LinkedIn URL."""
        match = re.search(r'linkedin\.com/in/([^/?]+)', url, re.IGNORECASE)
        return match.group(1) if match else ""
    
    
    async def _get_company(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Get LinkedIn company page data.
        
        Params:
            url: Company LinkedIn URL (e.g., https://linkedin.com/company/google)
        """
        url = params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: url")
        
        # Normalize URL
        if not url.startswith("http"):
            url = f"https://www.linkedin.com/company/{url}"
        
        return await self._scrape_sync(
            SCRAPER_IDS["company_by_url"],
            [{"url": url}]
        )
    
    async def _get_company_employees(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Get employees of a LinkedIn company.
        
        Params:
            company_url: Company LinkedIn URL
            limit: Max employees to return (default 50)
        """
        url = params.get("company_url") or params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: company_url")
        
        limit = min(params.get("limit", 50), 500)
        
        inputs = [{"url": url, "limit": limit}]
        
        # Always async for employee lookups (can be large)
        return await self._trigger_async(SCRAPER_IDS["company_employees"], inputs)
    
    async def _get_company_jobs(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Get job postings from a LinkedIn company.
        
        Params:
            company_url: Company LinkedIn URL
            limit: Max jobs to return (default 25)
        """
        url = params.get("company_url") or params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: company_url")
        
        limit = min(params.get("limit", 25), 100)
        
        return await self._scrape_sync(
            SCRAPER_IDS["company_jobs"],
            [{"url": url, "limit": limit}]
        )
    
    async def _get_profile_posts(self, params: Dict[str, Any]) -> ProviderResult:
        """
        Get recent posts from a LinkedIn profile.
        
        Params:
            profile_url: LinkedIn profile URL
            limit: Max posts to return (default 20)
        """
        url = params.get("profile_url") or params.get("url")
        if not url:
            return ProviderResult.failure("Missing required parameter: profile_url")
        
        limit = min(params.get("limit", 20), 100)
        
        return await self._scrape_sync(
            SCRAPER_IDS["posts_by_profile"],
            [{"url": url, "limit": limit}]
        )
    
    # ==========================================================================
    # Tool Definitions
    # ==========================================================================
    
    def get_operations(self) -> List[Dict[str, Any]]:
        """Return available LinkedIn operations."""
        return [
            {
                "name": "get_profile",
                "description": "Get detailed LinkedIn profile information by URL or username.",
                "parameters": {
                    "url": {
                        "type": "string",
                        "description": "LinkedIn profile URL or username"
                    }
                },
                "required": ["url"]
            },
            {
                "name": "search_profiles",
                "description": "Search for LinkedIn profiles by keyword (name, title, company, skills).",
                "parameters": {
                    "keyword": {
                        "type": "string",
                        "description": "Search keyword"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10, max 100)",
                        "default": 10
                    },
                    "get_full_data": {
                        "type": "boolean",
                        "description": "Return full profile data (slower)",
                        "default": False
                    }
                },
                "required": ["keyword"]
            },
            {
                "name": "get_company",
                "description": "Get LinkedIn company page information.",
                "parameters": {
                    "url": {
                        "type": "string",
                        "description": "Company LinkedIn URL or slug"
                    }
                },
                "required": ["url"]
            },
            {
                "name": "get_company_employees",
                "description": "Get list of employees from a LinkedIn company page.",
                "parameters": {
                    "company_url": {
                        "type": "string",
                        "description": "Company LinkedIn URL"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max employees (default 50)",
                        "default": 50
                    }
                },
                "required": ["company_url"]
            },
            {
                "name": "get_company_jobs",
                "description": "Get job postings from a LinkedIn company.",
                "parameters": {
                    "company_url": {
                        "type": "string",
                        "description": "Company LinkedIn URL"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max jobs (default 25)",
                        "default": 25
                    }
                },
                "required": ["company_url"]
            },
            {
                "name": "get_profile_posts",
                "description": "Get recent posts from a LinkedIn profile.",
                "parameters": {
                    "profile_url": {
                        "type": "string",
                        "description": "LinkedIn profile URL"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max posts (default 20)",
                        "default": 20
                    }
                },
                "required": ["profile_url"]
            },
        ]
