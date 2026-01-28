import logging
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.api.endpoints import router
from app.core.config import settings


# Add a filter to inject request_id into log records
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True


# Configure logging with filter that handles missing request_id
_request_id_filter = RequestIdFilter()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # Removed request_id from format - use explicit logging
)

# Add filter to root logger and all existing loggers
root_logger = logging.getLogger()
root_logger.addFilter(_request_id_filter)
for handler in root_logger.handlers:
    handler.addFilter(_request_id_filter)


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


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce API key authentication on all endpoints.

    Excludes /health endpoint (for load balancer health checks) and root.
    Requires X-API-Key header with valid key from environment variable.
    """

    async def dispatch(self, request: Request, call_next):
        # Public endpoints that don't require authentication
        public_paths = ["/health", "/"]

        if request.url.path in public_paths:
            return await call_next(request)

        # Check if API key is configured - FAIL CLOSED
        expected_key = settings.INTELLIGENCE_SERVICE_API_KEY
        if not expected_key:
            logger = logging.getLogger("jarvis.auth")
            logger.error("INTELLIGENCE_SERVICE_API_KEY not set - rejecting request (fail-closed)")
            return JSONResponse(
                status_code=503,
                content={"detail": "Service authentication not configured"}
            )

        # Get API key from request headers
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            logger = logging.getLogger("jarvis.auth")
            logger.warning(f"Missing API key from {request.client.host} for {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key. Include X-API-Key header."}
            )

        if api_key != expected_key:
            logger = logging.getLogger("jarvis.auth")
            logger.warning(f"Invalid API key from {request.client.host} for {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"}
            )

        # API key is valid, proceed with request
        return await call_next(request)


app = FastAPI(
    title="Jarvis Intelligence Service",
    description="AI Analysis and Reasoning Service for Jarvis",
    version="1.0.0"
)

# Add CORS middleware for web chat access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # LibreChat dev server
        "http://localhost:3080",  # LibreChat alternative port
        "http://localhost:5173",  # Vite dev server
        "https://*.vercel.app",   # Vercel deployments
        # Add your production URL when deployed
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API key authentication middleware (processes before request ID)
app.add_middleware(APIKeyAuthMiddleware)

# Add request ID middleware
app.add_middleware(RequestIdMiddleware)

app.include_router(router, prefix="/api/v1")

# Also mount chat routes at /v1 for OpenAI compatibility (LibreChat, etc.)
from app.api.routes import chat as chat_routes
app.include_router(chat_routes.router, prefix="/v1")

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
