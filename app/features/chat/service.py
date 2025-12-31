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
MAX_TOOL_CALLS = 5  # Prevent infinite loops


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

GUIDELINES:
1. **Use tools proactively** - Don't guess, query the data
2. **Be concise** - User is on mobile (Telegram), keep responses short
3. **Confirm actions** - When creating/completing tasks, confirm what was done
4. **Clarify when needed** - Ask if the query is ambiguous
5. **No results = say so** - "I couldn't find any meetings with John"
6. **Format for Telegram** - Use **bold**, _italic_, • bullet points
7. **Remember context** - Use conversation history to understand follow-up questions

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
- For "schedule a meeting" or "add to my calendar" → use create_calendar_event tool

VOICE MEMO CONTEXT:
The conversation history may include [Voice Memo Sent] entries. These indicate the user sent a voice recording that was processed. When users ask follow-up questions like:
- "What did you just create?"
- "Can you summarize what I said?"
- "What tasks came from that?"
Use the get_recent_voice_memo tool to get full details about the most recent recording and what was created.

CALENDAR CREATION:
When users ask to schedule something, use the create_calendar_event tool. You'll need:
- title: Event name
- start_time: ISO format (e.g., 2025-01-20T14:00:00)
- end_time: ISO format
- Optional: description, location, attendees (email addresses)

Always confirm details with the user before creating events. Use get_current_time first to know the current date/time for relative scheduling.

ABOUT THE USER:
Aaron is a German engineer currently based in Sydney, Australia, preparing to relocate to Singapore and Southeast Asia. He was the first employee at Algenie, an Australian biotech startup, and is currently in transition. His interests span climate tech, biotech, agritech, foodtech, and longevity. He records voice memos to capture thoughts, meetings, and reflections which are transcribed and stored in this system.

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
                            
                            logger.info(f"Tool call: {tool_name} with input: {json.dumps(tool_input)[:200]}")
                            tools_used.append(tool_name)
                            
                            # Execute the tool
                            result = execute_tool(tool_name, tool_input)
                            
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
