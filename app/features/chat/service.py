"""
Chat Service - Conversational AI with Tool Use and Memory.

This module provides a Claude-powered conversational interface that can:
1. Answer questions about your data (meetings, contacts, tasks, etc.)
2. Create new records (tasks, reflections)
3. Search and retrieve information
4. Execute actions (complete tasks, etc.)
5. Remember context across conversations (via Mem0)

Works similarly to Claude Desktop + MCP, but via Telegram.
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

import anthropic
from pydantic import BaseModel, Field

from app.features.chat.tools import TOOLS, execute_tool
from app.features.memory import get_memory_service

logger = logging.getLogger("Jarvis.Chat")

# Use Haiku 3.5 for chat (cost-effective for text conversations)
# Voice memo processing and journaling use Sonnet via llm.py (quality matters more there)
MODEL_ID = os.getenv("CLAUDE_CHAT_MODEL", "claude-haiku-4-5-20251001")
MAX_TOOL_CALLS = 3  # Reduced from 5 - prevents runaway loops


class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request to the chat endpoint."""
    message: str
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    user_context: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    response: str
    tools_used: List[str] = Field(default_factory=list)
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

⚠️ CRITICAL ANTI-LOOP RULES:
1. **NEVER send the same message twice** - if you already sent to someone, don't send again
2. **NEVER call the same tool with same params twice** - cache results mentally
3. **If a tool fails, try ONCE more then give up** - don't retry infinitely
4. **Maximum 2-3 tool calls per request** - if you need more, ask user to be more specific
5. **If you asked for confirmation, WAIT** - don't send in same turn you asked
6. **If send fails, tell user and STOP** - don't keep retrying the same send

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
    
    async def _get_memory_context(self, message: str) -> str:
        """Get relevant memories for the current message - ALWAYS included in prompt."""
        try:
            # Search for memories related to the message
            memories = await self.memory.search(message, limit=8)
            
            if not memories:
                # Even if no matches, note that memory is available
                return "\n\n**STORED MEMORIES:** No specific memories found for this query. Use search_memories tool if needed."
            
            # Format memories clearly
            lines = ["**RELEVANT STORED MEMORIES (from Mem0):**"]
            for mem in memories:
                memory_text = mem.get("memory", "")
                mem_type = mem.get("metadata", {}).get("type", "unknown")
                source = mem.get("metadata", {}).get("source", "unknown")
                if memory_text:
                    lines.append(f"• [{mem_type}] {memory_text}")
            
            lines.append(f"\n_({len(memories)} memories loaded - use search_memories for more)_")
            return "\n\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not get memory context: {e}")
            return "\n\n**MEMORY STATUS:** Memory service unavailable - use search_memories tool."
    
    async def _save_memory_from_conversation(self, user_message: str, assistant_response: str) -> None:
        """Extract and save memories from the conversation intelligently."""
        try:
            # Only extract if the user shared something meaningful (not just queries)
            meaningful_keywords = [
                "i'm", "i am", "my ", "i work", "i live", "i prefer", "i like", "i don't",
                "i was", "i met", "i went", "i have", "i need", "i want",
                "my name", "my job", "my company", "my friend"
            ]
            
            user_lower = user_message.lower()
            has_meaningful_content = any(kw in user_lower for kw in meaningful_keywords)
            
            if has_meaningful_content and len(user_message) > 30:
                # Extract memories from what user shared (not just questions)
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
            
            result = supabase.table("journals").select(
                "date, title, summary, mood, energy, tomorrow_focus, key_events, challenges, wins"
            ).gte("date", seven_days_ago).order("date", desc=True).limit(limit).execute()
            
            if not result.data:
                return ""
            
            journal_lines = []
            for j in result.data:
                date_str = j.get("date", "Unknown date")
                mood = j.get("mood") or "Not recorded"
                energy = j.get("energy") or "Not recorded"
                summary = j.get("summary") or j.get("title") or "No summary"
                
                # Truncate summary if too long
                if len(summary) > 300:
                    summary = summary[:300] + "..."
                
                journal_lines.append(f"**{date_str}** (Mood: {mood}, Energy: {energy})")
                journal_lines.append(f"  {summary}")
                
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
    
    def _build_system_prompt(self, memory_context: str = "", journal_context: str = "") -> str:
        """Build system prompt with current date/time/location, memory, and journal context."""
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
        
        # Append journal context (user's current mood/focus)
        if journal_context:
            base_prompt += journal_context
        
        # Append memory context if available
        if memory_context:
            base_prompt += memory_context
        
        return base_prompt
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Process a user message and return a response."""
        try:
            # Get relevant memories for this message
            memory_context = await self._get_memory_context(request.message)
            
            # Get recent journal context (mood, focus, recent activities)
            journal_context = self._get_recent_journals_context(limit=3)
            
            # Build dynamic system prompt with current context, journals, and memory
            system_prompt = self._build_system_prompt(memory_context, journal_context)
            
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
            
            while tool_call_count < MAX_TOOL_CALLS:
                response = self.client.messages.create(
                    model=MODEL_ID,
                    max_tokens=2000,
                    system=system_prompt,  # Use dynamic prompt with date/time/location
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
                    
                    # Save memories from this conversation (background, don't block)
                    try:
                        await self._save_memory_from_conversation(request.message, final_response)
                    except Exception as e:
                        logger.warning(f"Failed to save conversation memory: {e}")
                    
                    return ChatResponse(
                        response=final_response,
                        tools_used=list(set(tools_used))
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
