# Bittensor Tao Dividends API Service

A high-performance, asynchronous API service that provides authenticated access to Bittensor blockchain data with sentiment-driven trading capabilities.

## Project Overview

This service implements a fully asynchronous FastAPI application that:

1. Provides an authenticated endpoint to query Tao dividends from the Bittensor blockchain
2. Implements intelligent caching via Redis (2-minute TTL)
3. Features optional automated trading based on Twitter sentiment analysis:
   - Analyzes tweets about specified subnets using Datura.ai
   - Processes sentiment using Chutes.ai LLM
   - Stakes or unstakes TAO based on sentiment score (-100 to +100)
4. Utilizes Celery workers for background task processing
5. Stores historical data in a high-concurrency asynchronous database
6. Handles ~1000 concurrent requests with minimal latency

## Architecture

The service is built with modern async-first patterns:

- **FastAPI**: Handles HTTP requests with async endpoints
- **Redis**: Dual purpose as cache and Celery message broker
- **Celery**: Background processing for sentiment analysis and blockchain interactions
- **MongoDB**: Asynchronous storage via Motor client
- **Docker**: Full containerization of all services

## Features

### Core Features

- **Blockchain Data Query**: Asynchronous querying of Bittensor TaoDividendsPerSubnet data
- **Intelligent Caching**: Redis-based caching with 2-minute TTL for fast responses
- **API Authentication**: Secure API key authentication via X-API-Key header
- **Sentiment Analysis**: Tweet analysis via Datura.ai and Chutes.ai LLM
- **Automated Trading**: Sentiment-based stake/unstake decisions
- **Background Processing**: Non-blocking API responses with Celery task processing
- **Persistent Storage**: Historical data retention in MongoDB

### Extra Features

- **Complete Type Annotations**: 100% type coverage for enhanced reliability
- **Error Handling**: Graceful handling of API timeouts and blockchain failures
- **Comprehensive Logging**: Detailed event tracking throughout the system

## API Documentation

### Authentication

All endpoints require an API key:

```
X-API-Key: YOUR_API_KEY
```

Set the API key in the `.env` file (`API_KEY` variable).

### Endpoints

#### GET /api/v1/tao_dividends

Query Tao dividends data for specified subnet and hotkey.

**Parameters:**
- `netuid` (optional): Subnet ID number
  - If omitted: returns data for all subnets
  - Default: 18
- `hotkey` (optional): Account/wallet address
  - If omitted: returns data for all hotkeys in the subnet
  - Default: "5FFApaS75bv5pJHfAp2FVLBj9ZaXuFDjEypsaBNc1wCfe52v"
- `trade` (optional): Triggers sentiment-based trading
  - Default: false

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tao_dividends?netuid=18&hotkey=5FFApaS75bv5pJHfAp2FVLBj9ZaXuFDjEypsaBNc1wCfe52v&trade=true" \
  -H "X-API-Key: your_api_key_here"
```

**Example Response:**
```json
{
  "netuid": 18,
  "hotkey": "5FFApaS75bv5pJHfAp2FVLBj9ZaXuFDjEypsaBNc1wCfe52v",
  "dividend": 123456789,
  "timestamp": "2025-04-16T14:30:00Z",
  "cached": true,
  "trade_enqueued": true
}
```

#### GET /api/health

Simple health check endpoint.

**Example Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-04-16T14:30:00Z"
}
```

## Setup & Installation

### Prerequisites

- Docker and Docker Compose

### Environment Configuration

1. Clone the repository:
   ```bash
   git clone https://github.com/quantumInfection/take-home-python-task.git
   cd take-home-python-task
   ```

2. Create an `.env` file from the template:
   ```bash
   cp .env.example .env
   ```

3. Edit the `.env` file and set the required variables:
   ```
   # API Configuration
   API_KEY=your_secret_key_here
   
   # External Services
   DATURA_API_KEY=dt_$q4qWC2K5mwT5BnNh0ZNF9MfeMDJenJ-pddsi_rE1FZ8
   CHUTES_API_KEY=cpk_9402c24cc755440b94f4b0931ebaa272.7a748b60e4a557f6957af9ce25778f49.8huXjHVlrSttzKuuY0yU2Fy4qEskr5J0
   
   # Blockchain Configuration
   BITTENSOR_NETWORK=test
   BITTENSOR_WALLET_SEED=diamond like interest affair safe clarify lawsuit innocent beef van grief color
   
   # Database & Cache
   MONGO_URI=mongodb://mongo:27017/
   REDIS_URI=redis://redis:6379/0
   ```

### Running with Docker

Launch all services with a single command:

```bash
docker compose up --build
```

This will start:
- FastAPI application on http://localhost:8000
- Celery worker for background tasks
- Redis cache and message broker
- MongoDB database
- API documentation at http://localhost:8000/docs

## Project Structure

```
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                  # Application container definition
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── task_readme.md              # Original task description
└── app/
    ├── main.py                 # FastAPI application entry point
    ├── worker.py               # Celery worker configuration
    ├── api/
    │   ├── __init__.py
    │   └── routes.py           # API endpoints definitions
    ├── auth/
    │   ├── __init__.py
    │   └── auth.py             # Auth middleware and dependencies
    ├── core/
    │   ├── __init__.py
    │   └── config.py           # Configuration and settings
    ├── db/
    │   ├── __init__.py
    │   ├── models.py           # Data models
    │   └── mongo.py            # MongoDB async connection
    ├── services/
    │   ├── __init__.py
    │   ├── blockchain_service.py  # Bittensor integration
    │   ├── cache_service.py       # Redis caching logic
    │   └── sentiment_service.py   # Twitter sentiment analysis
    └── tasks/
        ├── blockchain_tasks.py    # Blockchain interaction tasks
        └── sentiment_tasks.py     # Sentiment analysis tasks
```

## Implementation Details

### Asynchronous Design

The entire application uses asyncio for non-blocking I/O:
- FastAPI routes are defined with `async def`
- Database queries use Motor's async client
- Blockchain interactions use AsyncSubtensor
- External API calls use aiohttp

### Caching Strategy

- Redis is used to cache blockchain query results for 2 minutes
- Cache keys are constructed from netuid and hotkey parameters
- Cache hits avoid blockchain queries for improved performance

### Sentiment Analysis & Trading

When `trade=true`:
1. A Celery task is dispatched to search tweets about the specified subnet
2. Tweets are analyzed through Chutes.ai LLM to get sentiment (-100 to +100)
3. For positive sentiment: add_stake (.01 tao * sentiment score)
4. For negative sentiment: unstake (.01 tao * sentiment score)

### Security Considerations

- API endpoints are protected with API key authentication via X-API-Key header
- All sensitive data (API keys, blockchain seeds) are stored as environment variables
- Input validation occurs at API and service layers

## Development Decisions

### Technology Choices

- **FastAPI**: Selected for its async-first design and automatic OpenAPI documentation
- **MongoDB/Motor**: Chosen for high-concurrency support and async capabilities
- **Redis**: Used for both caching and as a Celery broker for simplicity
- **Celery**: Implemented for reliable background task processing

### Trade-offs & Considerations

- **Caching Duration**: 2-minute TTL balances freshness vs. performance
- **Authentication**: Simple API key via X-API-Key header used for security
- **Error Handling**: Prioritized graceful degradation when external services fail

## Contributing

This project is a take-home assignment and not actively maintained. However, if you'd like to extend or modify it, please follow these guidelines:

1. Create feature branches from `main`
2. Follow type hints and docstring conventions
3. Update documentation as needed

## License

This project is provided for demonstration purposes only.