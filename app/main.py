import hashlib
import hmac
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import SQLModel

from . import metrics, storage
from .config import log_level, webhook_secret
from .logging_utils import LoggingMiddleware, log_webhook_event, setup_logging
from .models import engine

setup_logging(log_level)

app = FastAPI(title="LyftrAI Webhook Service")

app.add_middleware(LoggingMiddleware)


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):

    if request.url.path == "/webhook":
        metrics.record_webhook_request("validation_error")

    return JSONResponse(status_code=422, content={"detail": exc.errors()})


class WebhookMessage(BaseModel):


    message_id: str = Field(..., description="Unique message identifier")
    from_: str = Field(..., alias="from", description="Sender MSISDN")
    to: str = Field(..., description="Receiver MSISDN")
    ts: str = Field(..., description="ISO-8601 timestamp")
    text: Optional[str] = Field(None, description="Message text content")


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    if not secret:
        return False

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def webhook(request: Request, message: WebhookMessage):
    """
    Receive and validate webhook messages.

    Validates HMAC signature and stores message in database.
    Returns 200 for both new and duplicate messages (idempotent).
    """

    body = await request.body()


    signature = request.headers.get("X-Signature", "")

    if not signature:
        metrics.record_webhook_request("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid signature")


    if not verify_signature(webhook_secret, body, signature):
        metrics.record_webhook_request("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid signature")


    message_data = {
        "message_id": message.message_id,
        "from": message.from_,
        "to": message.to,
        "ts": message.ts,
        "text": message.text or "",
    }


    result = storage.save_message(message_data)


    webhook_result = "duplicate" if result["duplicate"] else "created"
    metrics.record_webhook_request(webhook_result)


    request_id = getattr(request.state, "request_id", "unknown")
    log_webhook_event(
        request_id=request_id,
        message_id=message.message_id,
        duplicate=result["duplicate"],
        result=webhook_result,
    )

    return {"status": "ok"}


@app.get("/messages")
async def get_messages(
    limit: int = Query(50, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    from_: Optional[str] = Query(None, alias="from", description="Filter by sender MSISDN"),
    since: Optional[str] = Query(None, description="Filter by timestamp >= since"),
    q: Optional[str] = Query(None, description="Free-text search in message text"),
    message_id: Optional[str] = Query(None, description="Filter by exact message_id"),
):
    """
    List stored messages with pagination and filters.

    Returns messages ordered by timestamp (ascending, deterministic).
    """

    filters = {}
    if from_:
        filters["from"] = from_
    if since:
        filters["since"] = since
    if q:
        filters["q"] = q
    if message_id:
        filters["message_id"] = message_id


    messages = storage.get_messages(filters=filters, limit=limit, offset=offset)
    total = storage.count_messages(filters=filters)

    return {"data": messages, "total": total, "limit": limit, "offset": offset}


@app.get("/stats")
async def get_stats():
    """
    Get message analytics and statistics.

    Returns aggregated data including total messages, sender counts, etc.
    """
    stats = storage.get_stats()
    return stats


@app.get("/health/live")
async def health_live():
    """Liveness probe - always returns 200 if app is running."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """
    Readiness probe - checks if app is ready to serve traffic.

    Verifies:
    - Database is reachable
    - WEBHOOK_SECRET is configured

    Returns 200 if ready, 503 if not ready.
    """

    if not webhook_secret:
        return JSONResponse(
            status_code=503, content={"status": "not ready", "reason": "WEBHOOK_SECRET not set"}
        )


    if not storage.check_db_health():
        return JSONResponse(
            status_code=503, content={"status": "not ready", "reason": "database not reachable"}
        )

    return {"status": "ok"}


@app.get("/metrics")
async def get_metrics():
    """
    Expose Prometheus-style metrics.

    Returns metrics in Prometheus text exposition format including:
    - http_requests_total: Counter for all HTTP requests
    - webhook_requests_total: Counter for webhook processing outcomes
    - request_latency_ms: Histogram for request latency
    """
    return metrics.get_metrics()


@app.get("/")
async def root():
    return {"message": "LyftrAI Webhook Service", "version": "1.0"}
