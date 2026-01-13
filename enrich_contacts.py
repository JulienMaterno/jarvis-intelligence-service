"""
Contact Enrichment Service - Enhance contacts with LinkedIn data via BrightData

This service fetches LinkedIn profile data for contacts that have linkedin_url set,
and stores the enriched data in:
- linkedin_data (JSONB): Full structured profile data
- profile_content (TEXT): Human-readable summary for RAG indexing
- profile_enriched_at (TIMESTAMPTZ): When last enriched

Usage:
    # Enrich single contact
    python enrich_contacts.py --contact-id <uuid>
    
    # Enrich all contacts with LinkedIn URLs (not yet enriched)
    python enrich_contacts.py --all
    
    # Force re-enrich all
    python enrich_contacts.py --all --force

Rate Limits & Costs:
    - BrightData: ~$0.01-0.05 per LinkedIn profile scrape
    - Respects rate limits automatically
    - Skips already-enriched contacts unless --force
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ContactEnrichment")

# Database client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    """Get Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def get_linkedin_provider():
    """Get the LinkedIn BrightData provider."""
    try:
        from app.features.research.providers.linkedin import LinkedInProvider
        provider = LinkedInProvider()
        if not provider.is_configured:
            logger.warning("BrightData API key not configured. Set BRIGHTDATA_API_KEY")
            return None
        return provider
    except ImportError as e:
        logger.error(f"Failed to import LinkedIn provider: {e}")
        return None


def format_profile_content(profile_data: Dict[str, Any], contact_name: str) -> str:
    """
    Convert LinkedIn profile data to human-readable text for RAG indexing.
    
    This text will be indexed into knowledge_chunks for semantic search.
    """
    lines = [f"LinkedIn Profile: {contact_name}"]
    
    # Headline / Title
    if profile_data.get("headline"):
        lines.append(f"Headline: {profile_data['headline']}")
    
    # Current position
    if profile_data.get("current_company"):
        company = profile_data["current_company"]
        if isinstance(company, dict):
            lines.append(f"Current Company: {company.get('name', '')}")
        else:
            lines.append(f"Current Company: {company}")
    
    # Location
    if profile_data.get("location"):
        lines.append(f"Location: {profile_data['location']}")
    
    # About / Summary
    if profile_data.get("about") or profile_data.get("summary"):
        about = profile_data.get("about") or profile_data.get("summary")
        lines.append(f"\nAbout:\n{about}")
    
    # Experience
    experience = profile_data.get("experience") or profile_data.get("positions") or []
    if experience:
        lines.append("\nExperience:")
        for exp in experience[:5]:  # Limit to 5 most recent
            if isinstance(exp, dict):
                title = exp.get("title", "")
                company = exp.get("company_name") or exp.get("company", "")
                duration = exp.get("duration", "")
                lines.append(f"- {title} at {company} ({duration})")
    
    # Education
    education = profile_data.get("education") or []
    if education:
        lines.append("\nEducation:")
        for edu in education[:3]:
            if isinstance(edu, dict):
                school = edu.get("school_name") or edu.get("school", "")
                degree = edu.get("degree_name") or edu.get("degree", "")
                field = edu.get("field_of_study", "")
                lines.append(f"- {school}: {degree} {field}".strip())
    
    # Skills
    skills = profile_data.get("skills") or []
    if skills:
        if isinstance(skills[0], dict):
            skill_names = [s.get("name", "") for s in skills[:10]]
        else:
            skill_names = skills[:10]
        lines.append(f"\nSkills: {', '.join(skill_names)}")
    
    # Languages
    languages = profile_data.get("languages") or []
    if languages:
        if isinstance(languages[0], dict):
            lang_names = [l.get("name", "") for l in languages]
        else:
            lang_names = languages
        lines.append(f"Languages: {', '.join(lang_names)}")
    
    # Connections
    if profile_data.get("connections_count"):
        lines.append(f"Connections: {profile_data['connections_count']}")
    
    return "\n".join(lines)


async def enrich_contact(contact: Dict[str, Any], provider, db) -> Dict[str, Any]:
    """
    Enrich a single contact with LinkedIn data.
    
    Returns:
        Dict with status and enrichment results
    """
    contact_id = contact["id"]
    linkedin_url = contact.get("linkedin_url")
    name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    
    if not linkedin_url:
        return {
            "contact_id": contact_id,
            "name": name,
            "status": "skipped",
            "reason": "No LinkedIn URL"
        }
    
    logger.info(f"Enriching: {name} - {linkedin_url}")
    
    try:
        # Fetch profile from BrightData
        result = await provider._get_profile({"url": linkedin_url})
        
        if result.status.value != "success":
            return {
                "contact_id": contact_id,
                "name": name,
                "status": "error",
                "error": result.error or "Unknown error"
            }
        
        # Extract profile data
        profiles = result.data if isinstance(result.data, list) else [result.data]
        if not profiles:
            return {
                "contact_id": contact_id,
                "name": name,
                "status": "error",
                "error": "No profile data returned"
            }
        
        profile_data = profiles[0]
        
        # Skip error responses
        if profile_data.get("error") or not profile_data.get("name"):
            return {
                "contact_id": contact_id,
                "name": name,
                "status": "error",
                "error": profile_data.get("error", "Invalid profile data")
            }
        
        # Format content for RAG
        profile_content = format_profile_content(profile_data, name)
        
        # Update contact in database
        update_data = {
            "linkedin_data": profile_data,
            "profile_content": profile_content,
            "profile_enriched_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Optionally update job title and company if not set
        if not contact.get("job_title") and profile_data.get("headline"):
            update_data["job_title"] = profile_data["headline"][:200]  # Truncate
        
        current_company = profile_data.get("current_company")
        if not contact.get("company") and current_company:
            if isinstance(current_company, dict):
                update_data["company"] = current_company.get("name", "")[:200]
            else:
                update_data["company"] = str(current_company)[:200]
        
        db.table("contacts").update(update_data).eq("id", contact_id).execute()
        
        logger.info(f"✓ Enriched: {name}")
        
        return {
            "contact_id": contact_id,
            "name": name,
            "status": "success",
            "profile_content_length": len(profile_content),
            "headline": profile_data.get("headline"),
            "company": update_data.get("company")
        }
        
    except Exception as e:
        logger.error(f"Error enriching {name}: {e}")
        return {
            "contact_id": contact_id,
            "name": name,
            "status": "error",
            "error": str(e)
        }


async def enrich_contacts(
    contact_ids: List[str] = None,
    all_with_linkedin: bool = False,
    force: bool = False,
    limit: int = None
) -> Dict[str, Any]:
    """
    Enrich contacts with LinkedIn data.
    
    Args:
        contact_ids: Specific contact IDs to enrich
        all_with_linkedin: Enrich all contacts that have linkedin_url
        force: Re-enrich even if already enriched
        limit: Max number of contacts to process
    
    Returns:
        Summary of enrichment results
    """
    db = get_supabase()
    provider = await get_linkedin_provider()
    
    if not provider:
        return {
            "status": "error",
            "error": "LinkedIn provider not available. Check BRIGHTDATA_API_KEY"
        }
    
    # Build query
    query = db.table("contacts").select("*")
    
    if contact_ids:
        query = query.in_("id", contact_ids)
    elif all_with_linkedin:
        query = query.not_.is_("linkedin_url", "null")
        if not force:
            # Skip already enriched
            query = query.is_("profile_enriched_at", "null")
    else:
        return {
            "status": "error",
            "error": "Must specify contact_ids or --all"
        }
    
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    contacts = result.data or []
    
    logger.info(f"Found {len(contacts)} contacts to enrich")
    
    if not contacts:
        return {
            "status": "success",
            "message": "No contacts to enrich",
            "total": 0
        }
    
    # Process contacts (with small delay between to respect rate limits)
    results = {
        "success": [],
        "skipped": [],
        "errors": []
    }
    
    for i, contact in enumerate(contacts):
        if i > 0:
            await asyncio.sleep(1)  # Rate limit buffer
        
        enrichment_result = await enrich_contact(contact, provider, db)
        
        status = enrichment_result["status"]
        if status == "success":
            results["success"].append(enrichment_result)
        elif status == "skipped":
            results["skipped"].append(enrichment_result)
        else:
            results["errors"].append(enrichment_result)
    
    return {
        "status": "success",
        "total": len(contacts),
        "enriched": len(results["success"]),
        "skipped": len(results["skipped"]),
        "errors": len(results["errors"]),
        "details": results
    }


async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich contacts with LinkedIn data")
    parser.add_argument("--contact-id", type=str, help="Specific contact ID to enrich")
    parser.add_argument("--all", action="store_true", help="Enrich all contacts with LinkedIn URLs")
    parser.add_argument("--force", action="store_true", help="Re-enrich even if already done")
    parser.add_argument("--limit", type=int, help="Max contacts to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    
    args = parser.parse_args()
    
    if args.dry_run:
        db = get_supabase()
        query = db.table("contacts").select("id, first_name, last_name, linkedin_url, profile_enriched_at")
        
        if args.contact_id:
            query = query.eq("id", args.contact_id)
        elif args.all:
            query = query.not_.is_("linkedin_url", "null")
            if not args.force:
                query = query.is_("profile_enriched_at", "null")
        
        if args.limit:
            query = query.limit(args.limit)
        
        result = query.execute()
        
        print(f"\n{'='*60}")
        print(f"DRY RUN - Would enrich {len(result.data)} contacts:")
        print(f"{'='*60}")
        
        for c in result.data:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            url = c.get('linkedin_url', 'N/A') or 'N/A'
            enriched = c.get('profile_enriched_at', 'Never')
            # Handle unicode safely for Windows console
            try:
                safe_name = name.encode('ascii', 'replace').decode()
                safe_url = url.encode('ascii', 'replace').decode() if url else 'N/A'
                print(f"  - {safe_name}: {safe_url} (last: {enriched})")
            except Exception:
                print(f"  - [unicode name]: {url[:50] if url else 'N/A'}... (last: {enriched})")
        
        return
    
    if not args.contact_id and not args.all:
        parser.print_help()
        print("\nError: Must specify --contact-id or --all")
        return
    
    contact_ids = [args.contact_id] if args.contact_id else None
    
    result = await enrich_contacts(
        contact_ids=contact_ids,
        all_with_linkedin=args.all,
        force=args.force,
        limit=args.limit
    )
    
    print(f"\n{'='*60}")
    print("Contact Enrichment Complete")
    print(f"{'='*60}")
    print(f"Total processed: {result.get('total', 0)}")
    print(f"Successfully enriched: {result.get('enriched', 0)}")
    print(f"Skipped: {result.get('skipped', 0)}")
    print(f"Errors: {result.get('errors', 0)}")
    
    if result.get("details", {}).get("errors"):
        print("\nErrors:")
        for err in result["details"]["errors"][:5]:
            print(f"  - {err.get('name')}: {err.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
