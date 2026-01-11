"""
LinkedIn Research Provider via Bright Data Web Scraper API

Provides LinkedIn data collection capabilities:
- Profile search by keywords
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
import logging
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger("Jarvis.Research.LinkedIn")

# Bright Data API configuration
BRIGHTDATA_API_KEY = os.getenv("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_BASE_URL = "https://api.brightdata.com/datasets/v3"

# Scraper IDs for different LinkedIn endpoints
# These are Bright Data's pre-built scraper identifiers
SCRAPER_IDS = {
    "profile_by_url": "gd_l1viktl72bvl7bjuj0",  # LinkedIn Profile by URL
    "profiles_by_keyword": "gd_l7q7dkf244hwjntr0",  # LinkedIn Profiles by Keyword
    "company_by_url": "gd_l1vikfnt1wgvvqz95w",  # LinkedIn Company by URL
    "company_employees": "gd_lyclf27l1hm8oagtho",  # LinkedIn Company Employees
    "company_jobs": "gd_lpfll7v81kap1ke3i6",  # LinkedIn Company Jobs
    "posts_by_profile": "gd_m0r9v8k2hqr5hcd1o5",  # LinkedIn Posts by Profile
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
                params={"dataset_id": scraper_id, "include_errors": str(include_errors).lower()},
                json=inputs
            )
            
            if response.status_code == 200:
                data = response.json()
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
        Search for LinkedIn profiles by keyword.
        
        Params:
            keyword: Search term (name, title, company, etc.)
            limit: Max results (default 10, max 100)
            get_full_data: Whether to return full profile data (slower, costs more)
        """
        keyword = params.get("keyword")
        if not keyword:
            return ProviderResult.failure("Missing required parameter: keyword")
        
        limit = min(params.get("limit", 10), 100)
        get_full_data = params.get("get_full_data", False)
        
        inputs = [{
            "keyword": keyword,
            "limit": limit,
            "get_full_data": get_full_data
        }]
        
        # Use async for large searches
        if limit > 20 or get_full_data:
            return await self._trigger_async(SCRAPER_IDS["profiles_by_keyword"], inputs)
        else:
            return await self._scrape_sync(SCRAPER_IDS["profiles_by_keyword"], inputs)
    
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
