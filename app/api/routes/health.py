from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Simple health endpoint for monitoring."""
    return {"status": "healthy"}
