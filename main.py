import logging
from fastapi import FastAPI
from app.api.endpoints import router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Jarvis Intelligence Service",
    description="AI Analysis and Reasoning Service for Jarvis",
    version="1.0.0"
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Jarvis Intelligence Service Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
