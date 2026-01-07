"""
Documents Feature - Personal Document Storage and Extraction

Stores user documents (CV, profiles, applications) with:
- Raw file storage (GCS) for future use (email attachments, etc.)
- Extracted text content for search and memory
- Metadata extraction (title, type, dates)
- Integration with memory system for seeding facts
"""

from app.features.documents.service import DocumentService, get_document_service
from app.features.documents.extractor import DocumentExtractor

__all__ = ["DocumentService", "get_document_service", "DocumentExtractor"]
