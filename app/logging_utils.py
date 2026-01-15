import json
import logging
import time
import uuid
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from . import metrics


class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_data = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status"):
            log_data["status"] = record.status
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "message_id"):
            log_data["message_id"] = record.message_id
        if hasattr(record, "dup"):
            log_data["dup"] = record.dup
        if hasattr(record, "result"):
            log_data["result"] = record.result

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO"):
    logger = logging.getLogger()
    logger.setLevel(log_level.upper())
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger


class LoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()

        response = await call_next(request)

        latency_ms = int((time.time() - start_time) * 1000)

        if request.url.path != "/metrics":
            metrics.record_http_request(
                path=request.url.path, method=request.method, status=response.status_code
            )
            metrics.record_request_latency(latency_ms)

        logger = logging.getLogger()
        logger.info(
            f"{request.method} {request.url.path} {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            },
        )

        return response


def log_webhook_event(request_id: str, message_id: str, duplicate: bool, result: str):
    logger = logging.getLogger()
    logger.info(
        f"Webhook processed: {message_id}",
        extra={
            "request_id": request_id,
            "message_id": message_id,
            "dup": duplicate,
            "result": result,
        },
    )
