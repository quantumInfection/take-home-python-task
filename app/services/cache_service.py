import json
import redis
from typing import Any, Dict, Optional

from app.core.config import settings


class RedisCacheService:
    """Service to handle Redis caching operations."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        
    def get_cache_key(self, netuid: Optional[int], hotkey: Optional[str]) -> str:
        """Generate a cache key for dividend data."""
        netuid_part = f"netuid:{netuid}" if netuid is not None else "netuid:all"
        hotkey_part = f"hotkey:{hotkey}" if hotkey is not None else "hotkey:all"
        return f"tao_dividend:{netuid_part}:{hotkey_part}"

    def get_cached_data(self, netuid: Optional[int], hotkey: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Try to get dividend data from cache.
        Returns cached data or None if not found.
        """
        cache_key = self.get_cache_key(netuid, hotkey)
        cached_data = self.redis_client.get(cache_key)
        
        if cached_data:
            return json.loads(cached_data)
        return None

    def cache_data(self, netuid: Optional[int], hotkey: Optional[str], data: Dict[str, Any]) -> bool:
        """
        Cache dividend data in Redis with TTL.
        Returns True if successful, False otherwise.
        """
        try:
            cache_key = self.get_cache_key(netuid, hotkey)
            # Set with expiration (TTL)
            self.redis_client.setex(
                cache_key,
                settings.CACHE_TTL_SECONDS,
                json.dumps(data)
            )
            return True
        except Exception:
            return False
    
    def purge_cache(self, netuid: Optional[int] = None, hotkey: Optional[str] = None) -> bool:
        """
        Purge cache for specific netuid/hotkey or all cache if both are None.
        Returns True if successful, False otherwise.
        """
        try:
            if netuid is None and hotkey is None:
                # Delete all tao_dividend keys
                keys = self.redis_client.keys("tao_dividend:*")
                if keys:
                    self.redis_client.delete(*keys)
            else:
                # Delete specific key
                cache_key = self.get_cache_key(netuid, hotkey)
                self.redis_client.delete(cache_key)
            return True
        except Exception:
            return False