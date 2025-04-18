from fastapi import APIRouter, Query, HTTPException, Depends, status
from fastapi.responses import JSONResponse
import warnings
from typing import Optional, Dict, Any, Tuple, Callable, List
import asyncio
import logging
import traceback
import redis
import contextlib
from celery import chain
from celery.exceptions import CeleryError, TaskRevokedError, TimeoutError as CeleryTimeoutError  # type: ignore
from celery.result import AsyncResult  # type: ignore

from app.services.cache_service import RedisCacheService
from app.services.blockchain_service import BlockchainService
from app.core.config import settings
from app.auth.auth import get_api_key_from_header
from app.tasks.sentiment_tasks import analyze_twitter_sentiment_task
from app.tasks.blockchain_tasks import process_stake_based_on_sentiment_task
import time

# Import database functions and models
from app.db import (
    get_dividend_history,
    get_latest_sentiment,
    record_stake_action,
    store_dividend_data,  # Import the function to store dividend data
    TaoDividendModel,
    StakeActionModel,
    SentimentDataModel,
)

router = APIRouter(tags=["Tao Dividends"])

# Initialize services
cache_service = RedisCacheService()
blockchain_service = BlockchainService()
logger = logging.getLogger(__name__)


# Custom exceptions for task operations
class TaskCreationError(Exception):
    """Exception raised when a task fails to be created"""

    pass


class TaskChainingError(Exception):
    """Exception raised when task chaining fails"""

    pass


# Define error categories
ERROR_CATEGORIES = {
    "TASK_CREATION": "Error creating sentiment analysis task",
    "TASK_CHAINING": "Error chaining tasks together",
    "REDIS_ERROR": "Error communicating with Redis",
    "TASK_REVOKED": "Task was revoked or cancelled",
    "TIMEOUT_ERROR": "Task execution timed out",
    "UNKNOWN_ERROR": "Unknown error during task processing",
    "BLOCKCHAIN_ERROR": "Error querying blockchain data",
}


def log_error(
    error_category: str, error_details: str, include_stack_trace: bool = True
) -> None:
    """
    Common helper function for logging errors in a consistent format.

    Args:
        error_category: The category of the error
        error_details: Detailed error message
        include_stack_trace: Whether to include stack trace in the logs
    """
    logger.error(f"{error_category}: {error_details}")
    if include_stack_trace:
        logger.error(f"Stack trace: {traceback.format_exc()}")


def handle_task_error(
    e: Exception,
    sentiment_task: Optional[AsyncResult] = None,
    task_chain: Optional[AsyncResult] = None,
) -> Tuple[str, str]:
    """
    Helper function to handle task errors in a consistent way.
    Also ensures any created tasks are properly revoked.

    Args:
        e: The exception that was raised
        sentiment_task: The sentiment analysis task (if created)
        task_chain: The task chain (if created)

    Returns:
        Tuple of (error_category, error_details)
    """
    # First, revoke any tasks that were created to prevent orphaned tasks
    if sentiment_task:
        try:
            logger.info(f"Explicitly revoking sentiment task: {sentiment_task.id}")
            sentiment_task.revoke(terminate=True)
        except Exception as revoke_error:
            logger.error(f"Error revoking sentiment task: {str(revoke_error)}")

    if task_chain:
        try:
            logger.info(f"Explicitly revoking task chain: {task_chain.id}")
            task_chain.revoke(terminate=True)
        except Exception as revoke_error:
            logger.error(f"Error revoking task chain: {str(revoke_error)}")

    # Determine error category using exception type mapping
    exception_type_to_category = {
        redis.RedisError: ERROR_CATEGORIES["REDIS_ERROR"],
        TaskRevokedError: ERROR_CATEGORIES["TASK_REVOKED"],
        CeleryTimeoutError: ERROR_CATEGORIES["TIMEOUT_ERROR"],
        TaskCreationError: ERROR_CATEGORIES["TASK_CREATION"],
        TaskChainingError: ERROR_CATEGORIES["TASK_CHAINING"],
    }

    error_category = exception_type_to_category.get(type(e))

    # For exception types not explicitly mapped
    if error_category is None:
        if isinstance(e, (CeleryError, ValueError)):
            # Determine what stage of task creation/chaining failed
            error_category = (
                ERROR_CATEGORIES["TASK_CHAINING"]
                if sentiment_task and not task_chain
                else ERROR_CATEGORIES["TASK_CREATION"]
            )
        else:
            # Default for any other exception type
            error_category = ERROR_CATEGORIES["UNKNOWN_ERROR"]

    # Format the error details appropriately based on the exception type
    if isinstance(e, TaskRevokedError):
        error_details = f"Task was revoked: {str(e)}"
        log_error(error_category, error_details, include_stack_trace=False)
    elif isinstance(e, redis.RedisError):
        error_details = f"Redis communication error: {str(e)}"
        log_error(error_category, error_details)
    elif isinstance(e, CeleryTimeoutError):
        error_details = f"Task execution timed out: {str(e)}"
        log_error(error_category, error_details)
    elif isinstance(e, (TaskCreationError, TaskChainingError)):
        error_details = str(e)
        log_error(error_category, error_details)
    elif isinstance(e, CeleryError):
        phase = "chaining tasks" if sentiment_task else "creating task"
        error_details = f"Celery error while {phase}: {str(e)}"
        log_error(error_category, error_details)
    elif isinstance(e, ValueError):
        error_details = str(e)
        log_error(error_category, error_details)
    else:
        error_details = f"Unexpected error: {str(e)}"
        log_error(error_category, error_details)

    return error_category, error_details


@contextlib.contextmanager
def manage_tasks():
    """
    Context manager for safely handling Celery tasks.
    Ensures tasks are properly revoked if an exception occurs.

    Usage:
        with manage_tasks() as task_manager:
            task_manager.sentiment_task = some_task.apply_async()
            task_manager.task_chain = task_manager.sentiment_task.then(next_task)
    """

    class TaskManager:
        def __init__(self):
            self.sentiment_task = None
            self.task_chain = None
            self._revocation_metrics = {
                "attempts": 0,
                "failures": 0,
                "connection_errors": 0,
                "timeout_errors": 0,
                "other_errors": 0,
            }

        @property
        def revocation_metrics(self):
            """Provide read-only access to revocation metrics"""
            return self._revocation_metrics.copy()

        def revoke_tasks(self):
            """
            Revoke any active tasks with specific exception handling and metrics.
            Uses retry pattern for connection errors.
            """
            tasks_to_revoke = []

            if self.sentiment_task:
                tasks_to_revoke.append(("sentiment_task", self.sentiment_task))

            if self.task_chain:
                tasks_to_revoke.append(("task_chain", self.task_chain))

            if not tasks_to_revoke:
                return  # No tasks to revoke

            for task_name, task in tasks_to_revoke:
                self._revoke_single_task(task_name, task)

        def _revoke_single_task(self, task_name, task, max_retries=2, retry_delay=0.5):
            """Revoke a single task with retry logic for connection issues"""
            self._revocation_metrics["attempts"] += 1
            retries = 0

            while retries <= max_retries:
                try:
                    logger.info(f"Revoking {task_name}: {task.id}")
                    task.revoke(terminate=True)
                    return  # Success, no need to retry

                except (redis.RedisError, ConnectionError) as e:
                    # Connection-specific errors that might be transient
                    retries += 1
                    self._revocation_metrics["connection_errors"] += 1

                    if retries <= max_retries:
                        logger.warning(
                            f"Connection error when revoking {task_name} (attempt {retries}/{max_retries}): {str(e)}. Retrying in {retry_delay}s"
                        )
                        time.sleep(retry_delay)  # Wait before retry
                    else:
                        logger.error(
                            f"Failed to revoke {task_name} after {max_retries} retries: {str(e)}"
                        )
                        self._revocation_metrics["failures"] += 1
                        # Consider alternative cleanup like marking in a "zombie tasks" table for later cleanup

                except TimeoutError as e:
                    # Timeout errors might be resolved with retry
                    retries += 1
                    self._revocation_metrics["timeout_errors"] += 1

                    if retries <= max_retries:
                        logger.warning(
                            f"Timeout when revoking {task_name} (attempt {retries}/{max_retries}): {str(e)}. Retrying in {retry_delay}s"
                        )
                        time.sleep(retry_delay)  # Wait before retry
                    else:
                        logger.error(
                            f"Timeout revoking {task_name} after {max_retries} retries: {str(e)}"
                        )
                        self._revocation_metrics["failures"] += 1

                except Exception as e:
                    # Other unexpected errors - log with more detail but don't retry
                    logger.error(
                        f"Error revoking {task_name} ({type(e).__name__}): {str(e)}"
                    )
                    logger.debug(
                        f"Full traceback for {task_name} revocation error:",
                        exc_info=True,
                    )
                    self._revocation_metrics["failures"] += 1
                    self._revocation_metrics["other_errors"] += 1
                    break  # Don't retry for other types of errors

    manager = TaskManager()
    try:
        yield manager
    except Exception:
        # Ensure tasks are revoked if an exception occurs
        manager.revoke_tasks()

        # Log metrics on revocation attempts
        if manager._revocation_metrics["attempts"] > 0:
            logger.info(f"Task revocation metrics: {manager.revocation_metrics}")

        raise
    finally:
        # Always ensure tasks are properly cleaned up, even without exceptions
        # This addresses potential resource leaks in normal execution flows
        if manager.sentiment_task or manager.task_chain:
            logger.debug("Performing final cleanup of task resources")
            # We don't need to revoke successful tasks, but we may need to perform other cleanup
            # For example, removing temporary files or closing connections

            # Log metrics if any revocations were attempted during cleanup
            if manager._revocation_metrics["attempts"] > 0:
                logger.info(f"Task cleanup metrics: {manager.revocation_metrics}")


async def get_tao_dividends(
    netuid: Optional[int], hotkey: Optional[str]
) -> Dict[str, Any]:
    """
    Query the blockchain for Tao dividends.
    Uses the BlockchainService to make the real blockchain query.

    Args:
        netuid: Optional subnet ID
        hotkey: Optional account hotkey

    Returns:
        Dictionary with dividend data
    """
    try:
        result = await blockchain_service.get_tao_dividends(netuid, hotkey)

        # Store the dividend data in the database
        if result and "dividend" in result:
            try:
                # Store the result in the database
                await store_dividend_data(
                    netuid=netuid if netuid is not None else settings.DEFAULT_NETUID,
                    hotkey=hotkey if hotkey is not None else settings.DEFAULT_HOTKEY,
                    dividend=result.get("dividend", 0),
                )
                logger.info(
                    f"Dividend data stored in database for netuid={netuid}, hotkey={hotkey}"
                )
            except Exception as db_error:
                logger.error(
                    f"Error storing dividend data in database: {str(db_error)}"
                )
                # Don't fail the query just because DB storage failed
                # Just continue with the result

        return result
    except Exception as e:
        logger.error(f"Error querying blockchain: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error querying blockchain: {str(e)}",
        )


@router.get("/tao_dividends")
async def tao_dividends_endpoint(
    netuid: Optional[int] = Query(None, description="Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Account hotkey"),
    trade: bool = Query(False, description="Trigger sentiment analysis and staking"),
    wait_for_results: bool = Query(False, description="Wait for task completion"),
    timeout: Optional[float] = Query(
        None,
        description="Timeout in seconds for waiting for task results (default: 20)",
    ),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Primary endpoint for Tao dividends with advanced features.

    This endpoint combines and extends the functionality of the other tao_dividends endpoints:
    - Provides cached access to dividend data (like /tao_dividends_cached)
    - Optionally triggers sentiment analysis and staking via background tasks

    Parameters:
    - netuid: Optional subnet ID (defaults to DEFAULT_NETUID from config)
    - hotkey: Optional account hotkey (defaults to DEFAULT_HOTKEY from config)
    - trade: If True, triggers sentiment analysis and staking background tasks
    - wait_for_results: If True and trade is True, waits for task completion
    - timeout: Maximum time to wait for task results in seconds (default: 20s)

    Returns:
    - Dividend data with cache status
    - If trade=True, includes information about triggered background tasks
    - If wait_for_results=True, includes task results (or timeout status)
    """
    # Use default values if not provided
    actual_netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
    actual_hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY
    actual_timeout = (
        timeout if timeout is not None else 20.0
    )  # Default timeout of 20 seconds

    # Try to get from cache first
    cached_result = cache_service.get_cached_data(actual_netuid, actual_hotkey)

    if cached_result:
        # Data found in cache
        result = {**cached_result, "cached": True}
    else:
        # Cache miss - query from blockchain
        try:
            result = await get_tao_dividends(actual_netuid, actual_hotkey)

            # Cache the result
            cache_service.cache_data(actual_netuid, actual_hotkey, result)
            result["cached"] = False
        except Exception as e:
            # Handle blockchain query errors
            error_category = ERROR_CATEGORIES["BLOCKCHAIN_ERROR"]
            error_details = f"Error querying blockchain: {str(e)}"
            log_error(error_category, error_details)

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "error": error_category,
                    "detail": str(e),
                    "netuid": actual_netuid,
                    "hotkey": actual_hotkey,
                },
            )

    # If trade is true, trigger sentiment analysis and staking background tasks
    if trade:
        with manage_tasks() as task_manager:
            try:
                # Define the first task (sentiment analysis)
                sentiment_signature = analyze_twitter_sentiment_task.s(
                    actual_netuid, actual_hotkey
                ).set(
                    time_limit=10,  # 10 seconds timeout for sentiment analysis
                    soft_time_limit=8,  # Soft timeout to allow for graceful handling
                )

                # Define the second task (blockchain processing)
                blockchain_signature = process_stake_based_on_sentiment_task.s(
                    actual_netuid, actual_hotkey
                ).set(
                    time_limit=15,  # 15 seconds timeout for blockchain operation
                    soft_time_limit=12,  # Soft timeout for graceful handling
                )

                # Create the chain
                task_chain_result = chain(
                    sentiment_signature, blockchain_signature
                ).apply_async()

                if not task_chain_result:
                    raise TaskChainingError("Failed to create task chain")

                # task_chain_result is an AsyncResult; its id is the id of the *last* task
                task_manager.task_chain = task_chain_result
                # Keep track of the first task's result if needed for individual monitoring/revocation
                # Note: task_chain_result.parent gives the result of the previous task in the chain
                task_manager.sentiment_task = task_chain_result.parent

                # Store reference to the full chain for proper monitoring
                # The AsyncResult returned by chain() represents the final task
                chain_result = task_manager.task_chain
                task_manager.full_chain = chain_result  # Redundant? task_chain already holds this. Let's keep task_chain as the main reference.

                # Track the chain lineage with a depth limit to avoid excessive traversal
                chain_lineage = []
                current_task = chain_result
                depth = 0
                max_depth = 10  # Reasonable limit for most practical chains

                while current_task and current_task.parent and depth < max_depth:
                    chain_lineage.append(current_task.id)
                    # Access the parent AsyncResult correctly
                    parent_result = (
                        AsyncResult(current_task.parent.id)
                        if current_task.parent
                        else None
                    )
                    current_task = parent_result
                    depth += 1

                # Add the root task ID if it exists and wasn't added
                if current_task and current_task.id not in chain_lineage:
                    chain_lineage.append(current_task.id)

                if depth >= max_depth and current_task and current_task.parent:
                    logger.warning(
                        f"Chain lineage traversal stopped at depth {max_depth}. Chain may be longer than expected."
                    )

                logger.debug(
                    f"Task chain lineage (depth: {depth}): {chain_lineage[::-1]}"
                )  # Reverse to show in execution order

                result["stake_tx_triggered"] = True
                result["task_timeouts"] = {
                    "sentiment_analysis": "8s soft, 10s hard",
                    "blockchain_operation": "12s soft, 15s hard",
                }

                # Log successful task creation
                logger.info(
                    f"Triggered sentiment analysis and staking for netuid={actual_netuid}, hotkey={actual_hotkey}"
                )
                # Safely access task IDs
                sentiment_task_id = getattr(task_manager.sentiment_task, "id", "N/A")
                chain_id = getattr(
                    task_manager.task_chain, "id", "N/A"
                )  # This should now work
                logger.debug(
                    f"Task IDs: sentiment_task.id={sentiment_task_id}, chain_id={chain_id}"
                )

                # If wait_for_results is True, wait for tasks to complete with timeout
                if wait_for_results:
                    try:
                        logger.info(
                            f"Waiting for task completion with timeout={actual_timeout}s"
                        )
                        result["task_wait"] = {
                            "enabled": True,
                            "timeout": actual_timeout,
                        }

                        # Wait for the final task in the chain to complete
                        task_result = task_manager.task_chain.get(
                            timeout=actual_timeout,
                            propagate=False,  # Don't raise exceptions from the task
                        )

                        # Add task results to the response
                        if task_result:
                            result["task_completed"] = True
                            result["task_result"] = task_result
                        else:
                            result["task_completed"] = False
                            result["task_error"] = "Task returned None"

                    except asyncio.TimeoutError:
                        # Handle asyncio timeout
                        logger.warning(
                            f"Asyncio timeout waiting for task completion after {actual_timeout}s"
                        )
                        result["task_completed"] = False
                        result["task_timeout"] = True
                        result["task_error"] = f"Timed out after {actual_timeout}s"
                        return JSONResponse(
                            status_code=status.HTTP_504_GATEWAY_TIMEOUT, content=result
                        )

                    except CeleryTimeoutError:
                        # Handle Celery timeout
                        logger.warning(
                            f"Celery timeout waiting for task completion after {actual_timeout}s"
                        )
                        result["task_completed"] = False
                        result["task_timeout"] = True
                        result["task_error"] = (
                            f"Celery task timed out after {actual_timeout}s"
                        )
                        return JSONResponse(
                            status_code=status.HTTP_504_GATEWAY_TIMEOUT, content=result
                        )

                    except Exception as e:
                        # Handle other exceptions during task wait
                        logger.error(f"Error waiting for task result: {str(e)}")
                        result["task_completed"] = False
                        result["task_error"] = f"Error retrieving task result: {str(e)}"
                        return JSONResponse(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content=result,
                        )
                else:
                    # Not waiting for results, just include task IDs
                    result["task_ids"] = {
                        "sentiment_task_id": sentiment_task_id,
                        "chain_task_id": chain_id,
                    }

            except Exception as e:
                # Use the helper function to handle the error
                error_category, error_details = handle_task_error(
                    e, task_manager.sentiment_task, task_manager.task_chain
                )

                # Determine appropriate status code based on the error type
                # Default status code is 500, only set different codes for special cases
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                if error_category == ERROR_CATEGORIES["REDIS_ERROR"]:
                    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                elif error_category == ERROR_CATEGORIES["TIMEOUT_ERROR"]:
                    status_code = status.HTTP_504_GATEWAY_TIMEOUT
                elif error_category == ERROR_CATEGORIES["TASK_REVOKED"]:
                    status_code = status.HTTP_409_CONFLICT
                # No need for explicit 500 cases since that's our default

                # Create error response
                error_response = {
                    "dividend_data": result,  # Include the dividend data we successfully retrieved
                    "stake_tx_triggered": False,
                    "stake_error": error_category,
                    "error_details": error_details,
                }

                # Return with appropriate status code
                return JSONResponse(status_code=status_code, content=error_response)
    else:
        result["stake_tx_triggered"] = False

    return result


@router.get("/tao_dividends_cached", deprecated=True)
async def get_tao_dividends_with_cache(
    netuid: Optional[int] = Query(None, description="Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Account hotkey"),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    DEPRECATED: Use /tao_dividends instead.

    Get Tao dividends with Redis caching.
    First checks cache, then falls back to blockchain query if not cached.
    """
    # Log deprecation warning
    logger.warning(
        "Deprecated endpoint /tao_dividends_cached was called. Use /tao_dividends instead."
    )
    return await tao_dividends_endpoint(netuid=netuid, hotkey=hotkey, api_key=api_key)


@router.get("/tao_dividends_no_cache")
async def get_tao_dividends_without_cache(
    netuid: Optional[int] = Query(None, description="Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Account hotkey"),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Get Tao dividends directly without using cache.
    Always performs a fresh blockchain query.
    """
    # Directly query from blockchain
    return await get_tao_dividends(netuid, hotkey)


@router.post("/purge_cache")
async def purge_cache_endpoint(
    netuid: Optional[int] = Query(None, description="Subnet ID to purge cache for"),
    hotkey: Optional[str] = Query(
        None, description="Account hotkey to purge cache for"
    ),
    api_key: str = Depends(get_api_key_from_header),
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


@router.get("/dividend_history", response_model=List[Dict[str, Any]])
async def get_dividend_history_endpoint(
    netuid: Optional[int] = Query(None, description="Filter by Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Filter by account hotkey"),
    limit: int = Query(100, description="Maximum number of records to return"),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Retrieve dividend history from the database.

    Parameters:
    - netuid: Optional filter by subnet ID
    - hotkey: Optional filter by hotkey
    - limit: Maximum number of records to return (default: 100)

    Returns:
    - List of dividend history records
    """
    try:
        history = await get_dividend_history(netuid=netuid, hotkey=hotkey, limit=limit)
        return history
    except Exception as e:
        logger.error(f"Error retrieving dividend history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving dividend history: {str(e)}",
        )


@router.get("/sentiment_history", response_model=Dict[str, Any])
async def get_sentiment_history_endpoint(
    netuid: int = Query(..., description="Subnet ID to get sentiment for"),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Retrieve the latest sentiment analysis for a specific subnet.

    Parameters:
    - netuid: Subnet ID to get sentiment for

    Returns:
    - Latest sentiment data including score and analyzed tweets
    """
    try:
        sentiment_data = await get_latest_sentiment(netuid=netuid)
        if sentiment_data:
            return sentiment_data
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No sentiment data found for netuid {netuid}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving sentiment data: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving sentiment data: {str(e)}",
        )


@router.get("/stake_history", response_model=List[Dict[str, Any]])
async def get_stake_history_endpoint(
    netuid: Optional[int] = Query(None, description="Filter by Subnet ID"),
    hotkey: Optional[str] = Query(None, description="Filter by account hotkey"),
    action_type: Optional[str] = Query(
        None, description="Filter by action type (stake/unstake)"
    ),
    limit: int = Query(100, description="Maximum number of records to return"),
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Retrieve staking action history from the database.

    Parameters:
    - netuid: Optional filter by subnet ID
    - hotkey: Optional filter by hotkey
    - action_type: Optional filter by action type ('stake' or 'unstake')
    - limit: Maximum number of records to return (default: 100)

    Returns:
    - List of stake action history records
    """
    try:
        # We need to implement this function in mongo.py
        from app.db.mongo import get_stake_history

        history = await get_stake_history(
            netuid=netuid, hotkey=hotkey, action_type=action_type, limit=limit
        )
        return history
    except Exception as e:
        logger.error(f"Error retrieving stake history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving stake history: {str(e)}",
        )


@router.get("/db_stats")
async def get_database_stats_endpoint(
    api_key: str = Depends(get_api_key_from_header),
):
    """
    Get database statistics and collection counts.

    Returns:
    - Collection statistics including document counts
    """
    try:
        # We need to implement this function in mongo.py
        from app.db.mongo import get_database_stats

        stats = await get_database_stats()
        return stats
    except Exception as e:
        logger.error(f"Error retrieving database stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving database stats: {str(e)}",
        )
