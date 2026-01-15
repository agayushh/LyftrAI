# Multi-stage Dockerfile for LyftrAI Webhook Service

# Build stage - install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies to /opt/venv
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage - minimal image
FROM python:3.11-slim

WORKDIR /app

# Copy Python virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY app ./app

# Create non-root user and set ownership
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /opt/venv

# Switch to non-root user
USER appuser

# Use virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
