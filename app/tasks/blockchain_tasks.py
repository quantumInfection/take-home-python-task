from typing import Dict, Any, Optional
import logging
import asyncio
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore
from app.worker import celery_app
from app.core.config import settings
from app.services.blockchain_service import BlockchainService
from app.db import record_stake_action  # Import the database function

logger = logging.getLogger(__name__)


@celery_app.task(name="process_stake_based_on_sentiment")
def process_stake_based_on_sentiment_task(
    sentiment_result: Dict[str, Any], netuid: int = None, hotkey: str = None
) -> Dict[str, Any]:
    """
    Process stake/unstake operations based on sentiment analysis results.

    Args:
        sentiment_result: The result from sentiment analysis task
        netuid: The subnet ID to stake/unstake on (optional)
        hotkey: The hotkey to stake/unstake to (optional)
    """
    sentiment_score = 0  # Initialize outside try block for exception handling
    try:
        # Extract sentiment score from the sentiment analysis result
        if not sentiment_result.get("success", False):
            logger.error(
                f"Sentiment analysis failed: {sentiment_result.get('error', 'Unknown error')}"
            )
            return {
                "success": False,
                "operation": "none",
                "error": f"Sentiment analysis failed: {sentiment_result.get('error', 'Unknown error')}",
                "netuid": netuid,
                "hotkey": hotkey,
                "sentiment_result": sentiment_result,
            }

        sentiment_score = sentiment_result.get("sentiment_score", 0.0)
        logger.info(f"Processing stake based on sentiment score: {sentiment_score}")

        # Use default values if not provided
        netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
        hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY

        # Calculate amount based on sentiment (0.01 tao * sentiment)
        amount = abs(sentiment_score) * 0.01

        # Early exit for zero amount
        if amount <= 0.001:  # Minimum threshold to avoid dust transactions
            return {
                "success": True,
                "operation": "none",
                "message": "Sentiment score resulted in zero or negligible stake amount",
                "netuid": netuid,
                "hotkey": hotkey,
                "sentiment_score": sentiment_score,
                "amount": 0,
            }

        # For positive sentiment: stake, for negative: unstake
        operation = "add_stake" if sentiment_score > 0 else "unstake"

        # Initialize blockchain service
        blockchain_service = BlockchainService()

        # Create new event loop for asyncio.run
        asyncio.set_event_loop(asyncio.new_event_loop())

        # Run the operation in the asyncio event loop
        if operation == "add_stake":
            result = asyncio.run(blockchain_service.add_stake(netuid, hotkey, amount))
        else:
            result = asyncio.run(blockchain_service.unstake(netuid, hotkey, amount))

        # Add sentiment information to the result
        result["sentiment_score"] = sentiment_score

        # Record the stake action in the database if blockchain operation was successful
        if result.get("success", False):
            try:
                # Create a new event loop for the database operation
                db_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(db_loop)

                # Store the stake action
                db_result = db_loop.run_until_complete(
                    record_stake_action(
                        netuid=netuid,
                        hotkey=hotkey,
                        action_type=operation,  # "add_stake" or "unstake"
                        amount=amount,
                        sentiment_score=sentiment_score,
                    )
                )

                # Close the loop
                db_loop.close()

                # Add database storage status to result
                result["stored_in_db"] = True
                result["db_record_id"] = db_result
                logger.info(f"Stake action recorded in database with ID: {db_result}")
            except Exception as db_error:
                logger.error(
                    f"Failed to store stake action in database: {str(db_error)}"
                )
                result["stored_in_db"] = False
                result["db_error"] = str(db_error)
        else:
            result["stored_in_db"] = False

        logger.info(f"Completed blockchain {operation} operation: {result['success']}")

        return result

    except SoftTimeLimitExceeded:
        # Handle soft time limit exceeded gracefully
        logger.warning(
            f"Blockchain operation timed out for netuid={netuid}, hotkey={hotkey}"
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
            "timed_out": True,
        }
    except Exception as e:
        logger.error(f"Error in blockchain operation: {str(e)}", exc_info=True)
        return {
            "success": False,
            "operation": "unknown",
            "netuid": netuid,
            "hotkey": hotkey,
            "sentiment_score": sentiment_result.get("sentiment_score", 0),
            "error": str(e),
        }
