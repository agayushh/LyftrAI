"""
Prometheus-style metrics for monitoring and observability.

Metrics exposed:
- http_requests_total{path, method, status}: Counter for all HTTP requests
- webhook_requests_total{result}: Counter for webhook processing outcomes
- request_latency_ms: Histogram for request latency in milliseconds
"""

from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# Create a custom registry to avoid conflicts
registry = CollectorRegistry()

# HTTP requests counter
# Tracks all HTTP requests by path, method, and status code
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["path", "method", "status"], registry=registry
)

# Webhook requests counter
# Tracks webhook processing outcomes
webhook_requests_total = Counter(
    "webhook_requests_total", "Total webhook requests by result", ["result"], registry=registry
)

# Request latency histogram
# Tracks request duration in milliseconds with buckets
request_latency_ms = Histogram(
    "request_latency_ms",
    "Request latency in milliseconds",
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
    registry=registry,
)


def record_http_request(path: str, method: str, status: int):
    """Record an HTTP request in metrics"""
    http_requests_total.labels(path=path, method=method, status=str(status)).inc()


def record_webhook_request(result: str):
    """
    Record a webhook request outcome.

    Valid results:
    - created: New message created
    - duplicate: Duplicate message (idempotent)
    - invalid_signature: Signature verification failed
    - validation_error: Request validation failed
    """
    webhook_requests_total.labels(result=result).inc()


def record_request_latency(latency_ms: float):
    """Record request latency in milliseconds"""
    request_latency_ms.observe(latency_ms)


def get_metrics() -> Response:
    """
    Generate Prometheus metrics in text exposition format.
    Returns a Response with metrics data.
    """
    metrics_data = generate_latest(registry)
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
