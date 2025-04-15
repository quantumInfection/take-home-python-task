import os
from pydantic import BaseModel


class Settings(BaseModel):
    # API authentication
    API_KEY: str = os.getenv("API_KEY", "")

    # Redis settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

    # Separate Redis databases for Celery broker and backend
    REDIS_BROKER_DB: int = int(os.getenv("REDIS_BROKER_DB", "0"))
    REDIS_BACKEND_DB: int = int(os.getenv("REDIS_BACKEND_DB", "1"))
    REDIS_BROKER_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_BROKER_DB}"
    REDIS_BACKEND_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_BACKEND_DB}"

    # Cache settings
    CACHE_TTL_SECONDS: int = int(
        os.getenv("CACHE_TTL_SECONDS", "120")
    )  # 2 minutes cache TTL

    # Default values for the API
    DEFAULT_NETUID: int = int(os.getenv("DEFAULT_NETUID", "18"))
    DEFAULT_HOTKEY: str = os.getenv(
        "DEFAULT_HOTKEY", "5FFApaS75bv5pJHfAp2FVLBj9ZaXuFDjEypsaBNc1wCfe52v"
    )

    # Bittensor settings
    BITTENSOR_NETWORK: str = os.getenv("BITTENSOR_NETWORK", "test")
    BITTENSOR_WALLET_NAME: str = os.getenv("BITTENSOR_WALLET_NAME", "default")
    BITTENSOR_WALLET_HOTKEY: str = os.getenv("BITTENSOR_WALLET_HOTKEY", "default")
    BITTENSOR_WALLET_MNEMONIC: str = os.getenv("BITTENSOR_WALLET_MNEMONIC", "")

    # External API keys
    DATURA_API_KEY: str = os.getenv("DATURA_API_KEY", "")
    CHUTES_API_KEY: str = os.getenv("CHUTES_API_KEY", "")


settings = Settings()
