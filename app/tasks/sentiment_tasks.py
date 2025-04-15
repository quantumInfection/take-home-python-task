from typing import Optional, List, Dict, Any
import logging
import asyncio
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore

from app.worker import celery_app
from app.core.config import settings
from app.services.sentiment_service import SentimentService
from app.db import store_sentiment_data  # Import the database function

logger = logging.getLogger(__name__)

# Define standardized error types and messages
ERROR_TYPES = {
    "CONNECTION_ERROR": "service_unavailable",
    "VALUE_ERROR": "invalid_request",
    "DATA_ERROR": "data_processing_error",
    "TIMEOUT_ERROR": "request_timeout",
    "UNKNOWN_ERROR": "internal_server_error",
}

# Standard error messages that don't expose implementation details
STANDARD_ERROR_MESSAGES = {
    "CONNECTION_ERROR": "Unable to connect to external data service",
    "VALUE_ERROR": "Invalid parameters for sentiment analysis",
    "DATA_ERROR": "Error processing sentiment data",
    "TIMEOUT_ERROR": "Sentiment analysis timed out",
    "UNKNOWN_ERROR": "An unexpected error occurred during sentiment analysis",
}


def validate_error_types():
    """
    Validates that all error types have corresponding standard messages.
    This function should be called during application initialization
    rather than at module import time to allow for dynamic extension of error types.
    """
    missing_types = []
    for error_type in ERROR_TYPES.keys():
        if error_type not in STANDARD_ERROR_MESSAGES:
            missing_types.append(error_type)

    if missing_types:
        error_msg = f"Missing standard error messages for error types: {', '.join(missing_types)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.debug(f"Validated {len(ERROR_TYPES)} error types with standard messages")


# Note: The validate_error_types() function should be called during application
# initialization in main.py or worker.py, not at module import time


def create_error_response(
    netuid: int,
    hotkey: str,
    error_type: str,
    error_message: str,
    original_error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a standardized error response with the detailed error logged but not exposed.

    Args:
        netuid: The subnet ID
        hotkey: The hotkey
        error_type: Standardized error type code
        error_message: User-friendly error message
        original_error: Original exception message (for logging only)

    Returns:
        Standardized error response dictionary
    """
    # Log the detailed error info if provided
    if original_error:
        logger.error(f"{error_message}. Original error: {original_error}")

    return {
        "success": False,
        "netuid": netuid,
        "hotkey": hotkey,
        "error_type": error_type,
        "error": error_message,
    }


@celery_app.task(name="analyze_twitter_sentiment")
def analyze_twitter_sentiment_task(netuid: int, hotkey: str) -> Dict[str, Any]:
    """
    Celery task that performs Twitter sentiment analysis for a Bittensor subnet.

    Args:
        netuid: The subnet ID to analyze sentiment for
        hotkey: The hotkey to associate with the sentiment analysis

    Returns:
        Dictionary containing sentiment analysis results
    """
    try:
        # Use default values if not provided
        actual_netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
        actual_hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY

        logger.info(
            f"Starting sentiment analysis for netuid={actual_netuid}, hotkey={actual_hotkey}"
        )

        # Initialize sentiment service
        sentiment_service = SentimentService()

        # Run the sentiment analysis in the asyncio event loop
        result = asyncio.run(
            sentiment_service.analyze_sentiment_for_subnet(actual_netuid)
        )

        # Add hotkey to the result
        result["hotkey"] = actual_hotkey

        # Store sentiment analysis result in MongoDB
        if (
            result.get("success", False)
            and "sentiment_score" in result
            and "tweets" in result
        ):
            try:
                # Create a new event loop for the database operation
                db_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(db_loop)

                # Store the sentiment data
                db_result = db_loop.run_until_complete(
                    store_sentiment_data(
                        netuid=actual_netuid,
                        tweets=result.get("tweets", []),
                        sentiment_score=result.get("sentiment_score", 0.0),
                    )
                )

                # Close the loop
                db_loop.close()

                # Add database storage status to result
                result["stored_in_db"] = True
                result["db_record_id"] = db_result
                logger.info(f"Sentiment data stored in database with ID: {db_result}")
            except Exception as db_error:
                logger.error(
                    f"Failed to store sentiment data in database: {str(db_error)}"
                )
                result["stored_in_db"] = False
                result["db_error"] = str(db_error)
        else:
            result["stored_in_db"] = False

        return result

    except SoftTimeLimitExceeded:
        # Handle soft time limit exceeded - allows for graceful shutdown
        logger.warning(
            f"Sentiment analysis timed out for netuid={netuid}, hotkey={hotkey}"
        )
        # Return standardized timeout error
        return create_error_response(
            netuid,
            hotkey,
            ERROR_TYPES["TIMEOUT_ERROR"],
            STANDARD_ERROR_MESSAGES["TIMEOUT_ERROR"],
        )
    except Exception as e:
        logger.error(f"Error in sentiment analysis task: {str(e)}", exc_info=True)

        # Categorize the error
        if "connect" in str(e).lower() or "timeout" in str(e).lower():
            error_type = ERROR_TYPES["CONNECTION_ERROR"]
            error_message = STANDARD_ERROR_MESSAGES["CONNECTION_ERROR"]
        else:
            error_type = ERROR_TYPES["UNKNOWN_ERROR"]
            error_message = STANDARD_ERROR_MESSAGES["UNKNOWN_ERROR"]

        return create_error_response(
            netuid, hotkey, error_type, error_message, original_error=str(e)
        )
