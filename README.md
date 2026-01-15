# LyftrAI Webhook Service

A production-ready FastAPI webhook receiver with HMAC-SHA256 signature validation, SQLite message storage, and Prometheus metrics.

## Features

- ✅ **Webhook Endpoint** - Receive and validate webhook messages with HMAC-SHA256 signatures
- ✅ **Idempotent Storage** - Duplicate messages handled gracefully (same message_id)
- ✅ **Message Querying** - Pagination, filtering, and full-text search
- ✅ **Analytics** - Message statistics and sender analytics
- ✅ **Metrics** - Prometheus-style metrics for monitoring
- ✅ **Health Checks** - Liveness and readiness probes for orchestration
- ✅ **JSON Logging** - Structured logging for observability
- ✅ **Docker Ready** - Multi-stage Dockerfile and Docker Compose setup

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /webhook (with X-Signature)
       ▼
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  ┌──────────────────────────────┐  │
│  │  HMAC Signature Validation   │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │    Message Storage (SQLite)  │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │   Logging & Metrics          │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

## API Endpoints

### `POST /webhook`
Receive and validate webhook messages.

**Headers:**
- `X-Signature`: HMAC-SHA256 signature of request body
- `Content-Type`: application/json

**Request Body:**
```json
{
  "message_id": "unique-id",
  "from": "+919876543210",
  "to": "+14155558100",
  "ts": "2025-01-15T10:00:00.000Z",
  "text": "Message content"
}
```

**Response:** `200 OK` (idempotent - returns 200 for duplicates too)

### `GET /messages`
List stored messages with pagination and filters.

**Query Parameters:**
- `limit` (default: 50, max: 100) - Number of results
- `offset` (default: 0) - Pagination offset
- `from` - Filter by sender MSISDN
- `since` - Filter by timestamp >= since (ISO-8601)
- `q` - Free-text search in message text
- `message_id` - Filter by exact message_id

**Response:**
```json
{
  "data": [...],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

### `GET /stats`
Get message analytics and statistics.

**Response:**
```json
{
  "total_messages": 1000,
  "senders_count": 50,
  "messages_per_sender": [
    {"from": "+919876543210", "count": 100},
    ...
  ],
  "first_message_ts": "2025-01-01T00:00:00.000Z",
  "last_message_ts": "2025-01-15T12:00:00.000Z"
}
```

### `GET /metrics`
Prometheus-style metrics endpoint.

### `GET /health/live`
Liveness probe - returns 200 if app is running.

### `GET /health/ready`
Readiness probe - checks database and configuration.

## Setup

### Local Development

1. **Clone the repository**
   ```bash
   cd /home/ayush/Desktop/lyftr
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install        # Production dependencies
   make install-dev    # Development dependencies
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set WEBHOOK_SECRET
   ```

5. **Run the application**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### Docker Deployment

1. **Build and run with Docker Compose**
   ```bash
   make up
   ```

2. **View logs**
   ```bash
   make logs
   ```

3. **Stop containers**
   ```bash
   make down
   ```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `WEBHOOK_SECRET` | HMAC secret for signature validation | - | ✅ Yes |
| `DATABASE_URL` | SQLite database URL | `sqlite:///./app.db` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |

## Testing

Run the test suite:
```bash
make test
```

Run specific test file:
```bash
pytest tests/test_webhook.py -v
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Code Quality

Format code:
```bash
make format
```

Run linter:
```bash
make lint
```

## Project Structure

```
lyftr/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # FastAPI app, middleware, routes
│   ├── models.py            # SQLModel database models
│   ├── storage.py           # Database operations
│   ├── logging_utils.py     # JSON logger
│   ├── metrics.py           # Prometheus metrics
│   └── config.py            # Environment configuration
├── tests/
│   ├── test_webhook.py      # Webhook endpoint tests
│   ├── test_messages.py     # Message querying tests
│   └── test_stats.py        # Statistics tests
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Docker Compose configuration
├── requirements.txt         # Production dependencies
├── requirements-dev.txt     # Development dependencies
├── pyproject.toml           # Python project configuration
├── .flake8                  # Flake8 linter configuration
├── Makefile                 # Common development tasks
└── README.md                # This file
```

## Monitoring

The `/metrics` endpoint exposes Prometheus-style metrics:

- `http_requests_total{path, method, status}` - Total HTTP requests
- `webhook_requests_total{result}` - Webhook processing outcomes
- `request_latency_ms` - Request latency histogram

## Logging

All logs are output in JSON format for easy parsing:

```json
{
  "ts": "2025-01-15T10:00:00.000Z",
  "level": "INFO",
  "message": "POST /webhook 200",
  "request_id": "uuid",
  "method": "POST",
  "path": "/webhook",
  "status": 200,
  "latency_ms": 15
}
```

## License

MIT

## Author

LyftrAI Team
