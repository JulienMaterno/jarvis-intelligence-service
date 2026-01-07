"""
Memory Service - Centralized AI Memory using Mem0

This service provides persistent memory that's accessible across ALL features:
- Chat: Remembers past conversations, user preferences
- Transcript Processing: Extracts and stores key facts from voice memos
- Briefings: Uses memory to provide context for meetings
- Journaling: Remembers patterns, goals, and progress

Architecture:
- Uses Mem0 with Qdrant vector store for semantic search
- Mem0's built-in conflict resolution handles duplicates and updates
- Falls back to in-memory store if Qdrant unavailable
- Integrates with Claude for memory extraction

Key Features:
- AUTOMATIC DEDUPLICATION: Mem0 handles duplicates via conflict resolution
- AUTOMATIC UPDATES: New facts about same topic update existing memories
- SEMANTIC SEARCH: Find relevant memories by meaning, not keywords

Memory Types:
1. FACTS - Persistent user information (preferences, background, relationships)
2. INTERACTIONS - Meeting summaries, key conversation points
3. INSIGHTS - Patterns, observations, learned behaviors
"""

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Jarvis.Memory")


class MemoryType(Enum):
    """Types of memories stored."""
    FACT = "fact"  # User facts: "User is vegetarian", "Works at Algenie"
    INTERACTION = "interaction"  # Meeting/conversation summaries
    INSIGHT = "insight"  # Patterns and observations
    PREFERENCE = "preference"  # User preferences
    RELATIONSHIP = "relationship"  # Info about contacts/relationships


class MemoryService:
    """
    Centralized memory service using Mem0.
    
    Provides semantic memory across all Jarvis features.
    Designed to be a singleton - use get_memory_service().
    """
    
    _instance: Optional["MemoryService"] = None
    _initialized: bool = False
    
    def __init__(self):
        """Initialize memory service with Mem0."""
        self.user_id = os.getenv("JARVIS_USER_ID", "aaron")
        self._memory = None
        self._fallback_memories: List[Dict] = []  # In-memory fallback
        self._use_fallback = False
        
    def _ensure_initialized(self) -> None:
        """Lazy initialization of Mem0 client."""
        if self._initialized:
            return
            
        try:
            from mem0 import Memory
            
            # Configure Mem0 with Anthropic LLM
            # Use Haiku for cost-efficiency (memory extraction happens frequently)
            # Sonnet is used in chat for higher quality responses
            config = {
                "llm": {
                    "provider": "anthropic",
                    "config": {
                        "model": os.getenv("MEM0_LLM_MODEL", "claude-3-5-haiku-20241022"),
                        "api_key": os.getenv("ANTHROPIC_API_KEY"),
                    }
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                    }
                },
            }
            
            # Vector store: Prefer Supabase/pgvector, fall back to Qdrant, then in-memory
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_db_password = os.getenv("SUPABASE_DB_PASSWORD")
            
            if supabase_url and supabase_db_password:
                # Extract project ref from Supabase URL (https://xxx.supabase.co -> xxx)
                import re
                match = re.search(r'https://([^.]+)\.supabase\.co', supabase_url)
                if match:
                    project_ref = match.group(1)
                    # Use Session Pooler for IPv4 compatibility (Cloud Run is IPv4-only)
                    # Format: postgresql://postgres.[project_ref]:[password]@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres
                    pooler_host = os.getenv("SUPABASE_POOLER_HOST", "aws-1-ap-southeast-2.pooler.supabase.com")
                    pooler_port = os.getenv("SUPABASE_POOLER_PORT", "5432")
                    
                    # Supabase pooler uses postgres.{project_ref} as the username
                    username = f"postgres.{project_ref}"
                    
                    # Log sanitized version (hide password)
                    logger.info(f"pgvector connection: {username}@{pooler_host}:{pooler_port}/postgres")
                    
                    # Pass parameters separately to avoid connection string parsing issues
                    # Mem0's pgvector accepts: user, password, host, port, dbname
                    # Note: Don't pass sslmode - Supabase pooler handles SSL automatically
                    config["vector_store"] = {
                        "provider": "pgvector",
                        "config": {
                            "user": username,
                            "password": supabase_db_password,
                            "host": pooler_host,
                            "port": int(pooler_port),
                            "dbname": "postgres",
                            "collection_name": "mem0_memories",
                            "embedding_model_dims": 1536,  # text-embedding-3-small
                            "hnsw": True,
                            "diskann": False,
                        }
                    }
                    logger.info(f"Mem0 configured with Supabase pgvector via Session Pooler (project: {project_ref})")
                else:
                    logger.warning(f"Could not parse Supabase URL: {supabase_url}")
            
            # Fall back to Qdrant if configured
            elif os.getenv("QDRANT_URL"):
                config["vector_store"] = {
                    "provider": "qdrant",
                    "config": {
                        "url": os.getenv("QDRANT_URL"),
                        "api_key": os.getenv("QDRANT_API_KEY"),
                        "collection_name": "jarvis_memories",
                    }
                }
                logger.info(f"Mem0 configured with Qdrant at {os.getenv('QDRANT_URL')}")
            else:
                logger.warning("Mem0 using in-memory vector store (no SUPABASE_DB_PASSWORD or QDRANT_URL)")
            
            self._memory = Memory.from_config(config)
            self._initialized = True
            logger.info("Memory service initialized successfully")
            
        except ImportError:
            logger.warning("mem0 not installed, using fallback in-memory storage")
            self._use_fallback = True
            self._memory = None
            self._initialized = True
        except Exception as e:
            import traceback
            logger.error(f"Failed to initialize Mem0: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self._use_fallback = True
            self._memory = None
            self._initialized = True
    
    # =========================================================================
    # CORE MEMORY OPERATIONS
    # =========================================================================
    
    async def add(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.FACT,
        metadata: Optional[Dict[str, Any]] = None,
        infer: bool = True,
    ) -> Optional[str]:
        """
        Add a memory using Mem0's intelligent processing.
        
        When infer=True (default), Mem0 will:
        1. Extract structured information from the content
        2. Check for existing memories about the same topic
        3. Update/merge if duplicate or conflicting info exists
        4. Store only truly new information
        
        Args:
            content: The memory content (natural language)
            memory_type: Type categorization
            metadata: Additional metadata (source, date, etc.)
            infer: If True (default), Mem0 handles deduplication automatically
            
        Returns:
            Memory ID if successful, None otherwise
        """
        self._ensure_initialized()
        
        meta = metadata or {}
        meta["type"] = memory_type.value
        meta["added_at"] = datetime.now(timezone.utc).isoformat()
        
        try:
            if self._use_fallback:
                mem_id = f"mem_{len(self._fallback_memories)}"
                self._fallback_memories.append({
                    "id": mem_id,
                    "content": content,
                    "metadata": meta,
                })
                logger.debug(f"Added fallback memory: {content[:50]}...")
                return mem_id
            
            # Add via Mem0 with inference enabled for automatic deduplication
            # Mem0's conflict resolution will:
            # - Skip true duplicates
            # - Update existing memories with new info
            # - Resolve contradictions (new info wins)
            result = self._memory.add(
                messages=[{"role": "user", "content": content}],
                user_id=self.user_id,
                metadata=meta,
                infer=infer,  # Enable Mem0's smart processing
            )
            
            if result and "results" in result:
                mem_id = result["results"][0].get("id") if result["results"] else None
                event = result["results"][0].get("event", "ADD") if result["results"] else "ADD"
                logger.info(f"Memory [{event}] [{memory_type.value}]: {content[:50]}...")
                return mem_id
                
            return None
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return None
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories semantically.
        
        Args:
            query: Natural language search query
            limit: Maximum results to return
            memory_type: Filter by memory type
            
        Returns:
            List of matching memories with scores
        """
        self._ensure_initialized()
        
        try:
            if self._use_fallback:
                # Simple keyword search for fallback
                query_lower = query.lower()
                matches = []
                for mem in self._fallback_memories:
                    if query_lower in mem["content"].lower():
                        matches.append({
                            "id": mem["id"],
                            "memory": mem["content"],
                            "metadata": mem["metadata"],
                            "score": 0.8,
                        })
                return matches[:limit]
            
            # Search via Mem0
            filters = {"user_id": self.user_id}
            if memory_type:
                filters["type"] = memory_type.value
            
            result = self._memory.search(
                query=query,
                user_id=self.user_id,
                limit=limit,
            )
            
            memories = result.get("results", []) if result else []
            logger.debug(f"Found {len(memories)} memories for query: {query[:30]}...")
            return memories
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
    
    async def update(self, memory_id: str, new_content: str) -> bool:
        """
        Update an existing memory with new content.
        
        Use this to correct incorrect memories or add details.
        
        Args:
            memory_id: The ID of the memory to update
            new_content: The corrected/updated content
            
        Returns:
            True if successful
        """
        self._ensure_initialized()
        
        try:
            if self._use_fallback:
                for mem in self._fallback_memories:
                    if mem["id"] == memory_id:
                        mem["content"] = new_content
                        mem["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
                        return True
                return False
            
            # Use Mem0's native update
            self._memory.update(memory_id=memory_id, data=new_content)
            logger.info(f"Updated memory {memory_id}: {new_content[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update memory {memory_id}: {e}")
            return False
    
    async def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all memories for the user."""
        self._ensure_initialized()
        
        try:
            if self._use_fallback:
                return self._fallback_memories[:limit]
            
            result = self._memory.get_all(user_id=self.user_id, limit=limit)
            return result.get("results", []) if result else []
            
        except Exception as e:
            logger.error(f"Failed to get all memories: {e}")
            return []
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        self._ensure_initialized()
        
        try:
            if self._use_fallback:
                self._fallback_memories = [
                    m for m in self._fallback_memories if m["id"] != memory_id
                ]
                return True
            
            self._memory.delete(memory_id=memory_id)
            logger.info(f"Deleted memory: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    # =========================================================================
    # HIGH-LEVEL MEMORY METHODS (Used by Features)
    # =========================================================================
    
    async def remember_fact(self, fact: str, source: Optional[str] = None) -> Optional[str]:
        """
        Remember a fact about the user.
        
        Examples:
            - "User is vegetarian"
            - "User works in biotech"
            - "User is moving to Singapore"
        """
        metadata = {"source": source} if source else {}
        return await self.add(fact, MemoryType.FACT, metadata)
    
    async def remember_interaction(
        self,
        summary: str,
        contact_name: Optional[str] = None,
        interaction_date: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[str]:
        """
        Remember an interaction/meeting summary.
        
        Examples:
            - "Met with John Smith about Algenie funding - discussed Series A timeline"
            - "Call with recruiter about Singapore opportunities"
        """
        metadata = {
            "contact": contact_name,
            "date": interaction_date,
            "source": source,
        }
        return await self.add(summary, MemoryType.INTERACTION, {k: v for k, v in metadata.items() if v})
    
    async def remember_preference(
        self,
        preference: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Remember a user preference.
        
        Examples:
            - "Prefers morning meetings"
            - "Uses German for personal notes"
        """
        metadata = {"category": category} if category else {}
        return await self.add(preference, MemoryType.PREFERENCE, metadata)
    
    async def remember_relationship(
        self,
        relationship_info: str,
        contact_name: str,
    ) -> Optional[str]:
        """
        Remember information about a relationship/contact.
        
        Examples:
            - "John is CTO at Algenie, known since 2023"
            - "Sarah is career coach, meets monthly"
        """
        return await self.add(
            relationship_info,
            MemoryType.RELATIONSHIP,
            {"contact": contact_name},
        )
    
    async def get_context(
        self,
        query: str,
        limit: int = 5,
        include_types: Optional[List[MemoryType]] = None,
    ) -> str:
        """
        Get relevant memory context for a query.
        
        Used by all features to inject memory into prompts.
        Returns a formatted string ready for system prompts.
        
        Args:
            query: The context to search for
            limit: Max memories to include
            include_types: Filter to specific memory types
            
        Returns:
            Formatted string of relevant memories
        """
        memories = await self.search(query, limit=limit)
        
        if not memories:
            return ""
        
        # Filter by types if specified
        if include_types:
            type_values = {t.value for t in include_types}
            memories = [
                m for m in memories
                if m.get("metadata", {}).get("type") in type_values
            ]
        
        # Format for prompt injection
        lines = []
        for mem in memories:
            memory_text = mem.get("memory", "")
            if memory_text:
                lines.append(f"• {memory_text}")
        
        return "\n".join(lines) if lines else ""
    
    async def get_contact_context(self, contact_name: str) -> str:
        """
        Get all memories related to a specific contact.
        
        Useful for meeting briefings and conversation context.
        """
        memories = await self.search(contact_name, limit=10)
        
        if not memories:
            return ""
        
        lines = []
        for mem in memories:
            memory_text = mem.get("memory", "")
            mem_type = mem.get("metadata", {}).get("type", "fact")
            if memory_text:
                lines.append(f"• [{mem_type}] {memory_text}")
        
        return "\n".join(lines) if lines else ""
    
    # =========================================================================
    # BULK OPERATIONS (For Initial Seeding)
    # =========================================================================
    
    async def seed_from_transcript_analysis(
        self,
        analysis: Dict[str, Any],
        source_file: str,
    ) -> int:
        """
        Extract and store memories from a transcript analysis.
        
        Called after transcript processing to build memory over time.
        This is the PRIMARY mechanism for ongoing memory growth.
        
        Args:
            analysis: The Claude analysis result
            source_file: Source filename for tracking
            
        Returns:
            Number of memories added
        """
        count = 0
        
        # Extract from meetings - key relationship touchpoints
        for meeting in analysis.get("meetings", []):
            summary = meeting.get("summary", "")
            title = meeting.get("title", "")
            contact = meeting.get("contact_name", "")
            topics = meeting.get("topics_discussed", [])
            
            if summary and contact:
                await self.remember_interaction(
                    f"Meeting with {contact}: {title} - {summary[:200]}",
                    contact_name=contact,
                    source=source_file,
                )
                count += 1
                
                # Also remember topics discussed with this person
                if topics and isinstance(topics, list):
                    topic_str = ", ".join(topics[:5])
                    await self.remember_relationship(
                        f"Discussed with {contact}: {topic_str}",
                        contact_name=contact,
                    )
                    count += 1
        
        # Extract from CRM updates (relationship facts)
        for crm in analysis.get("crm_updates", []):
            contact_name = crm.get("contact_name", "")
            updates = crm.get("updates", {})
            
            for field, value in updates.items():
                if value and field in ["company", "position", "notes", "job_title"]:
                    await self.remember_relationship(
                        f"{contact_name}: {field} is {value}",
                        contact_name=contact_name,
                    )
                    count += 1
        
        # Extract from journals - daily insights and patterns
        for journal in analysis.get("journals", []):
            mood = journal.get("mood", "")
            wins = journal.get("wins", [])
            challenges = journal.get("challenges", [])
            tomorrow_focus = journal.get("tomorrow_focus", [])
            
            # Store notable achievements
            if wins and isinstance(wins, list):
                for win in wins[:2]:  # Top 2 wins
                    await self.remember_fact(
                        f"Achievement: {win}",
                        source=source_file,
                    )
                    count += 1
            
            # Store recurring challenges (insights)
            if challenges and isinstance(challenges, list):
                for challenge in challenges[:1]:
                    await self.add(
                        f"Challenge noted: {challenge}",
                        MemoryType.INSIGHT,
                        metadata={"source": source_file}
                    )
                    count += 1
        
        # Extract key facts from reflections
        for reflection in analysis.get("reflections", []):
            title = reflection.get("title", "")
            content = reflection.get("content", "")[:300]
            tags = reflection.get("tags", [])
            
            # Store reflection insights
            if title and content:
                await self.add(
                    f"Reflection on {title}: {content}",
                    MemoryType.INSIGHT,
                    metadata={"source": source_file, "tags": tags}
                )
                count += 1
        
        # Extract tasks as potential commitments/plans
        for task in analysis.get("tasks", []):
            title = task.get("title", "")
            priority = task.get("priority", "")
            
            # Only remember high-priority commitments
            if title and priority == "high":
                await self.remember_fact(
                    f"Committed to: {title}",
                    source=source_file,
                )
                count += 1
        
        logger.info(f"Seeded {count} memories from transcript analysis ({source_file})")
        return count
    
    async def seed_from_existing_data(
        self,
        meetings: List[Dict],
        contacts: List[Dict],
        reflections: List[Dict],
    ) -> int:
        """
        Bulk seed memories from existing database records.
        
        Used for initial setup to populate memory from historical data.
        Quality filters ensure only meaningful information is stored.
        Mem0's deduplication handles duplicates automatically.
        
        Args:
            meetings: List of meeting records from Supabase
            contacts: List of contact records
            reflections: List of reflection records
            
        Returns:
            Number of memories added
        """
        count = 0
        
        # Seed from contacts (relationships) - filter for quality
        for contact in contacts[:50]:  # Limit to avoid overload
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            company = contact.get("company", "")
            position = contact.get("position", "") or contact.get("job_title", "")
            notes = contact.get("notes", "")
            
            # Skip contacts without meaningful info
            if not name or len(name) < 2:
                continue
                
            # Build a comprehensive relationship description
            if position and company:
                info = f"{name} is {position} at {company}"
                await self.remember_relationship(info, name)
                count += 1
            elif position:
                info = f"{name} is {position}"
                await self.remember_relationship(info, name)
                count += 1
            elif company:
                info = f"{name} works at {company}"
                await self.remember_relationship(info, name)
                count += 1
            
            # Only add notes if they're meaningful text (not just IDs or short strings)
            if notes and len(notes) > 10 and not notes.isdigit():
                # Filter out notes that look like system IDs
                if not any(c.isdigit() for c in notes[:5]) or len(notes) > 20:
                    await self.remember_relationship(
                        f"About {name}: {notes[:200]}",
                        name,
                    )
                    count += 1
        
        # Seed from recent meetings (interactions) - with quality filter
        for meeting in meetings[:30]:  # Recent meetings
            title = meeting.get("title", "")
            summary = meeting.get("summary", "")
            contact = meeting.get("contact_name", "")
            date = meeting.get("date", "")
            topics = meeting.get("topics_discussed", [])
            
            # Skip meetings without meaningful content
            if not summary or len(summary) < 20:
                continue
            
            # Build comprehensive meeting memory
            if contact:
                meeting_mem = f"Meeting '{title}' with {contact}: {summary[:200]}"
                await self.remember_interaction(
                    meeting_mem,
                    contact_name=contact,
                    interaction_date=date,
                    source="historical_data",
                )
                count += 1
                
                # Also store topics discussed with this person
                if topics and isinstance(topics, list) and len(topics) > 0:
                    topic_str = ", ".join(str(t) for t in topics[:5] if t)
                    if topic_str:
                        await self.remember_relationship(
                            f"Discussed with {contact}: {topic_str}",
                            contact_name=contact,
                        )
                        count += 1
            else:
                # Meeting without specific contact
                await self.remember_interaction(
                    f"Meeting '{title}': {summary[:200]}",
                    source="historical_data",
                )
                count += 1
        
        logger.info(f"Bulk seeded {count} memories from existing data")
        return count
    
    async def seed_from_raw_transcript(
        self,
        transcript_text: str,
        source_file: str,
        llm_client=None,
    ) -> int:
        """
        Extract and store memories from raw transcript text using Claude.
        
        This is for historical seeding - analyzes the transcript with Claude
        to extract memorable facts, preferences, and relationships.
        Mem0's automatic deduplication prevents storing duplicates.
        
        Args:
            transcript_text: The raw transcript text
            source_file: Source filename for tracking
            llm_client: Optional Claude client (will create one if not provided)
            
        Returns:
            Number of memories added
        """
        if not transcript_text or len(transcript_text) < 100:
            return 0
        
        try:
            # Create LLM client if not provided
            if llm_client is None:
                from app.services.llm import ClaudeMultiAnalyzer
                llm_client = ClaudeMultiAnalyzer()
            
            # Ask Claude to extract memorable information - comprehensive prompt
            prompt = f"""Analyze this voice memo transcript and extract ALL key memorable information.

The speaker is Aaron, the user of this AI assistant. Extract information that would help an AI assistant be more helpful and personalized in future conversations.

EXTRACT THESE CATEGORIES:

1. **FACTS** - Concrete information about the user:
   - Current location, places lived, travel plans
   - Work history, companies, roles, projects
   - Education, skills, languages spoken
   - Health, fitness goals, routines
   - Financial information (budgets, goals)

2. **PREFERENCES** - How the user likes things:
   - Work style, meeting times, communication preferences
   - Food preferences, dietary restrictions
   - Travel style, accommodation preferences
   - Learning style, reading habits
   - Social preferences

3. **RELATIONSHIPS** - People mentioned:
   - Name, role, company, how they know each other
   - Nature of relationship (friend, colleague, mentor, etc.)
   - Recent interactions or plans

4. **INSIGHTS** - Observations and learnings:
   - Market insights, industry observations
   - Personal realizations, life lessons
   - Cultural observations from travel

5. **GOALS & PLANS** - What user wants to achieve:
   - Short-term plans (this week, month)
   - Long-term aspirations
   - Projects being worked on

FORMAT: Return a JSON array. Each memory should be:
- ONE clear sentence
- Third person: "User..." or "Aaron..."
- Specific with names, numbers, dates when mentioned
- Unique information (not repeated)

Example:
[
  {{"type": "fact", "content": "User is originally from Germany and studied engineering"}},
  {{"type": "relationship", "content": "Ed Henderson is a friend from Sydney who is interested in robotics"}},
  {{"type": "preference", "content": "User prefers living in hacker houses with other startup founders"}},
  {{"type": "insight", "content": "Indonesian market is complex - like having Nigeria and Singapore in one country"}},
  {{"type": "fact", "content": "User's current body weight goal is to stay around 80kg"}}
]

Return ONLY the JSON array. Extract UP TO 15 unique, valuable memories.

TRANSCRIPT:
{transcript_text[:6000]}"""
            
            response = llm_client.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse JSON
            import json
            memories = []
            if result_text.startswith("["):
                memories = json.loads(result_text)
            else:
                # Try to extract JSON from response
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    memories = json.loads(result_text[start:end])
            
            # Store extracted memories - Mem0 handles deduplication
            count = 0
            type_mapping = {
                "fact": MemoryType.FACT,
                "preference": MemoryType.PREFERENCE,
                "relationship": MemoryType.RELATIONSHIP,
                "insight": MemoryType.INSIGHT,
            }
            
            for mem in memories:
                mem_type = mem.get("type", "fact")
                content = mem.get("content", "")
                
                # Quality filter - skip very short or empty content
                if content and len(content) > 15:
                    await self.add(
                        content=content,
                        memory_type=type_mapping.get(mem_type, MemoryType.FACT),
                        metadata={"source": source_file, "extracted_from": "transcript"},
                        infer=True,  # Let Mem0 handle deduplication
                    )
                    count += 1
            
            logger.info(f"Extracted {count} memories from transcript: {source_file}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to extract memories from transcript {source_file}: {e}")
            return 0

    async def extract_from_text(
        self,
        text: str,
        source: str = "chat",
        source_id: Optional[str] = None,
    ) -> int:
        """
        Extract memories from arbitrary text (chat messages, etc.).
        
        This is a lighter-weight version of seed_from_raw_transcript,
        designed for shorter text snippets like chat conversations.
        
        Args:
            text: The text to extract from
            source: Source identifier (e.g., "beeper", "chat")
            source_id: Optional ID for tracking (e.g., chat_id)
            
        Returns:
            Number of memories extracted
        """
        if not text or len(text) < 30:
            return 0
            
        try:
            from app.services.llm import ClaudeMultiAnalyzer
            llm = ClaudeMultiAnalyzer()
            
            prompt = f"""Extract key facts from this conversation that would help personalize future interactions.

Focus on:
- Facts about people mentioned (names, roles, companies, relationships)
- User preferences or opinions expressed
- Important dates, events, or plans
- Key decisions or commitments made

Return a JSON array of memories. Each should be ONE clear sentence in third person.
Maximum 5 memories. Only extract truly valuable, specific information.

Example:
[
  {{"type": "fact", "content": "John Smith works at Google as a product manager"}},
  {{"type": "relationship", "content": "Sarah is John's wife who works in healthcare"}}
]

Return ONLY the JSON array, or empty array [] if nothing valuable to extract.

TEXT:
{text[:2000]}"""
            
            response = llm.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            import json
            memories = []
            if result_text.startswith("["):
                memories = json.loads(result_text)
            else:
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    memories = json.loads(result_text[start:end])
            
            type_mapping = {
                "fact": MemoryType.FACT,
                "preference": MemoryType.PREFERENCE,
                "relationship": MemoryType.RELATIONSHIP,
                "insight": MemoryType.INSIGHT,
            }
            
            count = 0
            for mem in memories:
                content = mem.get("content", "")
                mem_type = mem.get("type", "fact")
                
                if content and len(content) > 15:
                    metadata = {"source": source}
                    if source_id:
                        metadata["source_id"] = source_id
                    
                    await self.add(
                        content=content,
                        memory_type=type_mapping.get(mem_type, MemoryType.FACT),
                        metadata=metadata,
                        infer=True,
                    )
                    count += 1
            
            logger.info(f"Extracted {count} memories from {source}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to extract memories from text: {e}")
            return 0

    def is_available(self) -> bool:
        """Check if memory service is available."""
        self._ensure_initialized()
        return self._initialized


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    """Get the singleton memory service instance."""
    if MemoryService._instance is None:
        MemoryService._instance = MemoryService()
    return MemoryService._instance

# Updated 2026-01-07 15:35
# v2
