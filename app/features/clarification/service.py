"""
Clarification Service - Handle follow-up questions from AI analysis.

When the AI can't resolve something (e.g., who is "Other Person"), this service:
1. Checks the DB first (contacts, memories, calendar)
2. If not found, asks the user via Telegram
3. Stores the answer as a memory for future reference
4. Optionally updates the original record

Flow:
1. Analysis produces `clarifications_needed` list
2. handle_clarifications() is called
3. For each clarification:
   a. Try to resolve from DB
   b. If resolved, update the record
   c. If not resolved, send Telegram question
4. User responds via Telegram
5. store_clarification_answer() saves answer and updates record
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger("Jarvis.Clarification")


async def handle_clarifications(
    clarifications: List[Dict[str, Any]],
    record_type: str,
    record_id: str,
    transcript_id: str,
    db,
    user_id: int = None,
    chat_id: int = None,
) -> Dict[str, Any]:
    """
    Process clarifications from AI analysis.
    
    Args:
        clarifications: List of {item, question, context} dicts
        record_type: 'meeting', 'reflection', etc.
        record_id: UUID of the record needing clarification
        transcript_id: UUID of the source transcript
        db: Database client
        user_id: Telegram user ID (for sending questions)
        chat_id: Telegram chat ID
    
    Returns:
        Dict with:
        - resolved: List of clarifications resolved from DB
        - pending: List of clarifications sent to user
        - failed: List of clarifications that couldn't be processed
    """
    from app.features.telegram.notifications import send_clarification_question
    from app.features.memory.service import get_memory_service
    
    results = {
        "resolved": [],
        "pending": [],
        "failed": []
    }
    
    memory_service = get_memory_service()
    
    for clarification in clarifications:
        item = clarification.get("item", "Unknown")
        question = clarification.get("question", "")
        context = clarification.get("context", "")
        
        logger.info(f"Processing clarification: {item}")
        
        # Step 1: Try to resolve from existing knowledge
        resolution = await try_resolve_from_knowledge(
            item=item,
            context=context,
            db=db,
            memory_service=memory_service
        )
        
        if resolution:
            logger.info(f"Resolved '{item}' from DB: {resolution}")
            results["resolved"].append({
                "item": item,
                "answer": resolution,
                "source": "database"
            })
            
            # Update the record with the resolved info
            await update_record_with_clarification(
                record_type=record_type,
                record_id=record_id,
                item=item,
                answer=resolution,
                db=db
            )
        else:
            # Step 2: Ask user via Telegram
            if user_id and chat_id:
                # Store pending clarification
                pending_id = await store_pending_clarification(
                    user_id=user_id,
                    chat_id=chat_id,
                    item=item,
                    question=question,
                    context={"original_context": context, "transcript_id": transcript_id},
                    record_type=record_type,
                    record_id=record_id,
                    transcript_id=transcript_id,
                    db=db
                )
                
                if pending_id:
                    # Send question to user via /set_pending_clarification endpoint
                    # This sets the bot to expect the user's reply
                    sent = await send_clarification_question(
                        clarification_id=pending_id,
                        user_id=user_id,
                        chat_id=chat_id,
                        item=item,
                        question=question
                    )
                    
                    if sent:
                        results["pending"].append({
                            "item": item,
                            "question": question,
                            "pending_id": pending_id
                        })
                        logger.info(f"Sent clarification question to user: {item}")
                    else:
                        results["failed"].append({
                            "item": item,
                            "reason": "Failed to send Telegram clarification"
                        })
                else:
                    results["failed"].append({
                        "item": item,
                        "reason": "Failed to store pending clarification"
                    })
            else:
                logger.warning(f"No user_id/chat_id for clarification: {item}")
                results["failed"].append({
                    "item": item,
                    "reason": "No user credentials for Telegram"
                })
    
    return results


async def try_resolve_from_knowledge(
    item: str,
    context: str,
    db,
    memory_service
) -> Optional[str]:
    """
    Try to resolve a clarification from existing knowledge.
    
    Searches:
    1. Contacts database (for person names)
    2. Memories (for facts about people/things)
    3. Calendar events (for meeting context)
    
    Returns the answer if found, None otherwise.
    """
    item_lower = item.lower()
    
    # Check if this is about a person's identity
    if "identity" in item_lower or "person" in item_lower or "who" in item_lower:
        # Search contacts
        # Extract potential name from context
        if context:
            # Try to find contacts matching context
            contacts = db.search_contacts_simple(context[:100])
            if contacts:
                # Return the most likely match
                best = contacts[0]
                name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()
                company = best.get('company', '')
                if company:
                    return f"{name} ({company})"
                return name
    
    # Check memories for relevant facts
    if memory_service:
        try:
            # Search memories for this item
            memories = await memory_service.search_async(f"{item} {context}"[:200], limit=3)
            if memories:
                # Check if any memory answers the question
                for mem in memories:
                    memory_text = mem.get("memory", "")
                    if item_lower in memory_text.lower():
                        return memory_text
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
    
    return None


async def store_pending_clarification(
    user_id: int,
    chat_id: int,
    item: str,
    question: str,
    context: Dict[str, Any],
    record_type: str,
    record_id: str,
    transcript_id: str,
    db
) -> Optional[str]:
    """
    Store a pending clarification in the database.
    
    Returns the clarification ID if successful, None otherwise.
    """
    try:
        result = db.client.table("pending_clarifications").insert({
            "user_id": user_id,
            "chat_id": chat_id,
            "item": item,
            "question": question,
            "context": context,
            "record_type": record_type,
            "record_id": record_id,
            "source_transcript_id": transcript_id,
            "status": "pending"
        }).execute()
        
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.error(f"Failed to store pending clarification: {e}")
    
    return None


async def get_pending_clarifications(user_id: int, db) -> List[Dict[str, Any]]:
    """Get all pending clarifications for a user."""
    try:
        result = db.client.table("pending_clarifications").select("*").eq(
            "user_id", user_id
        ).eq(
            "status", "pending"
        ).order("created_at", desc=False).execute()
        
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to get pending clarifications: {e}")
        return []


async def resolve_clarification(
    clarification_id: str,
    answer: str,
    db,
    memory_service=None
) -> bool:
    """
    Resolve a pending clarification with the user's answer.
    
    1. Updates the clarification record
    2. Updates the original record (meeting, etc.)
    3. Stores the answer as a memory for future reference
    """
    try:
        # Get the clarification details
        result = db.client.table("pending_clarifications").select("*").eq(
            "id", clarification_id
        ).execute()
        
        if not result.data:
            logger.error(f"Clarification not found: {clarification_id}")
            return False
        
        clarification = result.data[0]
        item = clarification.get("item", "")
        record_type = clarification.get("record_type")
        record_id = clarification.get("record_id")
        
        # 1. Update the clarification record
        db.client.table("pending_clarifications").update({
            "status": "resolved",
            "answer": answer,
            "resolved_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", clarification_id).execute()
        
        # 2. Update the original record
        if record_type and record_id:
            await update_record_with_clarification(
                record_type=record_type,
                record_id=record_id,
                item=item,
                answer=answer,
                db=db
            )
        
        # 3. Store as memory for future reference
        if memory_service:
            memory_text = f"{item}: {answer}"
            try:
                await memory_service.add_async(
                    memory_text,
                    metadata={
                        "type": "clarification_answer",
                        "item": item,
                        "source": "user_response"
                    }
                )
                logger.info(f"Stored clarification answer as memory: {item}")
            except Exception as e:
                logger.warning(f"Failed to store memory: {e}")
        
        logger.info(f"Resolved clarification {clarification_id}: {item} = {answer}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to resolve clarification: {e}")
        return False


async def update_record_with_clarification(
    record_type: str,
    record_id: str,
    item: str,
    answer: str,
    db
):
    """
    Update the original record with clarified information.
    
    This updates different fields based on what was clarified:
    - Person identity -> updates contact_name, tries to link contact
    - Program/org name -> updates notes/metadata
    """
    try:
        item_lower = item.lower()
        
        if record_type == "meeting":
            if "identity" in item_lower or "person" in item_lower:
                # Try to find and link the contact
                contacts = db.search_contacts_simple(answer)
                if contacts:
                    # Link to the contact
                    contact = contacts[0]
                    db.client.table("meetings").update({
                        "contact_id": contact["id"],
                        "contact_name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                    }).eq("id", record_id).execute()
                    logger.info(f"Linked meeting {record_id} to contact {contact['id']}")
                else:
                    # Just update the name
                    db.client.table("meetings").update({
                        "contact_name": answer
                    }).eq("id", record_id).execute()
            else:
                # Update notes/summary with the clarification
                current = db.client.table("meetings").select("notes").eq("id", record_id).execute()
                existing_notes = current.data[0].get("notes", "") if current.data else ""
                new_notes = f"{existing_notes}\n\n[Clarification: {item}]: {answer}".strip()
                db.client.table("meetings").update({
                    "notes": new_notes
                }).eq("id", record_id).execute()
        
        elif record_type == "reflection":
            # Add clarification to reflection content
            current = db.client.table("reflections").select("content").eq("id", record_id).execute()
            existing = current.data[0].get("content", "") if current.data else ""
            new_content = f"{existing}\n\n---\n[Clarified: {item}]: {answer}"
            db.client.table("reflections").update({
                "content": new_content
            }).eq("id", record_id).execute()
        
        logger.info(f"Updated {record_type} {record_id} with clarification: {item}")
        
    except Exception as e:
        logger.error(f"Failed to update record with clarification: {e}")
