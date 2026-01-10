"""
Chat Service - Conversational AI with Tool Use and Memory.

This module provides a Claude-powered conversational interface that can:
1. Answer questions about your data (meetings, contacts, tasks, etc.)
2. Create new records (tasks, reflections)
3. Search and retrieve information
4. Execute actions (complete tasks, etc.)
5. Remember context across conversations (via Mem0)
6. Track conversation history (via Letta + raw storage)

Works similarly to Claude Desktop + MCP, but via Telegram.
"""

import json
import logging
import os
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

import anthropic
from pydantic import BaseModel, Field

# Import config to ensure .env is loaded
from app.core.config import settings

from app.features.chat.tools import TOOLS, execute_tool
from app.features.memory import get_memory_service

# =============================================================================
# CONVERSATION-LEVEL MEMORY CACHE
# =============================================================================
# Cache memory context per conversation to avoid repeated embedding lookups.
# Memory is only searched ONCE when conversation starts (first message) or
# after significant time has passed (user returns later).
#
# This is similar to how Claude Desktop works - it loads context at start,
# not on every message.
# =============================================================================
_conversation_memory_cache: Dict[str, Tuple[float, str]] = {}
_CONVERSATION_CACHE_TTL = 1800.0  # 30 minutes - conversation context is valid for 30 min
_CONVERSATION_CACHE_MAX_SIZE = 100

def _get_cached_memory_context(conversation_id: str) -> Optional[str]:
    """Get cached memory context for a conversation if still valid."""
    if conversation_id in _conversation_memory_cache:
        cached_time, cached_context = _conversation_memory_cache[conversation_id]
        if time.time() - cached_time < _CONVERSATION_CACHE_TTL:
            return cached_context
    return None

def _set_cached_memory_context(conversation_id: str, context: str) -> None:
    """Cache memory context for a conversation."""
    global _conversation_memory_cache
    _conversation_memory_cache[conversation_id] = (time.time(), context)
    
    # Prune old entries if too large
    if len(_conversation_memory_cache) > _CONVERSATION_CACHE_MAX_SIZE:
        sorted_keys = sorted(_conversation_memory_cache.keys(), 
                            key=lambda k: _conversation_memory_cache[k][0])
        for old_key in sorted_keys[:len(sorted_keys) // 2]:
            del _conversation_memory_cache[old_key]
# =============================================================================

# Cost tracking (per 1M tokens)
COST_PER_1M_INPUT = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-sonnet-4-5-20250929": 3.00,
}
COST_PER_1M_OUTPUT = {
    "claude-haiku-4-5-20251001": 4.00,
    "claude-sonnet-4-5-20250929": 15.00,
}
from app.features.chat.storage import get_chat_storage
from app.features.letta import get_letta_service

logger = logging.getLogger("Jarvis.Chat")

# Use Haiku 3.5 for chat (cost-effective for text conversations)
# Voice memo processing and journaling use Sonnet via llm.py (quality matters more there)
MODEL_ID = os.getenv("CLAUDE_CHAT_MODEL", "claude-haiku-4-5-20251001")
MAX_TOOL_CALLS = 8  # Increased to handle multi-step requests


class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request to the chat endpoint."""
    message: str
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    conversation_id: Optional[str] = None  # For memory caching - same convo reuses cached context
    user_context: Optional[str] = None
    client_type: str = "telegram"  # "telegram" or "web" - controls response style
    model: Optional[str] = None  # Allow model selection (e.g., "claude-sonnet-4-5-20250929")


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    response: str
    tools_used: List[str] = Field(default_factory=list)
    tool_results_summary: Optional[str] = None  # Key findings from tool calls for history
    error: Optional[str] = None


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are Jarvis, a personal AI assistant with direct access to the user's knowledge database.

CURRENT CONTEXT:
- Date: {current_date}
- Time: {current_time}
- User Location: {user_location}

AVAILABLE TOOLS:
- **Database queries**: meetings, contacts, tasks, emails, calendar events, reflections, journals, messages
- **Task management**: create tasks, complete tasks, list pending tasks
- **Contact search**: find people, view interaction history
- **Time/Location**: get current time, update user location
- **Search**: full-text search across transcripts, notes, and messages
- **Books & Highlights**: reading list, book highlights, annotations, reading notes
- **Recent Voice Memo**: what was just recorded and what was created from it
- **Calendar creation**: schedule new events in Google Calendar
- **Email sending**: draft and send emails (with user confirmation)
- **Messaging (Beeper)**: send messages via WhatsApp, Telegram, LinkedIn, etc.
- **Sync trigger**: trigger immediate data sync when needed

MESSAGING DATA STRATEGY (IMPORTANT - READ THIS):
Messages from WhatsApp, Telegram, LinkedIn, etc. are synced to the database every 15 minutes.

**PREFER DATABASE QUERIES** (faster, more data, no external API):
- get_beeper_inbox → queries beeper_chats table
- get_beeper_contact_messages → queries beeper_messages table  
- search_beeper_messages → queries beeper_messages table
- get_beeper_chat_messages → queries beeper_messages table

**USE LIVE API ONLY WHEN:**
- User explicitly asks for "latest" or "most recent" messages (last 15 min)
- User says "sync messages now" or "refresh" → use trigger_beeper_sync
- User is about to send a message → use send_beeper_message (always live)

**Example decisions:**
- "Show messages from John" → get_beeper_contact_messages (database)
- "What did Sarah say?" → search_beeper_messages (database)
- "Any new messages in the last 5 minutes?" → trigger_beeper_sync first, then get_beeper_inbox
- "Send reply to John" → send_beeper_message (live API)

MESSAGING VIA BEEPER:
You have access to the user's messages across WhatsApp, Telegram, LinkedIn, and more through Beeper.

When the user says:
- "Send a message to X" → Use Beeper (WhatsApp by default if available)
- "Send a WhatsApp to X" → Use Beeper WhatsApp
- "Message X on LinkedIn" → Use Beeper LinkedIn
- "Reply to X" → Use Beeper to the appropriate platform
- "Who do I need to reply to?" → Use get_beeper_inbox
- "What did X send me?" → Use get_beeper_contact_messages

PLATFORM PRIORITY (when contact has multiple platforms):
1. **WhatsApp** (default - most personal/responsive)
2. **LinkedIn** (for professional contacts)
3. **Telegram** (lowest priority)

MESSAGING TOOLS:
- **get_beeper_inbox**: See who needs a reply (from DATABASE - synced every 15 min)
- **get_beeper_chat_messages**: Read conversation with someone (from DATABASE)
- **search_beeper_messages**: Search message history (from DATABASE)
- **get_beeper_contact_messages**: All messages with a contact (from DATABASE)
- **send_beeper_message**: Send a message (LIVE API - ⚠️ REQUIRES CONFIRMATION)
- **mark_beeper_read**: Mark messages as read (LIVE API)
- **archive_beeper_chat**: Archive a conversation (DATABASE + triggers sync)
- **trigger_beeper_sync**: Force immediate sync from Beeper → database (use when user needs latest)
- **get_beeper_status**: Check if messaging bridge is available

SENDING MESSAGES - CRITICAL RULES:
1. **ALWAYS ask for confirmation** before sending any message
2. Show the user: "[Platform] to [Name]: [Message]" and ask "Shall I send this?"
3. When user confirms ("yes", "send it", "go ahead"):
   → YOU MUST CALL send_beeper_message tool with user_confirmed=true
   → DO NOT just say "Message sent!" - you MUST invoke the tool
   → The message will NOT send unless you call the tool
4. NEVER send without explicit confirmation
5. NEVER claim success without actually calling the send tool

CONVERSATION CONTEXT FOR MESSAGING:
When user initiates a messaging flow, TRACK THE CONTEXT through follow-up messages:

**Example multi-turn conversation:**
User: "Send a message to Tobi"
Jarvis: "Found Tobi (WhatsApp). What would you like to send?"
User: "Frohes Neues Jahr!"
→ User is providing the MESSAGE CONTENT, not asking you to wish them happy new year!
→ You should confirm: "I'll send to Tobi on WhatsApp: 'Frohes Neues Jahr!' Shall I send it?"

**Key insight**: After asking "what do you want to send?", the next user message IS the content to send, not a new request.

**Another example:**
User: "Message Sarah"
Jarvis: "Found Sarah on WhatsApp. What's the message?"
User: "Running late, be there in 10"
→ This is the message! Confirm and send, don't interpret literally.

Example workflow:
User: "Tell Sarah I'm running 10 minutes late"
Jarvis: "I'll send this WhatsApp to Sarah: 'Hey, running about 10 minutes late!' Shall I send it?"
User: "Yes"
Jarvis: [calls send_beeper_message with user_confirmed=true]

GUIDELINES:
1. **Use tools proactively** - Don't guess, query the data
2. **Be concise** - User is on mobile (Telegram), keep responses short
3. **Confirm actions** - When creating/completing tasks, confirm what was done
4. **Clarify when needed** - Ask if the query is ambiguous
5. **No results = say so** - "I couldn't find any meetings with John"
6. **Format for Telegram** - Use **bold**, _italic_, • bullet points
7. **Remember context** - Use conversation history to understand follow-up questions
8. **Track multi-turn flows** - If you asked "what to send?", the next message IS the content

UNDERSTANDING CONVERSATION CONTEXT:
The conversation_history contains recent messages. Use it to understand what the user means:

**Pattern: Messaging flow**
- If previous assistant message asked "What would you like to send?" or "What's the message?"
- Then the current user message IS the message content to send
- Do NOT interpret it as a new command or question

**Pattern: Confirmation flow**
- If previous assistant message showed a draft and asked to confirm
- Then "yes", "yeah", "send it", "go ahead" = user_confirmed=true
- Then "no", "cancel", "wait" = don't send

**Pattern: Follow-up questions**
- If previous exchange was about a specific contact/meeting/task
- Then "show more", "what else", "when" refers to that same entity

QUERY TIPS:
- For "my tasks" or "what do I need to do" → use get_tasks tool
- For "who is [person]" → use search_contacts tool
- For "when did I last meet [person]" → use get_meetings tool with contact filter
- For "what happened today/yesterday" → use get_journals or search_transcripts
- For "remind me to X" or "add task X" → use create_task tool
- For "what time is it" → use get_current_time tool
- For "what did I just say?" or "summarize that" → use get_recent_voice_memo tool
- For "what books am I reading?" → use get_books tool
- For "show me highlights from [book]" → use get_highlights tool
- For "who messaged me?" or "any messages?" → use get_beeper_inbox tool
- For "send message/WhatsApp/text to X" → compose with send_beeper_message (confirm first!)
- For "what did X send me?" → use get_beeper_contact_messages
- For "reply to X" → get_beeper_chat_messages then send_beeper_message
- For "schedule a meeting" or "add to my calendar" → use create_calendar_event tool
- For "send email to X" or "write an email" → use create_email_draft
- For "show my drafts" → use list_email_drafts

VOICE MEMO CONTEXT:
The conversation history may include [Voice Memo Sent] entries. These indicate the user sent a voice recording that was processed. When users ask follow-up questions like:
- "What did you just create?"
- "Can you summarize what I said?"
- "What tasks came from that?"
Use the get_recent_voice_memo tool to get full details about the most recent recording and what was created.

CALENDAR CREATION (CRITICAL TIME RULES):
When users ask to schedule something:

1. **ALWAYS call get_current_time FIRST** - this gives you the user's LOCAL time and timezone
2. **SNAP to 30-minute intervals** - all events start/end at :00 or :30
   - "in an hour" at 1:43pm → 2:30pm or 3:00pm (next half-hour AFTER calculated time)
   - "at 3" → 3:00pm exactly
   - "in 20 minutes" at 2:10pm → 2:30pm
3. **Default 30-minute duration** unless user specifies otherwise
4. **Use user's timezone** - get_current_time tells you their timezone

EXAMPLES:
- "Create event in an hour" at 1:43pm → start 3:00pm, end 3:30pm (round 2:43 up to next :30/:00)
- "Meeting at 2pm for 1 hour" → start 2:00pm, end 3:00pm
- "Quick call in 30 min" at 2:05pm → start 2:30pm, end 3:00pm

Required fields: title, start_time (ISO), end_time (ISO)
Optional: description, location, attendees (email addresses)

CALENDAR MANAGEMENT (IMPORTANT):
You can create AND reschedule calendar events:

1. **Creating events**: Use create_calendar_event
   - Schedule meetings, block time, set reminders
   - Confirm details before creating

2. **Rescheduling your own meetings**: Use update_calendar_event
   - Query calendar_events table first to get google_event_id
   - Update time, location, description, attendees
   - Automatically notifies all attendees
   - Use description field to add reschedule reason: "Rescheduled due to [reason]"

3. **Declining invitations**: Use decline_calendar_event
   - For meetings someone else invited you to
   - Can include comment like "Can we do 3pm instead?"
   - Notifies the organizer

WORKFLOW EXAMPLES:
- "Reschedule my meeting with Ed to 3pm tomorrow" → Query calendar_events for the event → update_calendar_event with new time
- "Decline Ed's meeting and suggest Friday instead" → Query calendar_events → decline_calendar_event with comment
- "Move my 2pm meeting to 4pm and add a note about the reason" → update_calendar_event with new time + description

EMAIL DRAFTS (IMPORTANT):
Emails work through Gmail's draft system for safety:

1. **Creating emails**: Use create_email_draft - this saves to Gmail Drafts folder
   - The draft appears immediately in the user's Gmail
   - Can look up contact emails by name
   - Show the draft details and ask if user wants to send

2. **Listing drafts**: Use list_email_drafts to see all pending drafts
   - Works for both Jarvis-created and manually-created drafts in Gmail

3. **Sending**: ONLY use send_email_draft after explicit confirmation
   - Requires the draft_id from create_email_draft
   - User must say "send it", "yes send", etc.
   - NEVER send without clear confirmation

4. **Deleting**: Use delete_email_draft to discard drafts

The user prefers reviewing drafts before sending. Always create drafts first and wait for confirmation.

ABOUT THE USER:
The user's name is **Aaron**. All other details about Aaron (location, interests, current projects, mood, focus areas) are stored in Mem0 memories and journal entries - always query these for up-to-date context rather than assuming.

⚠️ CRITICAL INSTRUCTION-FOLLOWING RULES:
1. **FOLLOW SEQUENCES EXACTLY** - If user says "First do X, then Y", complete X before starting Y
2. **CONFIRM BEFORE PROCEEDING** - If user says "list them here first", show the list and WAIT for approval
3. **DO NOT SKIP STEPS** - Every numbered instruction must be executed in order
4. **ACKNOWLEDGE EACH STEP** - Say "✅ Done: [action]" before moving to next step
5. **ASK IF UNSURE** - "You asked me to do X then Y. I've done X. Should I proceed with Y?"

⚠️ CRITICAL ANTI-LOOP RULES:
1. **NEVER send the same message twice** - if you already sent to someone, don't send again
2. **NEVER call the same tool with same params twice** - cache results mentally
3. **If a tool fails, try ONCE more then give up** - don't retry infinitely
4. **If you asked for confirmation, WAIT** - don't send in same turn you asked
5. **If send fails, tell user and STOP** - don't keep retrying the same send

⚠️ CRITICAL HONESTY RULES (NO HALLUCINATION):
1. **NEVER claim you did something without tool result confirmation**
   - If you call forget_memory → check the returned status
   - If status is "deleted" → you can say "I deleted it"
   - If status is anything else → say "I couldn't delete it" with the actual error
2. **ALWAYS verify tool results before reporting to user**
   - Tool returns success → report success
   - Tool returns error/failed → report failure
3. **When user asks "did it work?" → actually check**
   - Call search_memories to verify deletion
   - Don't assume - query the data
4. **CURRENT DATE IS {current_date}** - do NOT say dates have passed if they haven't
   - January 10th has NOT passed if today is before January 10th
   - Check the date above before making temporal claims

Remember: You have access to a rich personal knowledge base. Use the tools to provide genuinely helpful, personalized responses."""

# Default prompt (used when we can't get dynamic context)
SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(
    current_date="(use get_current_time tool)",
    current_time="(use get_current_time tool)",
    user_location="Unknown (user can tell you via chat)"
)


# =============================================================================
# CHAT PROCESSING
# =============================================================================

class ChatService:
    """Handles conversational AI with tool use and memory."""
    
    def __init__(self):
        # Disable automatic retries - better to fail fast than consume rate limit budget
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_retries=0  # Don't auto-retry on 429 - we handle it ourselves
        )
        # Get memory service
        self.memory = get_memory_service()
    
    async def _get_memory_context(self, message: str, conversation_id: Optional[str] = None) -> str:
        """
        Get relevant memories for the current message.
        
        Uses conversation-level caching: memory is only searched ONCE when the
        conversation starts (first message), not on every follow-up message.
        This is similar to how Claude Desktop loads context at conversation start.
        
        Cache TTL is 30 minutes - if user returns later, we re-search for fresh context.
        """
        # Check conversation cache first (fast path - no API call)
        if conversation_id:
            cached_context = _get_cached_memory_context(conversation_id)
            if cached_context is not None:
                logger.debug(f"Using cached memory context for conversation {conversation_id[:8]}...")
                return cached_context
        
        try:
            # Search for memories related to the message
            # Using 10 for good context with faster response (18 was too slow)
            memories = await self.memory.search(message, limit=10)
            
            if not memories:
                # Even if no matches, note that memory is available
                context = "\n\n**STORED MEMORIES:** No specific memories found for this query. Use search_memories tool if needed."
            else:
                # Format memories clearly
                lines = ["**RELEVANT STORED MEMORIES (from Mem0):**"]
                for mem in memories:
                    memory_text = mem.get("memory", "")
                    mem_type = mem.get("metadata", {}).get("type", "unknown")
                    source = mem.get("metadata", {}).get("source", "unknown")
                    if memory_text:
                        lines.append(f"• [{mem_type}] {memory_text}")
                
                lines.append(f"\n_({len(memories)} memories loaded - use search_memories for more)_")
                context = "\n\n" + "\n".join(lines)
            
            # Cache the result for this conversation
            if conversation_id:
                _set_cached_memory_context(conversation_id, context)
                logger.info(f"Cached memory context for conversation {conversation_id[:8]}... (30min TTL)")
            
            return context
        except Exception as e:
            logger.warning(f"Could not get memory context: {e}")
            return "\n\n**MEMORY STATUS:** Memory service unavailable - use search_memories tool."
    
    async def _save_memory_from_conversation(self, user_message: str, assistant_response: str) -> None:
        """
        Extract and save memories from the conversation intelligently.
        
        Uses a smarter heuristic than just keywords - we want to capture:
        - Personal facts (I am, my job, etc.)
        - Project updates (built, deployed, finished, working on)
        - Decisions and events (decided, chose, met with, started)
        - Opinions and preferences (think, believe, prefer)
        - Temporal context (today, yesterday, this week)
        
        The actual extraction is done by Claude Haiku via Mem0's add() method,
        which intelligently parses the text for facts. The heuristic here just
        gates the API call to avoid unnecessary costs.
        """
        try:
            user_lower = user_message.lower()
            
            # Skip pure questions (unlikely to contain memorable facts)
            question_starters = ["what ", "when ", "where ", "who ", "how ", "why ", "can you", "could you", "would you", "do you"]
            is_pure_question = any(user_lower.strip().startswith(q) for q in question_starters) and "?" in user_message
            
            # Skip very short messages
            if len(user_message) < 25:
                return
            
            # Broader heuristics for meaningful content (not just "I am...")
            personal_indicators = [
                # Traditional personal statements
                "i'm", "i am", "my ", "i work", "i live", "i prefer", "i like", "i don't",
                "i was", "i met", "i went", "i have", "i need", "i want",
                # Actions and achievements
                "i built", "i deployed", "i created", "i finished", "i started", "i completed",
                "i decided", "i chose", "i realized", "i learned", "i discovered",
                # Project/work updates
                "working on", "built the", "deployed the", "finished the", "shipped",
                "launched", "released", "implemented", "fixed", "updated",
                # Decisions and opinions
                "decided to", "going to", "plan to", "will be", "should be",
                "think that", "believe that", "feel that",
                # Temporal markers (often accompany important info)
                "today ", "yesterday", "this week", "last week", "this month",
                "just now", "earlier", "recently",
                # Relationships and context
                "met with", "talked to", "spoke with", "heard from",
                "relationship", "contact", "friend", "colleague",
            ]
            
            has_meaningful_content = any(kw in user_lower for kw in personal_indicators)
            
            # If it's a pure question with no personal context, skip
            if is_pure_question and not has_meaningful_content:
                return
            
            # If it has meaningful content, extract memories
            if has_meaningful_content:
                combined = f"User said: {user_message}"
                count = await self.memory.extract_from_text(
                    text=combined,
                    source="chat",
                )
                if count > 0:
                    logger.info(f"Extracted {count} memories from chat")
        except Exception as e:
            logger.warning(f"Could not save memory: {e}")
    
    def _get_recent_journals_context(self, limit: int = 3) -> str:
        """
        Get recent journal entries to provide context about user's current state.
        
        This gives the AI awareness of:
        - Current mood and energy levels
        - Recent activities and focus areas
        - Tomorrow's planned tasks
        - Recent challenges and wins
        """
        try:
            from app.core.database import supabase
            from datetime import datetime, timedelta
            
            # Get journals from the last 7 days
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            # Note: Using only columns that exist in the journals table
            result = supabase.table("journals").select(
                "date, title, content, mood, tomorrow_focus, gratitude"
            ).gte("date", seven_days_ago).order("date", desc=True).limit(limit).execute()
            
            if not result.data:
                return ""
            
            journal_lines = []
            for j in result.data:
                date_str = j.get("date", "Unknown date")
                mood = j.get("mood") or "Not recorded"
                content = j.get("content") or j.get("title") or "No content"
                
                # Truncate content if too long
                if len(content) > 300:
                    content = content[:300] + "..."
                
                journal_lines.append(f"**{date_str}** (Mood: {mood})")
                journal_lines.append(f"  {content}")
                
                # Add tomorrow's focus if available (most relevant for recent entries)
                tomorrow_focus = j.get("tomorrow_focus")
                if tomorrow_focus and isinstance(tomorrow_focus, list) and len(tomorrow_focus) > 0:
                    focus_str = ", ".join(tomorrow_focus[:3])
                    journal_lines.append(f"  → Focus: {focus_str}")
                
                journal_lines.append("")
            
            if journal_lines:
                return "\n\n**RECENT JOURNAL CONTEXT (user's current state):**\n" + "\n".join(journal_lines)
            return ""
            
        except Exception as e:
            logger.warning(f"Could not get journal context: {e}")
            return ""
    
    async def _get_letta_context(self) -> str:
        """Get episodic memory context from Letta (conversation history, topics, decisions)."""
        try:
            letta = get_letta_service()
            return await letta.get_context_for_chat()
        except Exception as e:
            logger.warning(f"Could not get Letta context: {e}")
            return ""
    
    def _extract_key_finding(self, tool_name: str, tool_input: dict, result: dict) -> Optional[str]:
        """
        Extract key findings from tool results to persist in conversation history.
        This helps maintain context across conversation turns.
        
        Returns a concise string summarizing important findings, or None if nothing notable.
        """
        try:
            # Skip tools that don't produce important findings for history
            skip_tools = {"get_current_time", "get_user_location", "update_user_location", "trigger_beeper_sync"}
            if tool_name in skip_tools:
                return None
            
            # Handle search/get results that found something
            if isinstance(result, dict):
                # Message sending - capture what was sent
                if tool_name == "send_beeper_message":
                    if result.get("status") == "sent":
                        chat_name = result.get("chat_name", "unknown")
                        return f"SENT message to {chat_name}"
                    elif "error" in result:
                        return f"FAILED to send: {result.get('error', 'unknown error')[:50]}"
                
                # Meeting/contact searches - capture who was found
                if tool_name in ("get_meetings", "search_meetings"):
                    meetings = result.get("meetings", [])
                    if meetings:
                        titles = [m.get("title", "untitled")[:30] for m in meetings[:3]]
                        return f"FOUND {len(meetings)} meeting(s): {', '.join(titles)}"
                
                if tool_name in ("search_contacts", "get_contacts"):
                    contacts = result.get("contacts", [])
                    if contacts:
                        names = [f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() for c in contacts[:3]]
                        return f"FOUND {len(contacts)} contact(s): {', '.join(names)}"
                
                # Beeper inbox - capture what needs response
                if tool_name == "get_beeper_inbox":
                    chats = result.get("chats", [])
                    if chats:
                        names = [c.get("chat_name", "")[:20] for c in chats[:3]]
                        return f"INBOX: {len(chats)} chat(s) need reply: {', '.join(names)}"
                
                # Chat messages - capture recent message content
                if tool_name in ("get_beeper_chat_messages", "get_beeper_contact_messages"):
                    messages = result.get("messages", [])
                    if messages:
                        latest = messages[0] if messages else {}
                        sender = latest.get("sender", "unknown")
                        content_preview = (latest.get("content", "")[:50] + "...") if latest.get("content", "") else ""
                        return f"LAST MSG from {sender}: {content_preview}"
                
                # Task operations
                if tool_name == "create_task":
                    if result.get("status") == "created":
                        return f"CREATED task: {result.get('title', 'untitled')[:40]}"
                
                if tool_name == "complete_task":
                    if result.get("status") == "completed":
                        return f"COMPLETED task: {result.get('title', 'untitled')[:40]}"
                
                # Calendar operations  
                if tool_name == "create_calendar_event":
                    if result.get("status") == "created":
                        return f"CREATED event: {result.get('title', 'untitled')[:30]}"
                
                # Email operations
                if tool_name == "create_email_draft":
                    if result.get("status") == "draft_created":
                        return f"DRAFTED email to: {result.get('to', 'unknown')[:30]}"
                
                if tool_name == "send_email_draft":
                    if result.get("status") == "sent":
                        return f"SENT email to: {result.get('to', 'unknown')[:30]}"
                
                # Full-text search
                if tool_name == "search_transcripts":
                    results = result.get("results", [])
                    if results:
                        return f"SEARCH found {len(results)} transcript(s)"
                
                # Recent voice memo
                if tool_name == "get_recent_voice_memo":
                    if result.get("found"):
                        category = result.get("category", "unknown")
                        return f"VOICE MEMO: {category} - {result.get('summary', '')[:50]}"
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting finding: {e}")
            return None
    
    def _build_system_prompt(self, memory_context: str = "", journal_context: str = "", letta_context: str = "") -> str:
        """Build system prompt with current date/time/location, memory, journal, and Letta context."""
        from datetime import datetime
        from app.features.chat.tools import _get_user_location
        
        # Get user location (returns location string or "Not set")
        location_info = _get_user_location()
        location_str = location_info.get("location", "Not set")
        timezone_str = location_info.get("timezone", "UTC")
        
        # Get current time in user's timezone
        try:
            import pytz
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            current_date = now.strftime("%A, %B %d, %Y")
            current_time = now.strftime("%I:%M %p")
        except Exception:
            now = datetime.utcnow()
            current_date = now.strftime("%A, %B %d, %Y") + " (UTC)"
            current_time = now.strftime("%I:%M %p") + " (UTC)"
        
        base_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            current_date=current_date,
            current_time=current_time,
            user_location=f"{location_str} ({timezone_str})"
        )

        # Append Letta episodic context first (conversation history, topics, decisions)
        if letta_context:
            base_prompt += letta_context

        # Append journal context (user's current mood/focus)
        if journal_context:
            base_prompt += journal_context

        # Append Mem0 semantic memory context last
        if memory_context:
            base_prompt += memory_context

        return base_prompt

    def _add_client_specific_instructions(self, base_prompt: str, client_type: str) -> str:
        """
        Add client-specific response style instructions.

        Telegram: Short, concise, mobile-optimized
        Web: Detailed, comprehensive, desktop reading experience
        """
        if client_type == "telegram":
            return base_prompt + """

TELEGRAM MODE - RESPONSE STYLE:
- Keep responses SHORT and CONCISE (1-3 sentences when possible)
- Use simple Markdown (bold, italic, code only - NO tables or complex formatting)
- Prioritize mobile readability
- Ask before long operations
- Get to the point quickly
"""
        else:  # web or default
            return base_prompt + """

WEB CHAT MODE - RESPONSE STYLE:
- Provide DETAILED, THOROUGH explanations
- Use rich Markdown: tables, code blocks, numbered lists, bullet points
- Include context and reasoning
- Show intermediate steps for complex operations
- Format for desktop reading experience
- Be comprehensive and explanatory
"""
    
    async def process_message_stream(self, request: ChatRequest):
        """
        Process a user message and yield streaming chunks.

        Yields dictionaries with:
        - {"type": "content", "text": "..."} for text chunks
        - {"type": "tool_use", "tool": "...", "input": {...}} for tool calls
        - {"type": "tool_result", "tool": "...", "output": {...}} for tool results
        - {"type": "done", "tools_used": [...]} when complete
        - {"type": "error", "message": "..."} on error
        """
        import asyncio
        import time
        
        try:
            start_time = time.time()
            
            # Run all context gathering in PARALLEL for faster startup
            # Pass conversation_id for memory caching (avoids repeat embedding lookups)
            memory_task = asyncio.create_task(
                self._get_memory_context(request.message, conversation_id=request.conversation_id)
            )
            letta_task = asyncio.create_task(self._get_letta_context())
            
            # Journal context is sync/fast, run directly
            journal_context = self._get_recent_journals_context(limit=3)
            
            # Wait for async tasks (in parallel) with timeout
            try:
                memory_context, letta_context = await asyncio.wait_for(
                    asyncio.gather(memory_task, letta_task, return_exceptions=True),
                    timeout=2.0  # 2 second max for context gathering
                )
            except asyncio.TimeoutError:
                logger.warning("Context gathering timed out after 2s, proceeding without")
                memory_context = ""
                letta_context = ""
            
            # Handle exceptions from gather
            if isinstance(memory_context, Exception):
                logger.warning(f"Memory context failed: {memory_context}")
                memory_context = ""
            if isinstance(letta_context, Exception):
                logger.warning(f"Letta context failed: {letta_context}")
                letta_context = ""
            
            context_time = time.time() - start_time
            logger.info(f"Context gathered in {context_time:.2f}s (parallel)")

            system_prompt = self._build_system_prompt(memory_context, journal_context, letta_context)
            system_prompt = self._add_client_specific_instructions(system_prompt, request.client_type)

            model = request.model or MODEL_ID
            logger.info(f"Streaming with model: {model}, client_type: {request.client_type}")

            # Build messages
            messages = []
            for msg in request.conversation_history[-10:]:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": request.message})

            tools_used = []
            tool_call_count = 0

            # Tool loop with streaming
            while tool_call_count < MAX_TOOL_CALLS:
                # Log the request parameters for debugging
                logger.info(f"Calling Anthropic streaming API:")
                logger.info(f"  Model: {model}")
                logger.info(f"  Max tokens: 8000")
                logger.info(f"  Messages count: {len(messages)}")
                logger.info(f"  Tools count: {len(TOOLS)}")

                # Use Anthropic's streaming API
                try:
                    with self.client.messages.stream(
                        model=model,
                        max_tokens=8000,
                        system=system_prompt,
                        tools=TOOLS,
                        messages=messages
                    ) as stream:
                        # Stream text chunks in real-time
                        for text in stream.text_stream:
                            yield {"type": "content", "text": text}

                        # Get the final message after streaming completes
                        response = stream.get_final_message()
                except anthropic.BadRequestError as e:
                    logger.error(f"Anthropic API error: {e}")
                    yield {"type": "error", "message": str(e)}
                    return

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    tool_call_count += 1

                    assistant_content = response.content
                    tool_results = []

                    for block in assistant_content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_id = block.id

                            logger.info(f"🔧 Tool invoked: {tool_name}")
                            tools_used.append(tool_name)

                            # Notify client about tool use
                            yield {"type": "tool_use", "tool": tool_name, "input": tool_input}

                            # Execute tool
                            result = execute_tool(tool_name, tool_input, last_user_message=request.message)
                            logger.info(f"   Result: {json.dumps(result, indent=2)[:500]}")

                            # Notify client about tool result
                            yield {"type": "tool_result", "tool": tool_name, "output": result}

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": json.dumps(result)
                            })

                    # Add to messages for next iteration
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                else:
                    # Done - no more tool calls
                    break

            # Final event
            yield {"type": "done", "tools_used": tools_used}

        except Exception as e:
            logger.exception("Streaming error")
            yield {"type": "error", "message": str(e)}

    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Process a user message and return a response."""
        import asyncio
        import time
        
        try:
            start_time = time.time()
            
            # Run all context gathering in PARALLEL for faster startup
            # Pass conversation_id for memory caching (avoids repeat embedding lookups)
            memory_task = asyncio.create_task(
                self._get_memory_context(request.message, conversation_id=request.conversation_id)
            )
            letta_task = asyncio.create_task(self._get_letta_context())
            
            # Journal context is sync/fast, run directly
            journal_context = self._get_recent_journals_context(limit=3)
            
            # Wait for async tasks (in parallel) with timeout
            try:
                memory_context, letta_context = await asyncio.wait_for(
                    asyncio.gather(memory_task, letta_task, return_exceptions=True),
                    timeout=2.0  # 2 second max for context gathering
                )
            except asyncio.TimeoutError:
                logger.warning("Context gathering timed out after 2s, proceeding without")
                memory_context = ""
                letta_context = ""
            
            # Handle exceptions from gather
            if isinstance(memory_context, Exception):
                logger.warning(f"Memory context failed: {memory_context}")
                memory_context = ""
            if isinstance(letta_context, Exception):
                logger.warning(f"Letta context failed: {letta_context}")
                letta_context = ""
            
            context_time = time.time() - start_time
            logger.info(f"Context gathered in {context_time:.2f}s (parallel)")
            
            # Build dynamic system prompt with current context, journals, Letta, and memory
            system_prompt = self._build_system_prompt(memory_context, journal_context, letta_context)

            # Add client-specific response style instructions (telegram vs web)
            system_prompt = self._add_client_specific_instructions(system_prompt, request.client_type)

            # Use specified model or default
            model = request.model or MODEL_ID
            logger.info(f"Using model: {model}, client_type: {request.client_type}")
            
            # Build conversation messages
            messages = []
            
            # Add conversation history
            for msg in request.conversation_history[-10:]:  # Last 10 messages for context
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add current message
            messages.append({
                "role": "user",
                "content": request.message
            })
            
            # Call Claude with tools
            tools_used = []
            tool_call_count = 0
            
            # Track sent messages in THIS request to prevent duplicates
            sent_messages_this_request = set()
            
            # Track important tool findings to persist in conversation history
            key_tool_findings = []
            
            while tool_call_count < MAX_TOOL_CALLS:
                response = self.client.messages.create(
                    model=model,  # Use selected model
                    max_tokens=8000,  # Increased for web chat detailed responses
                    system=system_prompt,  # Use dynamic prompt with date/time/location and client-specific style
                    tools=TOOLS,
                    messages=messages
                )
                
                # Check if Claude wants to use a tool
                if response.stop_reason == "tool_use":
                    tool_call_count += 1
                    
                    # Process tool calls
                    assistant_content = response.content
                    tool_results = []
                    
                    for block in assistant_content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_id = block.id
                            
                            logger.info(f"🔧 Tool invoked: {tool_name}")
                            logger.info(f"   Input: {json.dumps(tool_input, indent=2)[:500]}")
                            tools_used.append(tool_name)
                            
                            # DUPLICATE CHECK for send_beeper_message
                            if tool_name == "send_beeper_message":
                                chat_id = tool_input.get("beeper_chat_id", "")
                                content_hash = hash(tool_input.get("content", "")[:50])
                                dedup_key = f"{chat_id}:{content_hash}"
                                
                                if dedup_key in sent_messages_this_request:
                                    logger.warning(f"⚠️ DUPLICATE BLOCKED: Already sent to {chat_id} in this request")
                                    result = {"error": "Already sent this message in this request. Cannot send duplicate."}
                                else:
                                    sent_messages_this_request.add(dedup_key)
                                    result = execute_tool(tool_name, tool_input, last_user_message=request.message)
                            else:
                                # Execute the tool - pass last user message for send_beeper_message confirmation check
                                result = execute_tool(tool_name, tool_input, last_user_message=request.message)
                            
                            logger.info(f"   Result: {json.dumps(result, indent=2)[:500]}")
                            
                            # Capture key findings for conversation history
                            finding = self._extract_key_finding(tool_name, tool_input, result)
                            if finding:
                                key_tool_findings.append(finding)
                            
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": json.dumps(result)
                            })
                    
                    # Add assistant message and tool results to conversation
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content
                    })
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                    
                else:
                    # Claude is done - extract final response
                    final_response = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_response += block.text
                    
                    logger.info(f"💬 Final response (no more tools): {final_response[:200]}")
                    
                    # Save memories from this conversation (Mem0 - cheap, selective)
                    # Only extracts if user shared meaningful content
                    try:
                        await self._save_memory_from_conversation(request.message, final_response)
                    except Exception as e:
                        logger.warning(f"Failed to save conversation memory: {e}")
                    
                    # Calculate and log cost using selected model
                    input_tokens = response.usage.input_tokens
                    output_tokens = response.usage.output_tokens
                    input_cost = (input_tokens / 1_000_000) * COST_PER_1M_INPUT.get(model, 0.80)
                    output_cost = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT.get(model, 4.00)
                    total_cost = input_cost + output_cost

                    logger.info(f"💵 Cost: ${total_cost:.4f} ({input_tokens} in / {output_tokens} out) | Model: {model}")
                    
                    # Store raw message exchange in Supabase (for audit trail + Letta batch)
                    # This is processed by Letta in batch later (hourly/daily), not per-message
                    try:
                        storage = get_chat_storage()
                        await storage.store_exchange(
                            user_message=request.message,
                            assistant_response=final_response,
                            source="telegram",
                            tools_used=list(set(tools_used)) if tools_used else None,
                            assistant_metadata={
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "cost_usd": round(total_cost, 6),
                                "model": MODEL_ID,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store message exchange: {e}")
                    
                    # NOTE: Letta is NOT called per-message (too expensive ~$0.05/call)
                    # Instead, batch processing runs hourly (lightweight archival) 
                    # and daily (full consolidation with memory block updates)
                    # See: LettaService.process_unprocessed_messages()
                    
                    # Build tool results summary for conversation history
                    tool_results_summary = None
                    if key_tool_findings:
                        tool_results_summary = " | ".join(key_tool_findings[:5])  # Limit to 5 most important
                    
                    return ChatResponse(
                        response=final_response,
                        tools_used=list(set(tools_used)),
                        tool_results_summary=tool_results_summary
                    )
            
            # Max tool calls reached
            return ChatResponse(
                response="I've done a lot of searching but couldn't complete the request. Could you try a more specific question?",
                tools_used=tools_used,
                error="max_tool_calls_reached"
            )
        
        except anthropic.RateLimitError as e:
            # Rate limit - fail fast, don't retry
            logger.warning(f"Rate limited by Anthropic: {e}")
            return ChatResponse(
                response="🔄 I'm a bit overloaded right now. Please wait a moment and try again.",
                error="rate_limited"
            )
        except anthropic.APIStatusError as e:
            # Other API errors (500s, etc) - fail fast
            logger.error(f"Anthropic API status error {e.status_code}: {e.message}")
            return ChatResponse(
                response="Sorry, I'm having trouble connecting right now. Please try again in a moment.",
                error=f"api_error_{e.status_code}"
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return ChatResponse(
                response="Sorry, I'm having trouble connecting to my brain. Please try again.",
                error=str(e)
            )
        except Exception as e:
            logger.exception("Chat processing error")
            return ChatResponse(
                response="Something went wrong. Please try again.",
                error=str(e)
            )


# Singleton instance
_chat_service: Optional[ChatService] = None

def get_chat_service() -> ChatService:
    """Get or create the chat service singleton."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
