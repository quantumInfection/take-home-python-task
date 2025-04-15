from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
import os
from app.core.config import settings

# API key header extractor
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Get API key from environment variable
def get_api_key():
    return os.getenv("API_KEY")

async def get_api_key_from_header(api_key_header: str = Security(API_KEY_HEADER)):
    """
    Validate the API key from the X-API-Key header
    """
    if api_key_header is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key header is missing",
        )
    
    if not settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API Key not configured on server",
        )
    
    if api_key_header != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    
    return api_key_header