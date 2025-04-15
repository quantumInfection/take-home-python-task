import os
from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import router
from app.db import get_db_client, close_db_connection

# Initialize FastAPI app
app = FastAPI(
    title="Bittensor API Service",
    description="""API for querying Tao dividends with caching capabilities.
    
## Authentication
This API requires an API key for all endpoints. 
To authenticate, include the `X-API-Key` header in your requests:

```
X-API-Key: your_api_key_here
```

The API key should be set as the `API_KEY` environment variable on the server.
""",
    version="0.1.0",
)

# Include API router
app.include_router(router, prefix="/api/v1")


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint to verify API is running"""
    return {"status": "healthy"}


# Database startup and shutdown event handlers
@app.on_event("startup")
async def startup_db_client():
    """Initialize database connection on startup"""
    await get_db_client()
    print("MongoDB connection established")


@app.on_event("shutdown")
async def shutdown_db_client():
    """Close database connection on shutdown"""
    await close_db_connection()
    print("MongoDB connection closed")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
