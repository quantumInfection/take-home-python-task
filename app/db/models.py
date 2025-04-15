"""
Pydantic models for database entities.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class TaoDividendModel(BaseModel):
    """Model for Tao dividends data."""

    netuid: int
    hotkey: str
    dividend: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StakeActionModel(BaseModel):
    """Model for stake/unstake actions."""

    netuid: int
    hotkey: str
    action_type: str  # "stake" or "unstake"
    amount: float
    sentiment_score: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SentimentDataModel(BaseModel):
    """Model for Twitter sentiment data."""

    netuid: int
    tweets: List[Dict[str, Any]]
    sentiment_score: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
