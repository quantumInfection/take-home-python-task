import logging
import json
import httpx
from typing import Dict, Any, List
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)


class SentimentService:
    """Service for sentiment analysis of Twitter data using Datura.ai and Chutes.ai."""

    def __init__(self):
        """Initialize API keys for external services."""
        self.datura_api_key = settings.DATURA_API_KEY
        self.chutes_api_key = settings.CHUTES_API_KEY

    async def search_tweets(self, netuid: int) -> List[Dict[str, Any]]:
        """
        Search Twitter for tweets about Bittensor subnet using Datura.ai.

        Args:
            netuid: Subnet ID to search for

        Returns:
            List of tweets matching the search query
        """
        logger.info(f"Searching tweets for Bittensor netuid {netuid}")

        search_query = f"Bittensor netuid {netuid}"
        url = "https://api.datura.ai/api/twitter-search"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.datura_api_key}",
        }

        payload = {
            "query": search_query,
            "max_results": 20,  # Reasonable number of tweets for analysis
            "sort_order": "relevancy",  # Get most relevant tweets first
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        logger.error(
                            f"Datura API error: {response.status}, {await response.text()}"
                        )
                        raise Exception(
                            f"Datura API returned status code {response.status}"
                        )

                    data = await response.json()

                    if not data.get("data") or not isinstance(data["data"], list):
                        logger.warning(f"Datura API returned no tweets: {data}")
                        return []

                    logger.info(
                        f"Found {len(data['data'])} tweets about Bittensor netuid {netuid}"
                    )
                    return data["data"]

        except Exception as e:
            logger.error(f"Error searching tweets: {str(e)}", exc_info=True)
            raise

    async def analyze_sentiment_with_llm(self, tweets: List[Dict[str, Any]]) -> float:
        """
        Analyze sentiment of tweets using Chutes.ai LLM.

        Args:
            tweets: List of tweets to analyze

        Returns:
            Sentiment score from -100 (very negative) to +100 (very positive)
        """
        logger.info(f"Analyzing sentiment of {len(tweets)} tweets with Chutes.ai LLM")

        if not tweets:
            logger.warning("No tweets to analyze, returning neutral sentiment (0)")
            return 0.0

        # Extract tweet texts for analysis
        tweet_texts = [tweet.get("text", "") for tweet in tweets if tweet.get("text")]

        if not tweet_texts:
            logger.warning(
                "No tweet texts found for analysis, returning neutral sentiment (0)"
            )
            return 0.0

        # Join tweets for context but limit text length to avoid token limits
        combined_text = "\n".join(tweet_texts)
        if len(combined_text) > 8000:  # Reasonable token limit for most LLMs
            combined_text = combined_text[:8000] + "..."

        # Define the prompt for the LLM
        prompt = f"""
        Analyze the sentiment of the following tweets about Bittensor. Rate the overall sentiment on a 
        scale from -100 (extremely negative) to +100 (extremely positive), where 0 is neutral.
        
        Return ONLY a number between -100 and +100 indicating the sentiment score.
        
        Tweets:
        {combined_text}
        
        Sentiment score:
        """

        url = (
            "https://api.chutes.ai/api/v1/predict/20acffc0-0c5f-58e3-97af-21fc0b261ec4"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.chutes_api_key}",
        }

        payload = {
            "input": prompt,
            "options": {
                "temperature": 0.1,  # Low temperature for more consistent results
                "top_p": 0.9,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        logger.error(
                            f"Chutes API error: {response.status}, {await response.text()}"
                        )
                        raise Exception(
                            f"Chutes API returned status code {response.status}"
                        )

                    data = await response.json()

                    # Extract sentiment score from LLM response
                    llm_output = data.get("output", "0").strip()

                    # Try to parse the sentiment score
                    try:
                        # Extract just the number from the response
                        sentiment_score = float(llm_output.replace(",", "").strip())
                        # Ensure the score is within the valid range
                        sentiment_score = max(min(sentiment_score, 100), -100)
                        logger.info(f"Sentiment analysis result: {sentiment_score}")
                        return sentiment_score
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Could not parse sentiment score from LLM output: {llm_output}"
                        )
                        return 0.0  # Default to neutral sentiment

        except Exception as e:
            logger.error(f"Error analyzing sentiment: {str(e)}", exc_info=True)
            raise

    async def analyze_sentiment_for_subnet(self, netuid: int) -> Dict[str, Any]:
        """
        Complete sentiment analysis workflow for a subnet.
        1. Search for tweets about the subnet
        2. Analyze sentiment of the tweets

        Args:
            netuid: Subnet ID to analyze

        Returns:
            Dictionary with sentiment analysis results
        """
        try:
            # Search for tweets
            tweets = await self.search_tweets(netuid)

            # If no tweets found, return neutral sentiment
            if not tweets:
                return {
                    "success": True,
                    "netuid": netuid,
                    "sentiment_score": 0.0,
                    "num_tweets_analyzed": 0,
                    "message": "No tweets found for analysis",
                }

            # Analyze sentiment
            sentiment_score = await self.analyze_sentiment_with_llm(tweets)

            return {
                "success": True,
                "netuid": netuid,
                "sentiment_score": sentiment_score,
                "num_tweets_analyzed": len(tweets),
            }

        except Exception as e:
            logger.error(
                f"Error in sentiment analysis workflow: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "netuid": netuid,
                "error": str(e),
            }
