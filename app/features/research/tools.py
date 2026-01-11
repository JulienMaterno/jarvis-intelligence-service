"""
Research Tools for Chat - Claude-compatible tool definitions

These tools expose the research service capabilities to the chat system.
They follow the same pattern as other chat tools in app/features/chat/tools.py.

IMPORTANT: These tools are expensive (API costs). Use with care.
- LinkedIn lookups: ~$0.01-0.05 per profile
- Web searches: ~$0.001-0.01 per search

Tools:
- linkedin_get_profile: Get LinkedIn profile by URL
- linkedin_search_profiles: Search for LinkedIn profiles
- linkedin_get_company: Get company info
- web_search: Search the web
- research_person: Comprehensive person research
- research_company: Comprehensive company research
"""

import logging
from typing import Any, Dict, List

from .service import get_research_service

logger = logging.getLogger("Jarvis.Research.Tools")


# =============================================================================
# Tool Definitions (for Claude)
# =============================================================================

RESEARCH_TOOLS = [
    {
        "name": "linkedin_get_profile",
        "description": """Get detailed LinkedIn profile information.
        
Use when user asks about a specific person's LinkedIn profile, professional background, or current role.
Requires the profile URL or username.

⚠️ COST: ~$0.01-0.05 per lookup. Only use when specifically requested.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "LinkedIn profile URL (e.g., https://linkedin.com/in/username) or just the username"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "linkedin_search_profiles",
        "description": """Search for LinkedIn profiles by keyword (name, title, company, skills).
        
Use when user wants to find people on LinkedIn by name, job title, company, or skills.
Returns a list of matching profiles.

⚠️ COST: ~$0.02-0.10 depending on result count. Only use when specifically requested.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (name, title, company, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10, max 50)",
                    "default": 10
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "linkedin_get_company",
        "description": """Get LinkedIn company page information.
        
Use when user asks about a company's LinkedIn presence, size, industry, etc.

⚠️ COST: ~$0.01-0.05 per lookup. Only use when specifically requested.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Company LinkedIn URL (e.g., https://linkedin.com/company/google) or company slug"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "linkedin_get_company_jobs",
        "description": """Get job postings from a LinkedIn company page.
        
Use when user asks about job openings at a specific company.

⚠️ COST: ~$0.02-0.10 depending on job count.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_url": {
                    "type": "string",
                    "description": "Company LinkedIn URL"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max jobs to return (default 25)",
                    "default": 25
                }
            },
            "required": ["company_url"]
        }
    },
    {
        "name": "web_search",
        "description": """Search the web for information.
        
Use when user needs current information from the web that isn't in the knowledge base.
Returns search results with titles, URLs, and snippets.

Good for:
- Current news and events
- Research on topics not in database
- Fact-checking
- Finding specific websites/resources

⚠️ Use sparingly - check database/memory first.""",
        "input_schema": {
            "type": "object",
            "properties": {
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
                    "description": "Only search these domains (e.g., ['wikipedia.org', 'reuters.com'])"
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude these domains"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "research_person",
        "description": """Comprehensive person research combining LinkedIn and web search.
        
Use when user wants thorough research on a person, combining:
- LinkedIn profile data
- Web mentions and news
- Professional background

Provide LinkedIn URL if known for best results.

⚠️ COST: Higher cost tool (~$0.05-0.15). Only use when explicitly requested.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Person's full name"
                },
                "company": {
                    "type": "string",
                    "description": "Company name (helps narrow search)"
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "LinkedIn profile URL if known"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "research_company",
        "description": """Comprehensive company research combining LinkedIn and web search.
        
Use when user wants thorough research on a company, including:
- Company profile and description
- Industry and size
- Recent news and web mentions
- Optionally: job postings and employee list

⚠️ COST: Higher cost tool. Only use when explicitly requested.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Company name"
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "LinkedIn company URL if known"
                },
                "include_jobs": {
                    "type": "boolean",
                    "description": "Include job postings (adds cost)",
                    "default": False
                },
                "include_employees": {
                    "type": "boolean",
                    "description": "Include employee list (adds cost, can be slow)",
                    "default": False
                }
            },
            "required": ["company_name"]
        }
    },
    {
        "name": "get_research_status",
        "description": "Check which research providers are configured and available.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# =============================================================================
# Tool Implementations
# =============================================================================

async def _linkedin_get_profile(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get LinkedIn profile by URL."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {
            "error": "LinkedIn research not configured",
            "message": "Set BRIGHTDATA_API_KEY to enable LinkedIn lookups."
        }
    
    url = tool_input.get("url", "")
    result = await service.linkedin.execute("get_profile", {"url": url})
    
    if result.is_success:
        return {
            "status": "success",
            "profile": result.data,
            "cache_hit": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _linkedin_search_profiles(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search LinkedIn profiles."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {
            "error": "LinkedIn research not configured",
            "message": "Set BRIGHTDATA_API_KEY to enable LinkedIn searches."
        }
    
    keyword = tool_input.get("keyword", "")
    limit = min(tool_input.get("limit", 10), 50)
    
    result = await service.linkedin.execute(
        "search_profiles",
        {"keyword": keyword, "limit": limit}
    )
    
    if result.is_success:
        return {
            "status": "success",
            "profiles": result.data,
            "count": len(result.data) if isinstance(result.data, list) else None,
            "cache_hit": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _linkedin_get_company(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get LinkedIn company info."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {
            "error": "LinkedIn research not configured",
            "message": "Set BRIGHTDATA_API_KEY to enable LinkedIn lookups."
        }
    
    url = tool_input.get("url", "")
    result = await service.linkedin.execute("get_company", {"url": url})
    
    if result.is_success:
        return {
            "status": "success",
            "company": result.data,
            "cache_hit": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _linkedin_get_company_jobs(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get company job postings."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {"error": "LinkedIn research not configured"}
    
    company_url = tool_input.get("company_url", "")
    limit = tool_input.get("limit", 25)
    
    result = await service.linkedin.execute(
        "get_company_jobs",
        {"company_url": company_url, "limit": limit}
    )
    
    if result.is_success:
        return {"status": "success", "jobs": result.data}
    else:
        return {"error": result.error, "status": result.status.value}


async def _web_search(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute web search."""
    service = get_research_service()
    
    if not service.web_search.is_configured:
        return {
            "error": "Web search not configured",
            "message": "Set TAVILY_API_KEY or another search API key."
        }
    
    query = tool_input.get("query", "")
    num_results = tool_input.get("num_results", 10)
    include_domains = tool_input.get("include_domains")
    exclude_domains = tool_input.get("exclude_domains")
    
    params = {"query": query, "num_results": num_results}
    if include_domains:
        params["include_domains"] = include_domains
    if exclude_domains:
        params["exclude_domains"] = exclude_domains
    
    result = await service.web_search.execute("search", params)
    
    if result.is_success:
        return {
            "status": "success",
            "results": result.data,
            "backend": result.metadata.get("backend"),
            "cache_hit": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _research_person(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Comprehensive person research."""
    service = get_research_service()
    
    name = tool_input.get("name", "")
    company = tool_input.get("company")
    linkedin_url = tool_input.get("linkedin_url")
    
    if not name:
        return {"error": "Name is required"}
    
    result = await service.research_person(
        name=name,
        company=company,
        linkedin_url=linkedin_url
    )
    
    return {
        "status": "success",
        "research": result,
        "sources_used": {
            "linkedin": result.get("linkedin") is not None,
            "web": result.get("web_mentions") is not None
        }
    }


async def _research_company(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Comprehensive company research."""
    service = get_research_service()
    
    company_name = tool_input.get("company_name", "")
    linkedin_url = tool_input.get("linkedin_url")
    include_jobs = tool_input.get("include_jobs", False)
    include_employees = tool_input.get("include_employees", False)
    
    if not company_name:
        return {"error": "Company name is required"}
    
    result = await service.research_company(
        company_name=company_name,
        linkedin_url=linkedin_url,
        include_jobs=include_jobs,
        include_employees=include_employees
    )
    
    return {
        "status": "success",
        "research": result
    }


async def _get_research_status(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get research service status."""
    service = get_research_service()
    return {
        "status": "success",
        "providers": service.get_status()
    }


# =============================================================================
# Tool Router (for chat service integration)
# =============================================================================

RESEARCH_TOOL_HANDLERS = {
    "linkedin_get_profile": _linkedin_get_profile,
    "linkedin_search_profiles": _linkedin_search_profiles,
    "linkedin_get_company": _linkedin_get_company,
    "linkedin_get_company_jobs": _linkedin_get_company_jobs,
    "web_search": _web_search,
    "research_person": _research_person,
    "research_company": _research_company,
    "get_research_status": _get_research_status,
}


async def handle_research_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route research tool calls to appropriate handlers.
    
    Called by the main chat service when a research tool is invoked.
    """
    handler = RESEARCH_TOOL_HANDLERS.get(tool_name)
    if handler:
        return await handler(tool_input)
    else:
        return {"error": f"Unknown research tool: {tool_name}"}


def get_research_tool_names() -> List[str]:
    """Get list of all research tool names."""
    return list(RESEARCH_TOOL_HANDLERS.keys())
