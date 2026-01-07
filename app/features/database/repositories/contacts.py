"""
Contacts Repository - Contact data access operations.

Handles all contact-related database operations including:
- Finding contacts by name, email, or phone
- Fuzzy matching and suggestions
- Contact creation and updates
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Jarvis.Database.Contacts")


class ContactsRepository:
    """Repository for contact operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
    
    def find_by_name(self, name: str) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Find a contact by name using fuzzy matching.
        
        Returns:
            Tuple of (matched_contact, suggestions)
            - matched_contact: The contact dict if found with high confidence, None otherwise
            - suggestions: List of possible matches if no exact match
        """
        if not name:
            return None, []
        
        try:
            name_parts = name.strip().split()
            if not name_parts:
                return None, []
            
            first_name = name_parts[0].lower()
            last_name = name_parts[-1].lower() if len(name_parts) > 1 else None
            
            # Strategy 1: Exact full name match (case-insensitive)
            if last_name:
                result = self.client.table("contacts").select("*").ilike(
                    "first_name", first_name
                ).ilike(
                    "last_name", last_name
                ).is_("deleted_at", "null").execute()
                
                if result.data:
                    logger.info(f"Found contact by exact name: {name}")
                    return result.data[0], []
            
            # Strategy 2: First name only match
            result = self.client.table("contacts").select("*").ilike(
                "first_name", f"%{first_name}%"
            ).is_("deleted_at", "null").limit(10).execute()
            
            if len(result.data) == 1:
                contact = result.data[0]
                logger.info(f"Found unique contact by first name '{first_name}'")
                return contact, []
            elif len(result.data) > 1:
                logger.info(f"Multiple contacts match '{first_name}', returning as suggestions")
                return None, result.data[:5]
            
            # Strategy 3: Fuzzy search in both names
            result = self.client.table("contacts").select("*").or_(
                f"first_name.ilike.%{first_name}%,last_name.ilike.%{first_name}%"
            ).is_("deleted_at", "null").limit(5).execute()
            
            if result.data:
                logger.info(f"Found {len(result.data)} fuzzy matches for '{name}'")
                return None, result.data
            
            return None, []
            
        except Exception as e:
            logger.error(f"Error finding contact '{name}': {e}")
            return None, []
    
    def find_by_email(self, email: str) -> Optional[Dict]:
        """Find a contact by email address."""
        if not email:
            return None
        
        try:
            email_lower = email.lower().strip()
            
            result = self.client.table("contacts").select("*").ilike(
                "email", email_lower
            ).is_("deleted_at", "null").execute()
            
            if result.data:
                logger.info(f"Found contact by email: {email}")
                return result.data[0]
            
            # Check alternative emails
            result = self.client.table("contacts").select("*").contains(
                "alternative_emails", [email_lower]
            ).is_("deleted_at", "null").execute()
            
            if result.data:
                return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding contact by email '{email}': {e}")
            return None
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Search contacts by partial name match."""
        if not query or len(query) < 2:
            return []
        
        try:
            result = self.client.table("contacts").select(
                "id, first_name, last_name, company, job_title"
            ).or_(
                f"first_name.ilike.%{query}%,last_name.ilike.%{query}%"
            ).is_("deleted_at", "null").limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            return []
    
    def get_by_id(self, contact_id: str) -> Optional[Dict]:
        """Get a contact by ID."""
        try:
            result = self.client.table("contacts").select("*").eq(
                "id", contact_id
            ).is_("deleted_at", "null").execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting contact {contact_id}: {e}")
            return None
    
    def create(
        self,
        first_name: str,
        last_name: str = None,
        email: str = None,
        company: str = None,
        position: str = None,
        notes: str = None,
    ) -> Optional[str]:
        """
        Create a new contact.
        
        Returns:
            Contact ID if successful, None otherwise
        """
        try:
            payload = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "company": company,
                "position": position,
                "notes": notes,
                "last_sync_source": "supabase",
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            result = self.client.table("contacts").insert(payload).execute()
            contact_id = result.data[0]["id"]
            logger.info(f"Created contact: {first_name} {last_name or ''} ({contact_id})")
            return contact_id
            
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            return None
    
    def update(self, contact_id: str, updates: Dict) -> bool:
        """Update a contact."""
        try:
            updates["last_sync_source"] = "supabase"
            self.client.table("contacts").update(updates).eq("id", contact_id).execute()
            logger.info(f"Updated contact {contact_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating contact {contact_id}: {e}")
            return False
    
    def get_all(self, limit: int = 100) -> List[Dict]:
        """Get all contacts."""
        try:
            result = self.client.table("contacts").select("*").is_(
                "deleted_at", "null"
            ).order("first_name").limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting all contacts: {e}")
            return []
