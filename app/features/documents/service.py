"""
Document Service - Store, manage, and extract from personal documents.

Features:
- Store documents with extracted text content (for search/AI use)
- Optional file storage (GCS) for attachments/downloads
- Memory seeding from document content
- Document type classification (CV, profile, application, notes)
"""

import logging
import os
import hashlib
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("Jarvis.Documents.Service")


class DocumentService:
    """
    Service for managing personal documents.
    
    Documents are stored in Supabase with:
    - Extracted text content (for search and AI context)
    - Metadata (title, type, format, etc.)
    - Optional file URL (for actual file storage in GCS)
    """
    
    _instance: Optional["DocumentService"] = None
    
    def __init__(self):
        """Initialize document service."""
        self._db = None
        self._storage = None  # GCS client for file storage
        self._bucket_name = os.getenv("GCS_DOCUMENTS_BUCKET", "jarvis-documents")
    
    def _ensure_db(self):
        """Lazy load database client."""
        if self._db is None:
            from app.core.database import supabase
            self._db = supabase
        return self._db
    
    async def store_document(
        self,
        content: str,
        title: str,
        document_type: str = "other",
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Store a document with extracted content.
        
        Args:
            content: Extracted text content (for search/AI)
            title: Document title
            document_type: One of: cv, profile, application, notes, other
            file_bytes: Optional raw file bytes to store
            filename: Original filename
            metadata: Additional metadata
            tags: Tags for categorization
            
        Returns:
            Document ID if successful
        """
        db = self._ensure_db()
        doc_id = str(uuid4())
        
        # Calculate content hash for deduplication
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        # Check for duplicate content
        existing = db.table("documents").select("id").eq(
            "content_hash", content_hash
        ).execute()
        
        if existing.data:
            logger.info(f"Document already exists with hash {content_hash}")
            return existing.data[0]["id"]
        
        # Prepare document record
        doc_record = {
            "id": doc_id,
            "title": title,
            "type": document_type,
            "content": content,
            "content_hash": content_hash,
            "filename": filename,
            "metadata": metadata or {},
            "tags": tags or [],
            "word_count": len(content.split()),
            "char_count": len(content),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Store file if provided
        if file_bytes and filename:
            file_url = await self._store_file(doc_id, file_bytes, filename)
            if file_url:
                doc_record["file_url"] = file_url
        
        try:
            db.table("documents").insert(doc_record).execute()
            logger.info(f"Stored document: {title} ({document_type}) - {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store document: {e}")
            return None
    
    async def _store_file(
        self,
        doc_id: str,
        file_bytes: bytes,
        filename: str
    ) -> Optional[str]:
        """
        Store file in GCS for future use (email attachments, etc.).
        
        Returns:
            Public URL or signed URL for the file
        """
        try:
            from google.cloud import storage
            
            if self._storage is None:
                self._storage = storage.Client()
            
            bucket = self._storage.bucket(self._bucket_name)
            
            # Create blob with path: documents/{doc_id}/{filename}
            blob_path = f"documents/{doc_id}/{filename}"
            blob = bucket.blob(blob_path)
            
            # Upload
            blob.upload_from_string(file_bytes)
            
            # Generate URL (could be signed URL for security)
            url = f"gs://{self._bucket_name}/{blob_path}"
            logger.info(f"Stored file: {url}")
            return url
            
        except ImportError:
            logger.warning("google-cloud-storage not installed, skipping file storage")
            return None
        except Exception as e:
            logger.error(f"Failed to store file: {e}")
            return None
    
    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        db = self._ensure_db()
        
        try:
            result = db.table("documents").select("*").eq("id", doc_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None
    
    async def list_documents(
        self,
        document_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List documents, optionally filtered by type."""
        db = self._ensure_db()
        
        try:
            query = db.table("documents").select(
                "id, title, type, filename, tags, word_count, created_at, updated_at"
            ).order("updated_at", desc=True).limit(limit)
            
            if document_type:
                query = query.eq("type", document_type)
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []
    
    async def search_documents(
        self,
        query: str,
        document_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search documents by content."""
        db = self._ensure_db()
        
        try:
            # Simple text search using ILIKE
            q = db.table("documents").select(
                "id, title, type, content, filename, tags"
            ).ilike("content", f"%{query}%").limit(limit)
            
            if document_type:
                q = q.eq("type", document_type)
            
            result = q.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            return []
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its file."""
        db = self._ensure_db()
        
        try:
            # Get document first to find file URL
            doc = await self.get_document(doc_id)
            
            # Delete from database
            db.table("documents").delete().eq("id", doc_id).execute()
            
            # Delete file from GCS if exists
            if doc and doc.get("file_url"):
                await self._delete_file(doc["file_url"])
            
            logger.info(f"Deleted document: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
    
    async def _delete_file(self, file_url: str) -> bool:
        """Delete file from GCS."""
        try:
            if not file_url.startswith("gs://"):
                return False
            
            from google.cloud import storage
            
            if self._storage is None:
                self._storage = storage.Client()
            
            # Parse gs:// URL
            path = file_url.replace(f"gs://{self._bucket_name}/", "")
            bucket = self._storage.bucket(self._bucket_name)
            blob = bucket.blob(path)
            blob.delete()
            
            logger.info(f"Deleted file: {file_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_url}: {e}")
            return False
    
    async def get_document_for_context(
        self,
        query: str,
        max_chars: int = 4000
    ) -> str:
        """
        Get relevant document content for AI context.
        
        Used by chat to inject document knowledge.
        """
        docs = await self.search_documents(query, limit=3)
        
        if not docs:
            return ""
        
        context_parts = []
        total_chars = 0
        
        for doc in docs:
            content = doc.get("content", "")
            title = doc.get("title", "Unknown")
            doc_type = doc.get("type", "document")
            
            # Truncate if needed
            remaining = max_chars - total_chars
            if remaining <= 0:
                break
            
            snippet = content[:remaining]
            context_parts.append(f"[{doc_type.upper()}: {title}]\n{snippet}")
            total_chars += len(snippet)
        
        return "\n\n".join(context_parts)
    
    async def seed_memories_from_document(
        self,
        doc_id: str,
    ) -> int:
        """
        Extract and store memories from a document.
        
        Uses Claude to extract facts, preferences, and relationships.
        Returns number of memories created.
        """
        doc = await self.get_document(doc_id)
        if not doc:
            return 0
        
        content = doc.get("content", "")
        title = doc.get("title", "")
        doc_type = doc.get("type", "other")
        
        if not content or len(content) < 50:
            return 0
        
        try:
            from app.features.memory import get_memory_service
            from app.services.llm import ClaudeMultiAnalyzer
            
            memory_service = get_memory_service()
            llm = ClaudeMultiAnalyzer()
            
            # Create extraction prompt based on document type
            type_instructions = {
                "cv": "Focus on work experience, skills, education, achievements, and career progression.",
                "profile": "Focus on personal background, interests, values, and self-description.",
                "application": "Focus on motivations, goals, qualifications, and what the person is seeking.",
                "notes": "Focus on key ideas, plans, and insights.",
            }
            
            extra_instruction = type_instructions.get(doc_type, "Extract key facts and insights.")
            
            prompt = f"""Analyze this personal document and extract key memorable facts about the author.

Document Type: {doc_type}
Document Title: {title}

{extra_instruction}

Extract:
1. Personal facts (background, education, skills, achievements)
2. Work history (companies, roles, responsibilities, accomplishments)
3. Goals and aspirations
4. Preferences and values
5. Key relationships mentioned

Return a JSON array of memories. Each should be:
- One clear sentence
- Third person: "Aaron..." or "User..."
- Specific with names, dates, numbers when present

Example:
[
  {{"type": "fact", "content": "Aaron graduated from TU Munich with a degree in Engineering"}},
  {{"type": "fact", "content": "Aaron worked at Algenie as co-founder from 2022-2024"}},
  {{"type": "preference", "content": "Aaron is passionate about AI and climate technology"}}
]

Return ONLY the JSON array. Extract UP TO 20 unique memories.

DOCUMENT:
{content[:8000]}"""

            response = llm.client.messages.create(
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
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    memories = json.loads(result_text[start:end])
            
            # Store memories
            from app.features.memory.service import MemoryType
            
            count = 0
            type_mapping = {
                "fact": MemoryType.FACT,
                "preference": MemoryType.PREFERENCE,
                "relationship": MemoryType.RELATIONSHIP,
                "insight": MemoryType.INSIGHT,
            }
            
            for mem in memories:
                mem_type = mem.get("type", "fact")
                mem_content = mem.get("content", "")
                
                if mem_content and len(mem_content) > 15:
                    await memory_service.add(
                        content=mem_content,
                        memory_type=type_mapping.get(mem_type, MemoryType.FACT),
                        metadata={
                            "source": f"document:{doc_id}",
                            "document_title": title,
                            "document_type": doc_type
                        }
                    )
                    count += 1
            
            logger.info(f"Seeded {count} memories from document: {title}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to seed memories from document {doc_id}: {e}")
            return 0
    
    async def get_file_for_attachment(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file data for email attachment or download.
        
        Returns dict with filename, content_type, and bytes.
        """
        doc = await self.get_document(doc_id)
        if not doc or not doc.get("file_url"):
            return None
        
        try:
            from google.cloud import storage
            
            if self._storage is None:
                self._storage = storage.Client()
            
            file_url = doc["file_url"]
            path = file_url.replace(f"gs://{self._bucket_name}/", "")
            
            bucket = self._storage.bucket(self._bucket_name)
            blob = bucket.blob(path)
            
            file_bytes = blob.download_as_bytes()
            
            return {
                "filename": doc.get("filename", "document"),
                "content": file_bytes,
                "content_type": blob.content_type or "application/octet-stream"
            }
        except Exception as e:
            logger.error(f"Failed to get file for document {doc_id}: {e}")
            return None


@lru_cache(maxsize=1)
def get_document_service() -> DocumentService:
    """Get the singleton document service instance."""
    if DocumentService._instance is None:
        DocumentService._instance = DocumentService()
    return DocumentService._instance
