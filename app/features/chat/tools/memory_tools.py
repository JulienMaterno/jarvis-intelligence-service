"""
Memory Tools for Chat.

This module contains tools for memory operations including remembering facts,
behaviors, searching memories, and forgetting/correcting memories.
"""

import logging
from typing import Dict, List, Any, Optional

from .base import _run_async, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

MEMORY_TOOLS = [
    {
        "name": "remember_fact",
        "description": """Remember a fact or piece of information for future reference.
Use when user shares information you should remember, like preferences, important dates, or personal details.

Examples:
- "My birthday is January 15th"
- "I prefer dark mode"
- "My sister's name is Sarah"
- "I'm allergic to shellfish" """,
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact or information to remember"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about when/why this is relevant"
                }
            },
            "required": ["fact"]
        }
    },
    {
        "name": "remember_behavior",
        "description": """Learn a new behavior rule or preference for how you should act.
Use when user tells you how they want you to behave or respond.

Examples:
- "Always summarize long emails before asking what to do"
- "Never schedule meetings before 10am"
- "Remind me of upcoming deadlines at the start of each day"
- "Be more concise in your responses" """,
        "input_schema": {
            "type": "object",
            "properties": {
                "behavior": {
                    "type": "string",
                    "description": "The behavior rule or preference"
                },
                "context": {
                    "type": "string",
                    "description": "When this behavior should apply"
                }
            },
            "required": ["behavior"]
        }
    },
    {
        "name": "search_memories",
        "description": """Search through stored memories (facts and behaviors).
Use when you need to recall what you know about a topic.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "type": {
                    "type": "string",
                    "enum": ["fact", "behavior"],
                    "description": "Filter by memory type (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "correct_memory",
        "description": """Correct an existing memory by replacing incorrect information with correct information.
Use when user says something you remembered is wrong.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "incorrect_info": {
                    "type": "string",
                    "description": "The incorrect information to find and remove"
                },
                "correct_info": {
                    "type": "string",
                    "description": "The correct information to store"
                }
            },
            "required": ["incorrect_info", "correct_info"]
        }
    },
    {
        "name": "forget_memory",
        "description": """Delete a memory by ID or search query.
Use when user asks you to forget something.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "Specific memory ID to delete"
                },
                "query": {
                    "type": "string",
                    "description": "Or search query to find and delete matching memories"
                }
            },
            "required": []
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _remember_fact(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Remember a fact or piece of information."""
    from app.features.memory import get_memory_service, MemoryType

    fact = tool_input.get("fact", "").strip()
    context = tool_input.get("context", "").strip()

    if not fact:
        return {"error": "No fact provided to remember"}

    try:
        memory_service = get_memory_service()

        # Add the memory
        result = _run_async(
            memory_service.add(
                content=fact,
                memory_type=MemoryType.FACT,
                metadata={
                    "source": "chat_remember",
                    "context": context or None
                }
            )
        )

        # Handle different result types
        if isinstance(result, dict):
            status = result.get("status", "unknown")
            event = result.get("event", "UNKNOWN")
            memory_id = result.get("id")

            if status == "success":
                return {
                    "status": "remembered",
                    "memory_id": memory_id,
                    "event": event,
                    "fact": fact,
                    "context": context or None,
                    "message": f"Remembered: '{fact}'"
                }
            elif status == "deduplicated":
                return {
                    "status": "already_known",
                    "fact": fact,
                    "message": f"I already know this: '{fact}'"
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Failed to remember: {status}",
                    "fact": fact
                }
        elif result:  # Legacy: string memory_id returned
            return {
                "status": "remembered",
                "memory_id": result,
                "fact": fact,
                "message": f"Remembered: '{fact}'"
            }
        else:
            return {
                "status": "failed",
                "error": "Failed to store memory - no result returned",
                "fact": fact
            }

    except Exception as e:
        logger.error(f"Failed to remember fact: {e}")
        return {
            "status": "error",
            "error": f"Failed to remember: {str(e)}",
            "fact": fact
        }


def _remember_behavior(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Learn a new behavior rule or preference."""
    from app.features.memory import get_memory_service, MemoryType

    behavior = tool_input.get("behavior", "").strip()
    context = tool_input.get("context", "").strip()

    if not behavior:
        return {"error": "No behavior rule provided to learn"}

    try:
        memory_service = get_memory_service()

        result = _run_async(
            memory_service.add(
                content=behavior,
                memory_type=MemoryType.BEHAVIOR,
                metadata={
                    "source": "chat_learn_behavior",
                    "context": context or None
                }
            )
        )

        # Handle different result types
        if isinstance(result, dict):
            status = result.get("status", "unknown")
            event = result.get("event", "UNKNOWN")
            memory_id = result.get("id")

            if status == "success":
                return {
                    "status": "learned",
                    "memory_id": memory_id,
                    "event": event,
                    "behavior": behavior,
                    "context": context or None,
                    "message": f"Behavior learned: '{behavior}'"
                }
            elif status == "deduplicated":
                return {
                    "status": "already_known",
                    "behavior": behavior,
                    "message": f"Similar behavior rule already exists: '{behavior}'"
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Failed to learn behavior: {status}",
                    "behavior": behavior
                }
        elif result:
            return {
                "status": "learned",
                "memory_id": result,
                "behavior": behavior,
                "message": f"Behavior learned: '{behavior}'"
            }
        else:
            return {
                "status": "failed",
                "error": "Failed to store behavior - no result returned",
                "behavior": behavior
            }

    except Exception as e:
        logger.error(f"Failed to remember behavior: {e}")
        return {
            "status": "error",
            "error": f"Failed to learn behavior: {str(e)}",
            "behavior": behavior
        }


def _correct_memory(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Correct an existing memory by deleting old and adding new."""
    from app.features.memory import get_memory_service, MemoryType

    incorrect_info = tool_input.get("incorrect_info", "").strip()
    correct_info = tool_input.get("correct_info", "").strip()

    if not incorrect_info or not correct_info:
        return {"error": "Need both incorrect_info and correct_info"}

    try:
        memory_service = get_memory_service()

        # Search for memories matching the incorrect info
        memories = _run_async(memory_service.search(incorrect_info, limit=5))

        if not memories:
            # No existing memory found, just add the correct one
            memory_id = _run_async(
                memory_service.add(
                    content=correct_info,
                    memory_type=MemoryType.FACT,
                    metadata={"source": "chat_correction", "corrected_from": incorrect_info}
                )
            )
            return {
                "status": "added_new",
                "message": f"No existing memory found with '{incorrect_info}'. Created new memory: '{correct_info}'",
                "new_memory_id": memory_id
            }

        # Delete old memories matching the incorrect info
        deleted_count = 0
        deleted_items = []
        for mem in memories:
            mem_id = mem.get("id")
            mem_text = mem.get("memory", "") or mem.get("data", "")
            if mem_id and incorrect_info.lower() in mem_text.lower():
                success = _run_async(memory_service.delete(mem_id))
                if success:
                    deleted_count += 1
                    deleted_items.append({"id": mem_id, "content": mem_text[:80]})

        # Add the correct memory
        new_id = _run_async(
            memory_service.add(
                content=correct_info,
                memory_type=MemoryType.FACT,
                metadata={"source": "chat_correction", "corrected_from": incorrect_info}
            )
        )

        return {
            "status": "corrected",
            "deleted_count": deleted_count,
            "deleted_items": deleted_items,
            "new_memory_id": new_id,
            "new_content": correct_info,
            "message": f"Corrected! Deleted {deleted_count} old memory/memories and added: '{correct_info}'"
        }

    except Exception as e:
        logger.error(f"Failed to correct memory: {e}")
        return {"error": f"Failed to correct: {str(e)}"}


def _search_memories(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search stored memories."""
    from app.features.memory import get_memory_service

    query = tool_input.get("query", "").strip()
    limit = tool_input.get("limit", 10)
    memory_type = tool_input.get("type")

    if not query:
        return {"error": "No search query provided"}

    try:
        memory_service = get_memory_service()

        memories = _run_async(memory_service.search(query, limit=limit))

        if not memories:
            return {
                "status": "no_results",
                "message": f"I don't have any memories about '{query}'",
                "memories": []
            }

        # Format memories with FULL metadata for display
        formatted = []
        for mem in memories:
            metadata = mem.get("metadata") or {}
            payload = mem.get("payload") or {}

            if not isinstance(metadata, dict):
                metadata = {}
            if not isinstance(payload, dict):
                payload = {}

            mem_type = metadata.get("type") or payload.get("type") or "fact"
            source = metadata.get("source") or payload.get("source") or "unknown"
            created_at = metadata.get("created_at") or payload.get("created_at") or metadata.get("added_at") or payload.get("added_at")

            formatted.append({
                "id": mem.get("id", ""),
                "content": mem.get("memory", "") or mem.get("data", "") or payload.get("data", ""),
                "type": mem_type,
                "source": source,
                "created_at": created_at,
            })

        # Optionally filter by type if specified
        if memory_type:
            formatted = [m for m in formatted if m["type"] == memory_type]

        return {
            "status": "found",
            "count": len(formatted),
            "memories": formatted,
            "message": f"Found {len(formatted)} memories about '{query}'"
        }

    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        return {"error": f"Failed to search: {str(e)}"}


def _forget_memory(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a memory by ID or search query."""
    from app.features.memory import get_memory_service

    memory_id = tool_input.get("memory_id", "").strip()
    query = tool_input.get("query", "").strip()

    if not memory_id and not query:
        return {"error": "Provide either memory_id or query to specify what to forget"}

    try:
        memory_service = get_memory_service()

        # If specific ID provided, delete directly
        if memory_id:
            success = _run_async(memory_service.delete(memory_id))
            if success:
                return {
                    "status": "deleted",
                    "deleted_id": memory_id,
                    "message": f"Deleted memory with ID: {memory_id}"
                }
            else:
                return {
                    "status": "FAILED",
                    "error": f"DELETION FAILED for memory {memory_id} - may not exist or deletion error",
                    "message": f"FAILED to delete memory {memory_id}"
                }

        # Otherwise search and delete matching memories
        memories = _run_async(memory_service.search(query, limit=10))

        if not memories:
            return {
                "status": "FAILED",
                "error": f"NO MEMORIES FOUND matching '{query}' - nothing was deleted!",
                "message": f"FAILED: No memories found matching '{query}'"
            }

        # Show what was found and delete matches
        deleted_items = []
        failed_items = []

        for mem in memories:
            mem_id = mem.get("id")
            mem_text = mem.get("memory", "") or mem.get("data", "")

            # Only delete if query appears in the memory text (case-insensitive)
            if mem_id and query.lower() in mem_text.lower():
                success = _run_async(memory_service.delete(mem_id))
                if success:
                    deleted_items.append({
                        "id": mem_id,
                        "content": mem_text[:100]
                    })
                else:
                    failed_items.append(mem_id)

        if not deleted_items and not failed_items:
            found_previews = [f"- {m.get('memory', m.get('data', ''))[:60]}..." for m in memories[:5]]
            return {
                "status": "FAILED",
                "error": f"DELETION FAILED: Found {len(memories)} memories but query '{query}' didn't match any exactly.",
                "found_count": len(memories),
                "found_previews": found_previews,
                "message": f"FAILED to delete! Query '{query}' found {len(memories)} memories but none contained that exact text. You MUST use the exact memory ID to delete. Here are the memories found:\n" + "\n".join(found_previews)
            }

        return {
            "status": "deleted" if deleted_items else "FAILED",
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
            "failed_count": len(failed_items),
            "message": f"Deleted {len(deleted_items)} memory/memories" if deleted_items else "FAILED to delete any memories"
        }

    except Exception as e:
        logger.error(f"Failed to forget memory: {e}")
        return {"error": f"Failed to forget: {str(e)}"}
