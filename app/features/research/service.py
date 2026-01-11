"""
Research Service - Unified Interface for Research Operations

Provides a single entry point for all research capabilities:
- LinkedIn research (profiles, companies, jobs)
- Web search (multiple backends)
- Content scraping (TODO)

Design Goals:
1. Single service instance (singleton pattern)
2. Lazy loading of providers (only init when used)
3. Unified API for chat tools and background agents
4. LibreChat compatible tool definitions
5. Caching across all providers
"""

import logging
from typing import Any, Dict, List, Optional
from functools import lru_cache

from .providers.base import ProviderResult
from .providers.linkedin import LinkedInProvider
from .providers.web_search import WebSearchProvider

logger = logging.getLogger("Jarvis.Research")


class ResearchService:
    """
    Unified research service providing access to all research providers.
    
    Features:
    - Lazy-loaded providers (initialized on first use)
    - Unified tool interface for chat/agents
    - Provider health checking
    - Batch operations (TODO)
    
    Usage:
        service = get_research_service()
        
        # LinkedIn lookup
        result = await service.linkedin.execute("get_profile", {"url": "..."})
        
        # Web search
        result = await service.web_search.execute("search", {"query": "..."})
        
        # Or via unified interface
        result = await service.execute("linkedin", "get_profile", {"url": "..."})
    """
    
    _instance: Optional["ResearchService"] = None
    
    def __init__(self):
        self._linkedin: Optional[LinkedInProvider] = None
        self._web_search: Optional[WebSearchProvider] = None
        self._initialized = False
        logger.info("ResearchService initialized")
    
    @classmethod
    def get_instance(cls) -> "ResearchService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    # ==========================================================================
    # Provider Properties (Lazy Loading)
    # ==========================================================================
    
    @property
    def linkedin(self) -> LinkedInProvider:
        """Get LinkedIn provider (lazy loaded)."""
        if self._linkedin is None:
            self._linkedin = LinkedInProvider()
            logger.info(f"LinkedIn provider initialized (configured: {self._linkedin.is_configured})")
        return self._linkedin
    
    @property
    def web_search(self) -> WebSearchProvider:
        """Get web search provider (lazy loaded)."""
        if self._web_search is None:
            self._web_search = WebSearchProvider()
            logger.info(f"WebSearch provider initialized (configured: {self._web_search.is_configured})")
        return self._web_search
    
    # ==========================================================================
    # Unified Interface
    # ==========================================================================
    
    async def execute(
        self,
        provider: str,
        operation: str,
        params: Dict[str, Any],
        use_cache: bool = True
    ) -> ProviderResult:
        """
        Execute a research operation on a specific provider.
        
        Args:
            provider: Provider name ('linkedin', 'web_search')
            operation: Operation to execute
            params: Operation parameters
            use_cache: Whether to use caching
            
        Returns:
            ProviderResult with data or error
        """
        provider_instance = self._get_provider(provider)
        if provider_instance is None:
            return ProviderResult.failure(f"Unknown provider: {provider}")
        
        return await provider_instance.execute(operation, params, use_cache=use_cache)
    
    def _get_provider(self, name: str):
        """Get provider by name."""
        providers = {
            "linkedin": self.linkedin,
            "web_search": self.web_search,
            "websearch": self.web_search,  # alias
        }
        return providers.get(name.lower())
    
    # ==========================================================================
    # Health & Status
    # ==========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all research providers."""
        return {
            "linkedin": {
                "configured": self.linkedin.is_configured,
                "provider": "Bright Data Scrapers API",
                "operations": len(self.linkedin.get_operations())
            },
            "web_search": {
                "configured": self.web_search.is_configured,
                "provider": "Brave Search API",
                "operations": len(self.web_search.get_operations())
            }
        }
    
    # ==========================================================================
    # Tool Definitions (for Chat/Agents)
    # ==========================================================================
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions for all providers.
        Compatible with Claude's tool format.
        """
        tools = []
        
        # Add LinkedIn tools if configured
        if self.linkedin.is_configured:
            tools.extend(self.linkedin.to_tool_definitions())
        
        # Add Web Search tools if configured
        if self.web_search.is_configured:
            tools.extend(self.web_search.to_tool_definitions())
        
        return tools
    
    def get_tools_for_provider(self, provider: str) -> List[Dict[str, Any]]:
        """Get tool definitions for a specific provider."""
        provider_instance = self._get_provider(provider)
        if provider_instance:
            return provider_instance.to_tool_definitions()
        return []
    
    # ==========================================================================
    # High-Level Research Operations
    # ==========================================================================
    
    async def research_person(
        self,
        name: str,
        company: Optional[str] = None,
        linkedin_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive person research combining multiple sources.
        
        Args:
            name: Person's name
            company: Company name (optional, helps narrow search)
            linkedin_url: Direct LinkedIn URL (optional)
            
        Returns:
            Combined research results
        """
        results = {
            "name": name,
            "company": company,
            "linkedin": None,
            "web_mentions": None,
            "errors": []
        }
        
        # Try LinkedIn first
        if linkedin_url:
            linkedin_result = await self.linkedin.execute(
                "get_profile", {"url": linkedin_url}
            )
            if linkedin_result.is_success:
                results["linkedin"] = linkedin_result.data
            else:
                results["errors"].append(f"LinkedIn: {linkedin_result.error}")
        elif self.linkedin.is_configured:
            # Search by name
            search_query = f"{name} {company}" if company else name
            linkedin_result = await self.linkedin.execute(
                "search_profiles", {"keyword": search_query, "limit": 5}
            )
            if linkedin_result.is_success:
                results["linkedin"] = linkedin_result.data
            else:
                results["errors"].append(f"LinkedIn: {linkedin_result.error}")
        
        # Web search for additional context
        if self.web_search.is_configured:
            search_query = f'"{name}"'
            if company:
                search_query += f' "{company}"'
            
            web_result = await self.web_search.execute(
                "search", {"query": search_query, "num_results": 10}
            )
            if web_result.is_success:
                results["web_mentions"] = web_result.data
            else:
                results["errors"].append(f"Web: {web_result.error}")
        
        return results
    
    async def research_company(
        self,
        company_name: str,
        linkedin_url: Optional[str] = None,
        include_jobs: bool = False,
        include_employees: bool = False
    ) -> Dict[str, Any]:
        """
        Comprehensive company research.
        
        Args:
            company_name: Company name
            linkedin_url: Direct LinkedIn company URL (optional)
            include_jobs: Include job postings
            include_employees: Include employee list
            
        Returns:
            Combined company research
        """
        results = {
            "company": company_name,
            "linkedin_profile": None,
            "jobs": None,
            "employees": None,
            "web_mentions": None,
            "errors": []
        }
        
        # LinkedIn company lookup
        if linkedin_url and self.linkedin.is_configured:
            company_result = await self.linkedin.execute(
                "get_company", {"url": linkedin_url}
            )
            if company_result.is_success:
                results["linkedin_profile"] = company_result.data
                
                # Get jobs if requested
                if include_jobs:
                    jobs_result = await self.linkedin.execute(
                        "get_company_jobs", {"company_url": linkedin_url}
                    )
                    if jobs_result.is_success:
                        results["jobs"] = jobs_result.data
                
                # Get employees if requested
                if include_employees:
                    emp_result = await self.linkedin.execute(
                        "get_company_employees", {"company_url": linkedin_url}
                    )
                    if emp_result.is_success:
                        results["employees"] = emp_result.data
            else:
                results["errors"].append(f"LinkedIn: {company_result.error}")
        
        # Web search for company info
        if self.web_search.is_configured:
            web_result = await self.web_search.execute(
                "search", {"query": f'"{company_name}" company', "num_results": 10}
            )
            if web_result.is_success:
                results["web_mentions"] = web_result.data
        
        return results
    
    # ==========================================================================
    # Cleanup
    # ==========================================================================
    
    async def close(self):
        """Close all provider connections."""
        if self._linkedin:
            await self._linkedin.close()
        if self._web_search:
            await self._web_search.close()
        logger.info("ResearchService closed")


# =============================================================================
# Module-Level Singleton Access
# =============================================================================

@lru_cache(maxsize=1)
def get_research_service() -> ResearchService:
    """
    Get the research service singleton.
    
    Usage:
        from app.features.research import get_research_service
        
        service = get_research_service()
        result = await service.linkedin.execute("get_profile", {"url": "..."})
    """
    return ResearchService.get_instance()
