"""
Chat Service - Conversational AI with Tool Use.

This module provides a Claude-powered conversational interface that can:
1. Answer questions about your data (meetings, contacts, tasks, etc.)
2. Create new records (tasks, reflections)
3. Search and retrieve information
4. Execute actions (complete tasks, etc.)

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

logger = logging.getLogger("Jarvis.Chat")

MODEL_ID = os.getenv("CLAUDE_CHAT_MODEL", "claude-sonnet-4-5-20250929")
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
- **Database queries**: meetings, contacts, tasks, emails, calendar events, reflections, journals
- **Task management**: create tasks, complete tasks, list pending tasks
- **Contact search**: find people, view interaction history
- **Time/Location**: get current time, update user location
- **Search**: full-text search across transcripts and notes
- **Books & Highlights**: reading list, book highlights, annotations, reading notes
- **Recent Voice Memo**: what was just recorded and what was created from it
- **Calendar creation**: schedule new events in Google Calendar
- **Email sending**: draft and send emails (with user confirmation)
- **Messaging (Beeper)**: send messages via WhatsApp, Telegram, LinkedIn, etc.

MESSAGING VIA BEEPER (IMPORTANT):
You have access to the user's messages across WhatsApp, Telegram, LinkedIn, Signal, and more through Beeper.

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
- **get_beeper_inbox**: See who needs a reply (inbox-zero workflow)
- **get_beeper_chat_messages**: Read conversation with someone
- **search_beeper_messages**: Search message history
- **get_beeper_contact_messages**: All messages with a contact
- **send_beeper_message**: Send a message (⚠️ REQUIRES CONFIRMATION)
- **mark_beeper_read**: Mark messages as read
- **archive_beeper_chat**: Archive a conversation (handled)
- **get_beeper_status**: Check if messaging is available

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
Aaron is a German engineer currently based in Sydney, Australia, preparing to relocate to Singapore and Southeast Asia. He was the first employee at Algenie, an Australian biotech startup, and is currently in transition. His interests span climate tech, biotech, agritech, foodtech, and longevity. He records voice memos to capture thoughts, meetings, and reflections which are transcribed and stored in this system.

⚠️ CRITICAL ANTI-LOOP RULES:
1. **NEVER send the same message twice** - if you already sent to someone, don't send again
2. **NEVER call the same tool with same params twice** - cache results mentally
3. **If a tool fails, try ONCE more then give up** - don't retry infinitely
4. **Maximum 2-3 tool calls per request** - if you need more, ask user to be more specific
5. **If you asked for confirmation, WAIT** - don't send in same turn you asked
6. **If send fails, tell user and STOP** - don't keep retrying the same send

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
    """Handles conversational AI with tool use."""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with current date/time/location context."""
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
        
        return SYSTEM_PROMPT_TEMPLATE.format(
            current_date=current_date,
            current_time=current_time,
            user_location=f"{location_str} ({timezone_str})"
        )
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Process a user message and return a response."""
        try:
            # Build dynamic system prompt with current context
            system_prompt = self._build_system_prompt()
            
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
