import logging
import uuid
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.api.endpoints import router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s'
)

# Add a filter to inject request_id into log records
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True

# Add filter to root logger
logging.getLogger().addFilter(RequestIdFilter())


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request ID tracing for distributed debugging.
    
    Uses X-Request-ID header if provided (for cross-service tracing),
    otherwise generates a new UUID.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        
        # Store in request state for access in endpoints
        request.state.request_id = request_id
        
        # Create a logging adapter for this request
        logger = logging.getLogger("jarvis.request")
        logger.info(f"[{request_id}] {request.method} {request.url.path}", extra={"request_id": request_id})
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers for debugging
        response.headers["X-Request-ID"] = request_id
        
        return response


app = FastAPI(
    title="Jarvis Intelligence Service",
    description="AI Analysis and Reasoning Service for Jarvis",
    version="1.0.0"
)

# Add request ID middleware
app.add_middleware(RequestIdMiddleware)

app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Jarvis Intelligence Service Running"}

@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "healthy", "service": "jarvis-intelligence-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
