from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Dict, Any
import time

from app.services.cache_service import RedisCacheService
from app.core.config import settings

router = APIRouter(tags=["Tao Dividends"])

# Initialize cache service
cache_service = RedisCacheService()


# Mock function to simulate blockchain query with delay
async def mock_get_tao_dividends(
    netuid: Optional[int], hotkey: Optional[str]
) -> Dict[str, Any]:
    """
    Simulate blockchain query with artificial delay.
    In a real implementation, this would query the Bittensor blockchain.
    """
    # Simulate network delay
    time.sleep(2)

    # Use default values if not provided
    actual_netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
    actual_hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY

    # Mock dividend value (would come from blockchain in real implementation)
    mock_dividend = 12345678

    return {"netuid": actual_netuid, "hotkey": actual_hotkey, "dividend": mock_dividend}


@router.get("/tao_dividends_cached")
async def get_tao_dividends_with_cache(
    netuid: Optional[int] = Query(None, description="Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Account hotkey"),
):
    """
    Get Tao dividends with Redis caching.
    First checks cache, then falls back to blockchain query if not cached.
    """
    # Try to get from cache first
    cached_result = cache_service.get_cached_data(netuid, hotkey)

    if cached_result:
        # Data found in cache
        return {**cached_result, "cached": True}

    # Cache miss - query from "blockchain" (mock)
    result = await mock_get_tao_dividends(netuid, hotkey)

    # Cache the result
    cache_service.cache_data(netuid, hotkey, result)

    return {**result, "cached": False}


@router.get("/tao_dividends_no_cache")
async def get_tao_dividends_without_cache(
    netuid: Optional[int] = Query(None, description="Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Account hotkey"),
):
    """
    Get Tao dividends directly without using cache.
    Always performs a fresh blockchain query.
    """
    # Directly query from "blockchain" (mock)
    result = await mock_get_tao_dividends(netuid, hotkey)

    return result


@router.post("/purge_cache")
async def purge_cache_endpoint(
    netuid: Optional[int] = Query(None, description="Subnet ID to purge cache for"),
    hotkey: Optional[str] = Query(
        None, description="Account hotkey to purge cache for"
    ),
):
    """
    Purge cache for specific netuid/hotkey combination.
    If both are None, purges all tao_dividend cache entries.
    """
    success = cache_service.purge_cache(netuid, hotkey)

    if success:
        if netuid is None and hotkey is None:
            message = "All cache entries purged successfully"
        else:
            message = f"Cache purged for netuid={netuid}, hotkey={hotkey}"
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=500, detail="Failed to purge cache")
