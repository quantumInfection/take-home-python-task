"""
MongoDB database connection and utility functions.
Uses Motor as an asynchronous MongoDB driver.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, Any, Optional, List
import os
from datetime import datetime

# MongoDB connection settings - should be moved to environment variables in production
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
DB_NAME = os.getenv("MONGO_DB", "bittensor_app")

# Database collections
DIVIDENDS_COLLECTION = "tao_dividends"
STAKE_HISTORY_COLLECTION = "stake_history"
SENTIMENT_COLLECTION = "twitter_sentiments"

# MongoDB client instance
_client: Optional[AsyncIOMotorClient] = None


async def get_db_client() -> AsyncIOMotorClient:
    """Get or create a MongoDB client."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


async def get_db():
    """Get the database instance."""
    client = await get_db_client()
    return client[DB_NAME]


async def close_db_connection():
    """Close the MongoDB connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


# Database operations for Tao dividends
async def store_dividend_data(
    netuid: int, hotkey: str, dividend: int, timestamp: datetime = None
) -> str:
    """Store dividend data in the database."""
    db = await get_db()
    collection = db[DIVIDENDS_COLLECTION]

    if timestamp is None:
        timestamp = datetime.utcnow()

    document = {
        "netuid": netuid,
        "hotkey": hotkey,
        "dividend": dividend,
        "timestamp": timestamp,
    }

    result = await collection.insert_one(document)
    return str(result.inserted_id)


async def get_dividend_history(
    netuid: Optional[int] = None, hotkey: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """Get dividend history from the database."""
    db = await get_db()
    collection = db[DIVIDENDS_COLLECTION]

    query = {}
    if netuid is not None:
        query["netuid"] = netuid
    if hotkey is not None:
        query["hotkey"] = hotkey

    cursor = collection.find(query).sort("timestamp", -1).limit(limit)
    results = await cursor.to_list(length=limit)
    return results


# Stake history operations
async def record_stake_action(
    netuid: int,
    hotkey: str,
    action_type: str,
    amount: float,
    sentiment_score: Optional[float] = None,
) -> str:
    """Record a stake/unstake action in the database."""
    db = await get_db()
    collection = db[STAKE_HISTORY_COLLECTION]

    document = {
        "netuid": netuid,
        "hotkey": hotkey,
        "action_type": action_type,  # "stake" or "unstake"
        "amount": amount,
        "sentiment_score": sentiment_score,
        "timestamp": datetime.utcnow(),
    }

    result = await collection.insert_one(document)
    return str(result.inserted_id)


async def get_stake_history(
    netuid: Optional[int] = None,
    hotkey: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get stake history from the database with optional filters."""
    db = await get_db()
    collection = db[STAKE_HISTORY_COLLECTION]

    query = {}
    if netuid is not None:
        query["netuid"] = netuid
    if hotkey is not None:
        query["hotkey"] = hotkey
    if action_type is not None:
        query["action_type"] = action_type

    cursor = collection.find(query).sort("timestamp", -1).limit(limit)
    results = await cursor.to_list(length=limit)
    return results


# Twitter sentiment operations
async def store_sentiment_data(
    netuid: int,
    tweets: List[Dict[str, Any]],
    sentiment_score: float,
    timestamp: datetime = None,
) -> str:
    """Store Twitter sentiment data in the database."""
    db = await get_db()
    collection = db[SENTIMENT_COLLECTION]

    if timestamp is None:
        timestamp = datetime.utcnow()

    document = {
        "netuid": netuid,
        "tweets": tweets,
        "sentiment_score": sentiment_score,
        "timestamp": timestamp,
    }

    result = await collection.insert_one(document)
    return str(result.inserted_id)


async def get_latest_sentiment(netuid: int) -> Optional[Dict[str, Any]]:
    """Get the latest sentiment data for a specific netuid."""
    db = await get_db()
    collection = db[SENTIMENT_COLLECTION]

    result = await collection.find_one({"netuid": netuid}, sort=[("timestamp", -1)])

    return result


async def get_database_stats() -> Dict[str, Any]:
    """Get statistics about database collections."""
    db = await get_db()

    # Get collection counts
    dividend_count = await db[DIVIDENDS_COLLECTION].count_documents({})
    stake_count = await db[STAKE_HISTORY_COLLECTION].count_documents({})
    sentiment_count = await db[SENTIMENT_COLLECTION].count_documents({})

    # Get latest document from each collection
    latest_dividend = None
    latest_stake = None
    latest_sentiment = None

    dividend_cursor = db[DIVIDENDS_COLLECTION].find().sort("timestamp", -1).limit(1)
    if await dividend_cursor.fetch_next:
        latest_dividend = await dividend_cursor.next()

    stake_cursor = db[STAKE_HISTORY_COLLECTION].find().sort("timestamp", -1).limit(1)
    if await stake_cursor.fetch_next:
        latest_stake = await stake_cursor.next()

    sentiment_cursor = db[SENTIMENT_COLLECTION].find().sort("timestamp", -1).limit(1)
    if await sentiment_cursor.fetch_next:
        latest_sentiment = await sentiment_cursor.next()

    # Format the response
    stats = {
        "collections": {
            DIVIDENDS_COLLECTION: {
                "count": dividend_count,
                "latest_timestamp": (
                    latest_dividend.get("timestamp") if latest_dividend else None
                ),
            },
            STAKE_HISTORY_COLLECTION: {
                "count": stake_count,
                "latest_timestamp": (
                    latest_stake.get("timestamp") if latest_stake else None
                ),
            },
            SENTIMENT_COLLECTION: {
                "count": sentiment_count,
                "latest_timestamp": (
                    latest_sentiment.get("timestamp") if latest_sentiment else None
                ),
            },
        },
        "database_name": DB_NAME,
        "total_documents": dividend_count + stake_count + sentiment_count,
    }

    return stats
