from typing import Optional, List, Dict, Any
import logging
import random
import time
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore

from app.worker import celery_app
from app.core.config import settings

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


def perform_twitter_sentiment_analysis(netuid: int, hotkey: str) -> Dict[str, Any]:
    """
    Synchronous function that simulates Twitter sentiment analysis workflow.
    In a real implementation, this would make API calls to Twitter
    and perform sentiment analysis on the results.

    Args:
        netuid: The subnet ID to analyze sentiment for
        hotkey: The hotkey to associate with the sentiment analysis

    Returns:
        Dictionary containing sentiment analysis results
    """
    # Log that we're executing the function
    logger.info(f"Executing sentiment analysis for netuid={netuid}, hotkey={hotkey}")

    try:
        # In a real implementation:
        # 1. Fetch tweets related to the asset
        logger.debug(f"Fetching tweets for netuid={netuid}")
        # twitter_client = TwitterClient(api_key=settings.TWITTER_API_KEY)
        # tweets = twitter_client.get_tweets(keywords=[f"tao {netuid}", "bittensor"])

        # Simulate processing time (Twitter API call)
        time.sleep(1)

        # 2. Process tweets and perform sentiment analysis
        logger.debug("Performing sentiment analysis on tweets")
        # sentiment_analyzer = SentimentAnalyzer()
        # analyzed_tweets = [sentiment_analyzer.analyze(tweet) for tweet in tweets]

        # Simulate processing time (sentiment analysis)
        time.sleep(1)

        # 3. Aggregate results and calculate overall sentiment score
        # sentiment_score = calculate_weighted_sentiment(analyzed_tweets)

        # For mock implementation: Generate a random sentiment score
        sentiment_score = random.randint(-100, 100)
        num_tweets = random.randint(5, 20)

        logger.info(
            f"Generated sentiment score: {sentiment_score} based on {num_tweets} tweets for netuid={netuid}"
        )

        return {
            "success": True,
            "netuid": netuid,
            "hotkey": hotkey,
            "sentiment_score": sentiment_score,
            "num_tweets_analyzed": num_tweets,
            "is_mocked": True,
        }

    except ConnectionError as e:
        # Handle network connectivity issues
        error_msg = f"Network error while connecting to Twitter API: {str(e)}"
        logger.error(error_msg)
        # Log the detailed error but return a standardized response
        return create_error_response(
            netuid,
            hotkey,
            ERROR_TYPES["CONNECTION_ERROR"],
            STANDARD_ERROR_MESSAGES["CONNECTION_ERROR"],
            original_error=str(e),
        )

    except ValueError as e:
        # Handle issues with invalid parameters
        error_msg = f"Value error in sentiment analysis: {str(e)}"
        logger.error(error_msg)
        return create_error_response(
            netuid,
            hotkey,
            ERROR_TYPES["VALUE_ERROR"],
            STANDARD_ERROR_MESSAGES["VALUE_ERROR"],
            original_error=str(e),
        )

    except KeyError as e:
        # Handle issues with missing expected data
        error_msg = f"Missing expected data in API response: {str(e)}"
        logger.error(error_msg)
        return create_error_response(
            netuid,
            hotkey,
            ERROR_TYPES["DATA_ERROR"],
            STANDARD_ERROR_MESSAGES["DATA_ERROR"],
            original_error=str(e),
        )

    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"Unexpected error during sentiment analysis: {str(e)}"
        logger.error(f"{error_msg}. Traceback: ", exc_info=True)
        return create_error_response(
            netuid,
            hotkey,
            ERROR_TYPES["UNKNOWN_ERROR"],
            STANDARD_ERROR_MESSAGES["UNKNOWN_ERROR"],
            original_error=str(e),
        )


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
        "error": error_message,  # Changed from error_message to error for consistency
        "is_mocked": True,
    }


@celery_app.task(name="analyze_twitter_sentiment")
def analyze_twitter_sentiment_task(netuid: int, hotkey: str) -> Dict[str, Any]:
    """
    Mocked Celery task that simulates the Twitter sentiment analysis workflow.

    Args:
        netuid: The subnet ID to analyze sentiment for
        hotkey: The hotkey to associate with the sentiment analysis

    Returns:
        Dictionary containing sentiment analysis results
    """
    try:
        # Simply call the synchronous function directly
        result = perform_twitter_sentiment_analysis(netuid, hotkey)
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
