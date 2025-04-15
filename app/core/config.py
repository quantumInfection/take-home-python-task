import os
from pydantic import BaseModel


class Settings(BaseModel):
    # API authentication
    API_KEY: str = os.getenv("API_KEY", "")

    # Redis settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

    # Cache settings
    CACHE_TTL_SECONDS: int = 120  # 2 minutes cache TTL

    # Default values for the API
    DEFAULT_NETUID: int = 18
    DEFAULT_HOTKEY: str = "5FFApaS75bv5pJHfAp2FVLBj9ZaXuFDjEypsaBNc1wCfe52v"


settings = Settings()
