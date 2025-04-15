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

        # For positive sentiment: stake, for negative: unstake
        operation = "add_stake" if sentiment_score > 0 else "unstake"

        # Simulate processing time with variable sleep based on operation and amount
        # Higher amounts and unstaking operations generally take longer
        simulate_blockchain_operation(operation, amount)

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


def simulate_blockchain_operation(operation: str, amount: float) -> None:
    """
    Simulates blockchain operation with variable processing time based on operation type and amount.

    Args:
        operation: The type of operation ('add_stake' or 'unstake')
        amount: The amount of TAO being staked/unstaked
    """
    # Base sleep time for any blockchain operation
    base_sleep_time = 1.5  # seconds

    # Additional sleep time based on amount (larger amounts take longer to process)
    # Scale is dampened with sqrt to avoid excessive times for large amounts
    amount_factor = min(1.5, (amount / 10) ** 0.5)

    # Operation-specific factors (unstaking generally takes longer than staking)
    operation_factor = 1.2 if operation == "unstake" else 1.0

    # Calculate total sleep time
    total_sleep_time = base_sleep_time * operation_factor * amount_factor

    # Add slight randomness to simulate network variability (±15%)
    randomness = random.uniform(0.85, 1.15)
    final_sleep_time = total_sleep_time * randomness

    logger.debug(
        f"Simulating {operation} of {amount} TAO: sleep for {final_sleep_time:.2f}s "
        f"(base={base_sleep_time}s, amount_factor={amount_factor:.2f}, "
        f"operation_factor={operation_factor:.2f}, randomness={randomness:.2f})"
    )

    # Execute the sleep
    time.sleep(final_sleep_time)
