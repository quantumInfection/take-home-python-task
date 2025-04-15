from typing import Dict, Any, Optional
import logging
import time
import random
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore
from app.worker import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="process_stake_based_on_sentiment")
def process_stake_based_on_sentiment_task(
    netuid: int, hotkey: str, sentiment_score: float
) -> Dict[str, Any]:
    """
    Mocked task that simulates processing stake/unstake operations based on sentiment analysis.

    Args:
        netuid: The subnet ID to stake/unstake on
        hotkey: The hotkey to stake/unstake to
        sentiment_score: The sentiment score (-100 to +100)
    """
    try:
        logger.info(
            f"Executing mocked blockchain operation for netuid={netuid}, hotkey={hotkey}, sentiment={sentiment_score}"
        )

        # Use default values from settings if None (consistent with routes.py)
        netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
        hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY

        # Calculate amount based on sentiment (0.01 tao * sentiment)
        amount = abs(sentiment_score) * 0.01

        # Early exit for zero amount
        if amount <= 0:
            return {
                "success": True,
                "operation": "none",
                "message": "Sentiment score resulted in zero stake amount",
                "netuid": netuid,
                "hotkey": hotkey,
                "sentiment_score": sentiment_score,
                "amount": 0,
                "is_mocked": True,
            }

        # Simulate processing time (blockchain transactions are slow)
        time.sleep(3)

        # For positive sentiment: stake, for negative: unstake
        operation = "add_stake" if sentiment_score > 0 else "unstake"

        # Random success/failure to simulate real-world behavior
        success = random.random() > 0.1  # 90% success rate

        # Generate a mock transaction hash
        mock_hash = "0x" + "".join(random.choice("0123456789abcdef") for _ in range(64))

        result = {
            "success": success,
            "operation": operation,
            "netuid": netuid,
            "hotkey": hotkey,
            "amount": amount,
            "sentiment_score": sentiment_score,
            "hash": mock_hash if success else None,
            "error": None if success else "Simulated blockchain error",
            "is_mocked": True,
        }

        logger.info(
            f"Completed mock {operation} operation: {'success' if success else 'failed'}"
        )

        return result

    except SoftTimeLimitExceeded:
        # Handle soft time limit exceeded gracefully
        logger.warning(
            f"Blockchain operation timed out for netuid={netuid}, hotkey={hotkey}, sentiment={sentiment_score}"
        )

        # Prepare a response for the timeout situation
        operation = "add_stake" if sentiment_score > 0 else "unstake"
        amount = abs(sentiment_score) * 0.01

        return {
            "success": False,
            "operation": operation,
            "netuid": netuid,
            "hotkey": hotkey,
            "amount": amount,
            "sentiment_score": sentiment_score,
            "hash": None,
            "error": "Task timed out during blockchain operation",
            "is_mocked": True,
            "timed_out": True,
        }
