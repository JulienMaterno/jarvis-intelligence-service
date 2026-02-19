"""
Chat Tools Package.

This package provides all tools available to the Claude chat interface.
Tools are organized by domain into separate modules for maintainability.

Usage:
    from app.features.chat.tools import TOOLS, execute_tool, get_all_tools

Modules:
    - database_tools: SQL queries, writes, schema management, backups
    - calendar_tools: Calendar events, scheduling, invitations
    - email_tools: Email reading, drafts, sending
    - contact_tools: CRM contacts, history, notes
    - meeting_tools: Meeting records, search, creation
    - task_tools: Tasks/to-dos, completion, updates
    - sync_tools: Data synchronization triggers
    - messaging_tools: Beeper messaging (WhatsApp, LinkedIn, etc.)
    - knowledge_tools: Knowledge base, semantic search, documents
    - memory_tools: Memory management (facts, behaviors)
    - misc_tools: Location, books, transcripts, applications, LinkedIn posts
"""

import logging
from typing import Dict, List, Any

# Base utilities
from .base import (
    USE_MCP_DELEGATION,
    MCP_DELEGATED_TOOLS,
    _get_mcp_client,
    _get_identity_token,
    _get_sync_service_headers,
    _get_sync_service_url,
    _sanitize_ilike,
    _run_async,
    _handle_research_tool,
    logger,
)

# Tool definitions from each module
from .database_tools import DATABASE_TOOLS
from .calendar_tools import CALENDAR_TOOLS
from .email_tools import EMAIL_TOOLS
from .contact_tools import CONTACT_TOOLS
from .meeting_tools import MEETING_TOOLS
from .task_tools import TASK_TOOLS
from .sync_tools import SYNC_TOOLS
from .messaging_tools import MESSAGING_TOOLS
from .knowledge_tools import KNOWLEDGE_TOOLS
from .memory_tools import MEMORY_TOOLS
from .misc_tools import MISC_TOOLS
from .books_tools import BOOKS_PIPELINE_TOOLS

# Tool implementations from each module
from .database_tools import (
    _execute_sql_write, _update_record, _query_database,
    _list_database_tables, _create_database_table, _add_column_to_table,
    _update_data_batch, _insert_data_batch,
    _get_database_backup_status, _backup_table,
)
from .calendar_tools import (
    _get_upcoming_events, _create_calendar_event,
    _update_calendar_event, _decline_calendar_event,
)
from .email_tools import (
    _get_recent_emails, _get_email_by_id, _search_emails_live,
    _create_email_draft, _list_email_drafts, _get_email_draft,
    _send_email_draft, _delete_email_draft,
)
from .contact_tools import (
    _search_contacts, _get_contact_history, _create_contact,
    _update_contact, _add_contact_note, _who_to_contact,
)
from .meeting_tools import (
    _search_meetings, _create_meeting,
)
from .task_tools import (
    _get_tasks, _create_task, _update_task, _complete_task, _delete_task,
)
from .sync_tools import (
    _quick_sync,
)
from .messaging_tools import (
    _get_beeper_inbox, _get_beeper_chat_messages, _search_beeper_messages,
    _get_beeper_contact_messages, _archive_beeper_chat, _unarchive_beeper_chat,
    _send_beeper_message, _mark_beeper_read, _get_beeper_status,
)
from .knowledge_tools import (
    _query_knowledge, _search_documents, _get_document_content,
    _search_conversations, _get_reflections, _create_reflection, _get_journals,
)
from .memory_tools import (
    _remember_fact, _remember_behavior, _search_memories,
    _correct_memory, _forget_memory,
)
from .misc_tools import (
    _set_user_location, _get_user_location, _get_current_time,
    _get_books, _get_highlights, _search_reading_notes,
    _search_transcripts, _get_full_transcript, _get_recent_voice_memo,
    _summarize_activity,
    _get_applications, _search_applications, _get_application_content, _update_application,
    _get_linkedin_posts, _search_linkedin_posts, _get_linkedin_post_content,
)
from .books_tools import (
    _create_summary_book, _get_summary_book_status, _list_summary_book_projects,
)


# =============================================================================
# COMBINED TOOLS LIST
# =============================================================================

# All tool definitions combined
TOOLS = (
    DATABASE_TOOLS +
    CALENDAR_TOOLS +
    EMAIL_TOOLS +
    CONTACT_TOOLS +
    MEETING_TOOLS +
    TASK_TOOLS +
    SYNC_TOOLS +
    MESSAGING_TOOLS +
    KNOWLEDGE_TOOLS +
    MEMORY_TOOLS +
    MISC_TOOLS +
    BOOKS_PIPELINE_TOOLS
)


def get_all_tools() -> List[Dict[str, Any]]:
    """Get all tools including dynamically loaded research tools."""
    from app.features.research import RESEARCH_TOOLS
    return TOOLS + RESEARCH_TOOLS


# =============================================================================
# TOOL EXECUTION
# =============================================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any], last_user_message: str = "") -> Dict[str, Any]:
    """Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool parameters
        last_user_message: The most recent user message (for confirmation checks)

    MCP Delegation:
        When USE_MCP_DELEGATION=true, mapped tools delegate to jarvis-mcp-server.
        Falls back to local implementation if MCP call fails.
    """
    import asyncio
    import concurrent.futures

    # Try MCP delegation first if enabled
    if USE_MCP_DELEGATION and tool_name in MCP_DELEGATED_TOOLS:
        mcp = _get_mcp_client()
        if mcp:
            mcp_tool = MCP_DELEGATED_TOOLS[tool_name]
            try:
                # Run async MCP call in sync context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(
                            asyncio.run,
                            mcp.execute_tool(mcp_tool, tool_input)
                        ).result(timeout=30)
                else:
                    result = asyncio.run(mcp.execute_tool(mcp_tool, tool_input))

                if result.get("ok"):
                    logger.debug(f"Tool {tool_name} delegated to MCP successfully")
                    return {
                        "success": True,
                        "data": result.get("data"),
                        "source": "mcp",
                    }
                else:
                    logger.warning(f"MCP tool {tool_name} failed, falling back to local: {result.get('error')}")
            except Exception as e:
                logger.warning(f"MCP delegation failed for {tool_name}, falling back to local: {e}")

    # Local implementation (fallback or non-delegated tools)
    try:
        # Database tools
        if tool_name == "execute_sql_write":
            return _execute_sql_write(tool_input)
        elif tool_name == "update_record":
            return _update_record(tool_input)
        elif tool_name == "query_database":
            return _query_database(tool_input.get("sql", ""))
        elif tool_name == "list_database_tables":
            return _list_database_tables(tool_input)
        elif tool_name == "create_database_table":
            return _create_database_table(tool_input)
        elif tool_name == "add_column_to_table":
            return _add_column_to_table(tool_input)
        elif tool_name == "update_data_batch":
            return _update_data_batch(tool_input)
        elif tool_name == "insert_data_batch":
            return _insert_data_batch(tool_input)
        elif tool_name == "get_database_backup_status":
            return _get_database_backup_status(tool_input)
        elif tool_name == "backup_table":
            return _backup_table(tool_input)

        # Knowledge tools
        elif tool_name == "query_knowledge":
            return _query_knowledge(
                tool_input.get("query", ""),
                tool_input.get("content_types"),
                tool_input.get("limit", 10)
            )
        elif tool_name == "search_documents":
            return _run_async(_search_documents(tool_input))
        elif tool_name == "get_document_content":
            return _run_async(_get_document_content(tool_input))
        elif tool_name == "search_conversations":
            return _run_async(_search_conversations(tool_input))
        elif tool_name == "get_reflections":
            return _get_reflections(tool_input)
        elif tool_name == "create_reflection":
            return _create_reflection(tool_input)
        elif tool_name == "get_journals":
            return _get_journals(tool_input)

        # Contact tools
        elif tool_name == "search_contacts":
            return _search_contacts(tool_input.get("query", ""), tool_input.get("limit", 5))
        elif tool_name == "get_contact_history":
            return _get_contact_history(tool_input.get("contact_name", ""))
        elif tool_name == "create_contact":
            return _create_contact(tool_input)
        elif tool_name == "update_contact":
            return _update_contact(tool_input)
        elif tool_name == "add_contact_note":
            return _add_contact_note(tool_input)
        elif tool_name == "who_to_contact":
            return _who_to_contact(tool_input)

        # Task tools
        elif tool_name == "get_tasks":
            return _get_tasks(tool_input.get("status", "pending"), tool_input.get("limit", 100))
        elif tool_name == "create_task":
            return _create_task(tool_input)
        elif tool_name == "update_task":
            return _update_task(tool_input)
        elif tool_name == "complete_task":
            return _complete_task(tool_input)
        elif tool_name == "delete_task":
            return _delete_task(tool_input)

        # Meeting tools
        elif tool_name == "search_meetings":
            return _search_meetings(tool_input)
        elif tool_name == "create_meeting":
            return _create_meeting(tool_input)

        # Calendar tools
        elif tool_name == "get_upcoming_events":
            return _get_upcoming_events(tool_input.get("days", 7))
        elif tool_name == "create_calendar_event":
            return _create_calendar_event(tool_input)
        elif tool_name == "update_calendar_event":
            return _update_calendar_event(tool_input)
        elif tool_name == "decline_calendar_event":
            return _decline_calendar_event(tool_input)

        # Email tools
        elif tool_name == "get_recent_emails":
            return _get_recent_emails(tool_input)
        elif tool_name == "get_email_by_id":
            return _get_email_by_id(tool_input)
        elif tool_name == "search_emails_live":
            return _search_emails_live(tool_input)
        elif tool_name == "create_email_draft":
            return _create_email_draft(tool_input)
        elif tool_name == "list_email_drafts":
            return _list_email_drafts(tool_input)
        elif tool_name == "get_email_draft":
            return _get_email_draft(tool_input)
        elif tool_name == "send_email_draft":
            return _send_email_draft(tool_input)
        elif tool_name == "delete_email_draft":
            return _delete_email_draft(tool_input)

        # Messaging tools (Beeper)
        elif tool_name == "get_beeper_inbox":
            return _get_beeper_inbox(tool_input)
        elif tool_name == "get_beeper_chat_messages":
            return _get_beeper_chat_messages(tool_input)
        elif tool_name == "search_beeper_messages":
            return _search_beeper_messages(tool_input)
        elif tool_name == "get_beeper_contact_messages":
            return _get_beeper_contact_messages(tool_input)
        elif tool_name == "archive_beeper_chat":
            return _archive_beeper_chat(tool_input)
        elif tool_name == "unarchive_beeper_chat":
            return _unarchive_beeper_chat(tool_input)
        elif tool_name == "send_beeper_message":
            logger.info(f"SEND_BEEPER_MESSAGE called with: {tool_input}")
            tool_input["_last_user_message"] = last_user_message
            result = _send_beeper_message(tool_input)
            logger.info(f"SEND_BEEPER_MESSAGE result: {result}")
            return result
        elif tool_name == "mark_beeper_read":
            return _mark_beeper_read(tool_input)
        elif tool_name == "get_beeper_status":
            return _get_beeper_status(tool_input)

        # Memory tools
        elif tool_name == "remember_fact":
            return _remember_fact(tool_input)
        elif tool_name == "remember_behavior":
            return _remember_behavior(tool_input)
        elif tool_name == "search_memories":
            return _search_memories(tool_input)
        elif tool_name == "correct_memory":
            return _correct_memory(tool_input)
        elif tool_name == "forget_memory":
            return _forget_memory(tool_input)

        # Sync tools
        elif tool_name == "quick_sync":
            return _quick_sync(tool_input)

        # Misc tools - Location & Timezone
        elif tool_name == "set_user_location":
            return _set_user_location(tool_input)
        elif tool_name == "get_user_location":
            return _get_user_location()
        elif tool_name == "get_current_time":
            return _get_current_time()

        # Misc tools - Books & Highlights
        elif tool_name == "get_books":
            return _get_books(tool_input)
        elif tool_name == "get_highlights":
            return _get_highlights(tool_input)
        elif tool_name == "search_reading_notes":
            return _search_reading_notes(tool_input)

        # Misc tools - Transcripts
        elif tool_name == "search_transcripts":
            return _search_transcripts(tool_input)
        elif tool_name == "get_full_transcript":
            return _get_full_transcript(tool_input)
        elif tool_name == "get_recent_voice_memo":
            return _get_recent_voice_memo(tool_input)

        # Misc tools - Activity
        elif tool_name == "summarize_activity":
            return _summarize_activity(tool_input.get("period", "today"))

        # Misc tools - Applications
        elif tool_name == "get_applications":
            return _get_applications(tool_input)
        elif tool_name == "search_applications":
            return _search_applications(tool_input)
        elif tool_name == "get_application_content":
            return _get_application_content(tool_input)
        elif tool_name == "update_application":
            return _update_application(tool_input)

        # Misc tools - LinkedIn Posts
        elif tool_name == "get_linkedin_posts":
            return _get_linkedin_posts(tool_input)
        elif tool_name == "search_linkedin_posts":
            return _search_linkedin_posts(tool_input)
        elif tool_name == "get_linkedin_post_content":
            return _get_linkedin_post_content(tool_input)

        # Books pipeline tools
        elif tool_name == "create_summary_book":
            return _create_summary_book(tool_input)
        elif tool_name == "get_summary_book_status":
            return _get_summary_book_status(tool_input)
        elif tool_name == "list_summary_book_projects":
            return _list_summary_book_projects(tool_input)

        # Research tools (LinkedIn via Bright Data, Web Search via Brave)
        elif tool_name in ("linkedin_get_profiles", "linkedin_search_people",
                          "linkedin_get_company", "linkedin_get_company_employees",
                          "linkedin_get_company_jobs", "web_search", "web_search_news",
                          "get_research_status"):
            return _run_async(_handle_research_tool(tool_name, tool_input))

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Tool execution error [{tool_name}]: {e}")
        return {"error": str(e)}


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Main exports
    "TOOLS",
    "execute_tool",
    "get_all_tools",

    # Base utilities (for advanced usage)
    "USE_MCP_DELEGATION",
    "MCP_DELEGATED_TOOLS",

    # Tool lists by category (for inspection)
    "DATABASE_TOOLS",
    "CALENDAR_TOOLS",
    "EMAIL_TOOLS",
    "CONTACT_TOOLS",
    "MEETING_TOOLS",
    "TASK_TOOLS",
    "SYNC_TOOLS",
    "MESSAGING_TOOLS",
    "KNOWLEDGE_TOOLS",
    "MEMORY_TOOLS",
    "MISC_TOOLS",
    "BOOKS_PIPELINE_TOOLS",

    # Internal functions (exported for service.py)
    "_get_user_location",
]
