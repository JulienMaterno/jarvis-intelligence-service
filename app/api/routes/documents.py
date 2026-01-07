"""
Documents API Routes

Endpoints for:
- Uploading documents (PDF, MD, TXT)
- Listing and searching documents
- Getting document content
- Seeding memories from documents
- Getting files for attachments
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field

from app.features.documents import get_document_service, DocumentExtractor

router = APIRouter(tags=["Documents"])
logger = logging.getLogger("Jarvis.API.Documents")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class DocumentItem(BaseModel):
    """A document summary item."""
    id: str
    title: str
    type: str
    filename: Optional[str] = None
    tags: List[str] = []
    word_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentDetail(BaseModel):
    """Full document details including content."""
    id: str
    title: str
    type: str
    content: str
    filename: Optional[str] = None
    file_url: Optional[str] = None
    metadata: dict = {}
    tags: List[str] = []
    word_count: int = 0
    char_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Response with list of documents."""
    status: str
    count: int
    documents: List[DocumentItem]


class DocumentResponse(BaseModel):
    """Response for document operations."""
    status: str
    document_id: Optional[str] = None
    message: Optional[str] = None


class AddDocumentTextRequest(BaseModel):
    """Request to add a document from text content."""
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document text content")
    document_type: str = Field(
        default="other",
        description="Type: cv, profile, application, notes, other"
    )
    tags: List[str] = Field(default=[], description="Tags for categorization")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "My Professional Bio",
                "content": "I am a software engineer with 5 years of experience...",
                "document_type": "profile",
                "tags": ["bio", "professional"]
            }
        }


class SearchDocumentsRequest(BaseModel):
    """Request to search documents."""
    query: str = Field(..., description="Search query")
    document_type: Optional[str] = Field(default=None, description="Filter by type")
    limit: int = Field(default=10, ge=1, le=50)


class SeedMemoriesRequest(BaseModel):
    """Request to seed memories from a document."""
    document_id: str = Field(..., description="ID of the document to seed from")


# ============================================================================
# DOCUMENT ENDPOINTS
# ============================================================================

@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated
    seed_memories: bool = Form(True),
):
    """
    Upload a document file (PDF, MD, TXT, DOCX).
    
    The document will be:
    1. Parsed to extract text content
    2. Stored in the database with metadata
    3. Optionally stored as a file (for future email attachments)
    4. Optionally seeded into memories (default: yes)
    
    Args:
        file: The document file
        title: Optional title (auto-extracted if not provided)
        document_type: Optional type (auto-detected if not provided)
        tags: Optional comma-separated tags
        seed_memories: Whether to extract memories from document (default: true)
    """
    doc_service = get_document_service()
    
    try:
        # Read file
        file_bytes = await file.read()
        filename = file.filename or "unknown"
        
        # Extract content
        content, metadata = DocumentExtractor.extract(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=file.content_type
        )
        
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"Could not extract content from file: {metadata.get('error', 'Unknown error')}"
            )
        
        # Determine title
        doc_title = title or metadata.get("title") or filename.rsplit(".", 1)[0]
        
        # Determine type
        if document_type:
            doc_type = document_type
        else:
            doc_type = DocumentExtractor.infer_document_type(filename, content)
        
        # Parse tags
        tag_list = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        
        # Store document
        doc_id = await doc_service.store_document(
            content=content,
            title=doc_title,
            document_type=doc_type,
            file_bytes=file_bytes,
            filename=filename,
            metadata=metadata,
            tags=tag_list,
        )
        
        if not doc_id:
            raise HTTPException(status_code=500, detail="Failed to store document")
        
        # Seed memories in background
        if seed_memories:
            background_tasks.add_task(
                doc_service.seed_memories_from_document,
                doc_id
            )
        
        logger.info(f"Uploaded document: {doc_title} ({doc_type}) - {doc_id}")
        
        return DocumentResponse(
            status="success",
            document_id=doc_id,
            message=f"Document '{doc_title}' uploaded ({len(content)} chars extracted)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/text", response_model=DocumentResponse)
async def add_document_text(
    request: AddDocumentTextRequest,
    background_tasks: BackgroundTasks,
    seed_memories: bool = True,
):
    """
    Add a document from plain text content.
    
    Use this for pasting content directly without a file upload.
    """
    doc_service = get_document_service()
    
    try:
        doc_id = await doc_service.store_document(
            content=request.content,
            title=request.title,
            document_type=request.document_type,
            tags=request.tags,
        )
        
        if not doc_id:
            raise HTTPException(status_code=500, detail="Failed to store document")
        
        # Seed memories in background
        if seed_memories:
            background_tasks.add_task(
                doc_service.seed_memories_from_document,
                doc_id
            )
        
        return DocumentResponse(
            status="success",
            document_id=doc_id,
            message=f"Document '{request.title}' added"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to add document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    document_type: Optional[str] = None,
    limit: int = 50
):
    """
    List all documents.
    
    Args:
        document_type: Filter by type (cv, profile, application, notes, other)
        limit: Maximum documents to return
    """
    doc_service = get_document_service()
    
    try:
        docs = await doc_service.list_documents(
            document_type=document_type,
            limit=limit
        )
        
        items = [DocumentItem(**doc) for doc in docs]
        
        return DocumentListResponse(
            status="success",
            count=len(items),
            documents=items
        )
        
    except Exception as e:
        logger.exception("Failed to list documents")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str):
    """Get a document by ID, including full content."""
    doc_service = get_document_service()
    
    try:
        doc = await doc_service.get_document(document_id)
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return DocumentDetail(**doc)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get document {document_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/search", response_model=DocumentListResponse)
async def search_documents(request: SearchDocumentsRequest):
    """Search documents by content."""
    doc_service = get_document_service()
    
    try:
        docs = await doc_service.search_documents(
            query=request.query,
            document_type=request.document_type,
            limit=request.limit
        )
        
        items = []
        for doc in docs:
            items.append(DocumentItem(
                id=doc.get("id", ""),
                title=doc.get("title", ""),
                type=doc.get("type", "other"),
                filename=doc.get("filename"),
                tags=doc.get("tags", []),
            ))
        
        return DocumentListResponse(
            status="success",
            count=len(items),
            documents=items
        )
        
    except Exception as e:
        logger.exception("Failed to search documents")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}", response_model=DocumentResponse)
async def delete_document(document_id: str):
    """Delete a document and its stored file."""
    doc_service = get_document_service()
    
    try:
        deleted = await doc_service.delete_document(document_id)
        
        if deleted:
            return DocumentResponse(
                status="success",
                document_id=document_id,
                message="Document deleted"
            )
        else:
            raise HTTPException(status_code=404, detail="Document not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete document {document_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/seed-memories", response_model=DocumentResponse)
async def seed_memories_from_document(document_id: str):
    """
    Extract and store memories from a document.
    
    Uses Claude to extract facts, preferences, and relationships
    from the document content and stores them in the memory system.
    """
    doc_service = get_document_service()
    
    try:
        # Verify document exists
        doc = await doc_service.get_document(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Seed memories
        count = await doc_service.seed_memories_from_document(document_id)
        
        return DocumentResponse(
            status="success",
            document_id=document_id,
            message=f"Extracted {count} memories from document"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to seed memories from document {document_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: str):
    """
    Get just the text content of a document.
    
    Useful for quick content retrieval without full metadata.
    """
    doc_service = get_document_service()
    
    try:
        doc = await doc_service.get_document(document_id)
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {
            "document_id": document_id,
            "title": doc.get("title"),
            "content": doc.get("content", "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get document content {document_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/types/summary")
async def get_documents_by_type():
    """
    Get a summary of documents by type.
    
    Returns count of documents for each type.
    """
    doc_service = get_document_service()
    
    try:
        # Get all documents
        all_docs = await doc_service.list_documents(limit=1000)
        
        # Count by type
        type_counts = {}
        for doc in all_docs:
            doc_type = doc.get("type", "other")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        return {
            "status": "success",
            "total": len(all_docs),
            "by_type": type_counts
        }
        
    except Exception as e:
        logger.exception("Failed to get documents by type")
        raise HTTPException(status_code=500, detail=str(e))
