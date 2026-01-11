"""
Research Tools for Chat - Claude-compatible tool definitions

These tools expose LinkedIn research and web search capabilities.
They follow the same pattern as other chat tools in app/features/chat/tools.py.

Providers:
- LinkedIn: Bright Data Web Scraper API (sign up at https://brightdata.com)
- Web Search: Brave Search API (sign up at https://brave.com/search/api/)

Cost guidance:
- LinkedIn profile lookup: ~$0.01-0.05 each
- LinkedIn profile search: ~$0.02-0.10 per search
- Web search: ~$0.003 per query (2000 free/month on Brave)
"""

import logging
from typing import Any, Dict, List

from .service import get_research_service

logger = logging.getLogger("Jarvis.Research.Tools")


# =============================================================================
# Tool Definitions (for Claude)
# =============================================================================

RESEARCH_TOOLS = [
    # -------------------------------------------------------------------------
    # LinkedIn Tools (Bright Data)
    # -------------------------------------------------------------------------
    {
        "name": "linkedin_get_profiles",
        "description": """Get LinkedIn profile(s) by URL. Can handle single or multiple URLs.

USE WHEN:
- User provides one or more LinkedIn profile URLs
- User asks about a specific person's professional background
- Need to look up contacts by their LinkedIn URL

EXAMPLES:
- "Get the profile for linkedin.com/in/satya-nadella" → single URL
- "Look up these 5 people: [url1, url2, ...]" → batch of URLs
- "What does John's LinkedIn say?" (if URL is known)

⚠️ COST: ~$0.01-0.05 per profile. Use batch mode for multiple URLs (more efficient).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of LinkedIn profile URLs or usernames (1-20 URLs)"
                }
            },
            "required": ["urls"]
        }
    },
    {
        "name": "linkedin_search_people",
        "description": """Search LinkedIn for people matching keywords like name, title, company, location.

USE WHEN:
- User wants to find people by criteria (e.g., "Founders in Ho Chi Minh City")
- Looking for professionals with specific skills or titles
- Need to discover potential contacts, leads, or experts
- User asks "find me [person type] at [company/location]"

SEARCH TIPS:
- Be specific: "CTO fintech Singapore" works better than just "CTO"
- Include name if known: "John Smith product manager"
- Combine criteria: "Software Engineer AI startup HCMC"
- Include company: "VP Engineering at Google"

RETURNS: Full LinkedIn profiles including name, title, company, experience, education, and more.

⚠️ COST: ~$0.05-0.50 per search (Brave + Bright Data combined). Results are cached.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (combine: name, title, company, location, skills)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of profiles to return (default 5, max 10)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "linkedin_get_company",
        "description": """Get LinkedIn company page information.

USE WHEN:
- User asks about a company's LinkedIn profile
- Need company size, industry, description, location
- Researching a company before a meeting

⚠️ COST: ~$0.01-0.05 per lookup.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Company LinkedIn URL (e.g., linkedin.com/company/google) or company slug"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "linkedin_get_company_employees",
        "description": """Get list of employees at a company from LinkedIn.

USE WHEN:
- User wants to see who works at a company
- Looking for specific roles at a company
- Building a contact list for a target company

NOTE: This is an async operation for large results. May return a job ID to check later.

⚠️ COST: ~$0.05-0.20 depending on company size.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_url": {
                    "type": "string",
                    "description": "Company LinkedIn URL"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max employees (default 50, max 200)",
                    "default": 50
                }
            },
            "required": ["company_url"]
        }
    },
    {
        "name": "linkedin_get_company_jobs",
        "description": """Get job postings from a company's LinkedIn page.

USE WHEN:
- User asks about job openings at a company
- Researching hiring trends
- Looking for opportunities at a specific company

⚠️ COST: ~$0.02-0.10.""",
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
    # -------------------------------------------------------------------------
    # Web Search Tools (Brave)
    # -------------------------------------------------------------------------
    {
        "name": "web_search",
        "description": """Search the web using Brave Search.

USE WHEN:
- User needs current information not in your knowledge
- Fact-checking or research on any topic
- Looking up websites, news, or recent events
- Finding information about companies, products, people (non-LinkedIn)

DO NOT USE FOR:
- LinkedIn profiles (use linkedin_* tools instead)
- Information already in the database/memory

TIPS:
- Be specific in queries for better results
- Use 'freshness' for time-sensitive queries

⚠️ COST: ~$0.003/query (2000 free/month on Brave).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (default 10, max 20)",
                    "default": 10
                },
                "freshness": {
                    "type": "string",
                    "description": "Filter by recency: 'pd' (past day), 'pw' (past week), 'pm' (past month)",
                    "enum": ["pd", "pw", "pm"]
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_search_news",
        "description": """Search for news articles using Brave News.

USE WHEN:
- User asks about recent news or events
- Need to find news coverage about a company/person
- Researching current events

⚠️ COST: ~$0.003/query.""",
        "input_schema": {
            "type": "object",
            "properties": {
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
        }
    },
    # -------------------------------------------------------------------------
    # Meta Tools
    # -------------------------------------------------------------------------
    {
        "name": "get_research_status",
        "description": "Check which research providers are configured and available. Use this to diagnose configuration issues.",
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

async def _linkedin_get_profiles(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get LinkedIn profile(s) by URL - supports batch."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {
            "error": "LinkedIn research not configured",
            "setup": "Sign up at https://brightdata.com → Get Scrapers API key → Set BRIGHTDATA_API_KEY"
        }
    
    urls = tool_input.get("urls", [])
    if isinstance(urls, str):
        urls = [urls]  # Handle single URL passed as string
    
    if not urls:
        return {"error": "No URLs provided"}
    
    if len(urls) > 20:
        return {"error": f"Too many URLs ({len(urls)}). Maximum is 20 per request."}
    
    results = []
    errors = []
    
    for url in urls:
        try:
            result = await service.linkedin.execute("get_profile", {"url": url})
            if result.is_success:
                results.append({
                    "url": url,
                    "profile": result.data,
                    "cached": result.metadata.get("cache_hit", False)
                })
            else:
                errors.append({"url": url, "error": result.error})
        except Exception as e:
            errors.append({"url": url, "error": str(e)})
    
    return {
        "status": "success" if results else "failed",
        "profiles": results,
        "errors": errors if errors else None,
        "count": len(results),
        "failed_count": len(errors)
    }


async def _linkedin_search_people(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search LinkedIn for people."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {
            "error": "LinkedIn research not configured",
            "setup": "Sign up at https://brightdata.com → Get Scrapers API key → Set BRIGHTDATA_API_KEY"
        }
    
    query = tool_input.get("query", "")
    if not query:
        return {"error": "Search query is required"}
    
    limit = min(tool_input.get("limit", 10), 50)
    
    result = await service.linkedin.execute(
        "search_profiles",
        {"keyword": query, "limit": limit}
    )
    
    if result.is_success:
        # Handle both list response and async job response
        data = result.data
        if isinstance(data, dict) and data.get("snapshot_id"):
            return {
                "status": "pending",
                "message": "Large search started. Results will be available soon.",
                "snapshot_id": data["snapshot_id"]
            }
        
        profiles = data if isinstance(data, list) else []
        return {
            "status": "success",
            "profiles": profiles,
            "count": len(profiles),
            "query": query,
            "cached": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _linkedin_get_company(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get LinkedIn company info."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {"error": "LinkedIn research not configured"}
    
    url = tool_input.get("url", "")
    if not url:
        return {"error": "Company URL is required"}
    
    result = await service.linkedin.execute("get_company", {"url": url})
    
    if result.is_success:
        return {
            "status": "success",
            "company": result.data,
            "cached": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error}


async def _linkedin_get_company_employees(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get company employees from LinkedIn."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {"error": "LinkedIn research not configured"}
    
    company_url = tool_input.get("company_url", "")
    if not company_url:
        return {"error": "Company URL is required"}
    
    limit = min(tool_input.get("limit", 50), 200)
    
    result = await service.linkedin.execute(
        "get_company_employees",
        {"company_url": company_url, "limit": limit}
    )
    
    if result.is_success:
        data = result.data
        if isinstance(data, dict) and data.get("snapshot_id"):
            return {
                "status": "pending",
                "message": "Employee lookup started (async). Results will be available soon.",
                "snapshot_id": data["snapshot_id"]
            }
        return {"status": "success", "employees": data}
    else:
        return {"error": result.error}


async def _linkedin_get_company_jobs(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get company job postings."""
    service = get_research_service()
    
    if not service.linkedin.is_configured:
        return {"error": "LinkedIn research not configured"}
    
    company_url = tool_input.get("company_url", "")
    if not company_url:
        return {"error": "Company URL is required"}
    
    limit = tool_input.get("limit", 25)
    
    result = await service.linkedin.execute(
        "get_company_jobs",
        {"company_url": company_url, "limit": limit}
    )
    
    if result.is_success:
        return {"status": "success", "jobs": result.data}
    else:
        return {"error": result.error}


async def _web_search(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute web search via Brave."""
    service = get_research_service()
    
    if not service.web_search.is_configured:
        return {
            "error": "Web search not configured",
            "setup": "Sign up at https://brave.com/search/api/ → Set BRAVE_API_KEY"
        }
    
    query = tool_input.get("query", "")
    if not query:
        return {"error": "Search query is required"}
    
    params = {
        "query": query,
        "num_results": tool_input.get("num_results", 10)
    }
    if tool_input.get("freshness"):
        params["freshness"] = tool_input["freshness"]
    
    result = await service.web_search.execute("search", params)
    
    if result.is_success:
        return {
            "status": "success",
            "results": result.data,
            "cached": result.metadata.get("cache_hit", False)
        }
    else:
        return {"error": result.error, "status": result.status.value}


async def _web_search_news(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search news articles."""
    service = get_research_service()
    
    if not service.web_search.is_configured:
        return {"error": "Web search not configured"}
    
    query = tool_input.get("query", "")
    if not query:
        return {"error": "Search query is required"}
    
    params = {
        "query": query,
        "num_results": tool_input.get("num_results", 10)
    }
    
    result = await service.web_search.execute("search_news", params)
    
    if result.is_success:
        return {"status": "success", "articles": result.data}
    else:
        return {"error": result.error}


async def _get_research_status(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get research service status."""
    service = get_research_service()
    status = service.get_status()
    
    return {
        "status": "success",
        "providers": status,
        "setup_instructions": {
            "linkedin": "Bright Data Scrapers API → https://brightdata.com → Set BRIGHTDATA_API_KEY",
            "web_search": "Brave Search API → https://brave.com/search/api/ → Set BRAVE_API_KEY"
        }
    }


# =============================================================================
# Tool Router
# =============================================================================

RESEARCH_TOOL_HANDLERS = {
    "linkedin_get_profiles": _linkedin_get_profiles,
    "linkedin_search_people": _linkedin_search_people,
    "linkedin_get_company": _linkedin_get_company,
    "linkedin_get_company_employees": _linkedin_get_company_employees,
    "linkedin_get_company_jobs": _linkedin_get_company_jobs,
    "web_search": _web_search,
    "web_search_news": _web_search_news,
    "get_research_status": _get_research_status,
}


async def handle_research_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route research tool calls to appropriate handlers.
    
    Called by the main chat service when a research tool is invoked.
    """
    handler = RESEARCH_TOOL_HANDLERS.get(tool_name)
    if handler:
        try:
            return await handler(tool_input)
        except Exception as e:
            logger.error(f"Research tool error ({tool_name}): {e}")
            return {"error": str(e), "tool": tool_name}
    else:
        return {"error": f"Unknown research tool: {tool_name}"}


def get_research_tool_names() -> List[str]:
    """Get list of all research tool names."""
    return list(RESEARCH_TOOL_HANDLERS.keys())
