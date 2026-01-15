"""Test /messages endpoint - pagination and filters"""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test webhook secret before importing app
os.environ["WEBHOOK_SECRET"] = "test_secret_key_12345"

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture
def test_engine():
    """Create test database engine"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models import Message

    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(test_engine):
    """Create test client"""
    from app import main, models, storage

    # Override engine
    original_engine = models.engine
    models.engine = test_engine
    storage.engine = test_engine

    with TestClient(main.app) as test_client:
        yield test_client

    # Restore
    models.engine = original_engine
    storage.engine = original_engine


@pytest.fixture
def webhook_secret():
    """Return webhook secret"""
    return "test_secret_key_12345"


def generate_signature(secret: str, body: bytes) -> str:
    """Generate HMAC-SHA256 signature"""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def insert_test_message(client, webhook_secret, message):
    """Helper to insert a message via webhook"""
    body = json.dumps(message).encode()
    signature = generate_signature(webhook_secret, body)

    response = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )
    return response


@pytest.fixture
def sample_messages(client, webhook_secret):
    """Insert sample messages for testing"""
    messages = [
        {
            "message_id": "m1",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T10:00:00.000Z",
            "text": "Hello from Alice",
        },
        {
            "message_id": "m2",
            "from": "+919123456789",
            "to": "+14155558100",
            "ts": "2025-01-15T11:00:00.000Z",
            "text": "Hello from Bob",
        },
        {
            "message_id": "m3",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T12:00:00.000Z",
            "text": "Second message from Alice",
        },
        {
            "message_id": "m4",
            "from": "+919999999999",
            "to": "+14155558100",
            "ts": "2025-01-15T13:00:00.000Z",
            "text": "Message from Charlie",
        },
        {
            "message_id": "m5",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T14:00:00.000Z",
            "text": "Third message from Alice",
        },
    ]

    for msg in messages:
        insert_test_message(client, webhook_secret, msg)

    return messages


class TestMessagesPagination:
    """Test pagination functionality"""

    def test_default_pagination(self, client, sample_messages):
        """Test default limit and offset"""
        response = client.get("/messages")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        assert data["total"] == 5
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["data"]) == 5

    def test_custom_limit(self, client, sample_messages):
        """Test custom limit parameter"""
        response = client.get("/messages?limit=2")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert len(data["data"]) == 2
        # Should return first 2 messages (ordered by ts)
        assert data["data"][0]["message_id"] == "m1"
        assert data["data"][1]["message_id"] == "m2"

    def test_offset_pagination(self, client, sample_messages):
        """Test offset parameter"""
        response = client.get("/messages?limit=2&offset=2")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 2
        assert len(data["data"]) == 2
        # Should return messages 3 and 4
        assert data["data"][0]["message_id"] == "m3"
        assert data["data"][1]["message_id"] == "m4"

    def test_offset_beyond_total(self, client, sample_messages):
        """Test offset beyond total messages"""
        response = client.get("/messages?offset=10")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert len(data["data"]) == 0

    def test_limit_max_constraint(self, client, sample_messages):
        """Test limit maximum constraint (100)"""
        response = client.get("/messages?limit=150")

        # Should be rejected by validation
        assert response.status_code == 422

    def test_limit_min_constraint(self, client, sample_messages):
        """Test limit minimum constraint (1)"""
        response = client.get("/messages?limit=0")

        # Should be rejected by validation
        assert response.status_code == 422

    def test_negative_offset(self, client, sample_messages):
        """Test negative offset is rejected"""
        response = client.get("/messages?offset=-1")

        assert response.status_code == 422


class TestMessagesFilters:
    """Test filtering functionality"""

    def test_filter_by_from(self, client, sample_messages):
        """Test filtering by sender (from)"""
        response = client.get("/messages?from=%2B919876543210")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3  # Alice sent 3 messages
        assert len(data["data"]) == 3

        # All messages should be from Alice
        for msg in data["data"]:
            assert msg["from"] == "+919876543210"

    def test_filter_by_since(self, client, sample_messages):
        """Test filtering by timestamp (since)"""
        response = client.get("/messages?since=2025-01-15T12:00:00.000Z")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3  # m3, m4, m5
        assert len(data["data"]) == 3

        # All messages should be >= since timestamp
        for msg in data["data"]:
            assert msg["ts"] >= "2025-01-15T12:00:00.000Z"

    def test_filter_by_text_search(self, client, sample_messages):
        """Test free-text search in message text"""
        response = client.get("/messages?q=Alice")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3  # 3 messages contain "Alice"
        assert len(data["data"]) == 3

        # All messages should contain "Alice"
        for msg in data["data"]:
            assert "Alice" in msg["text"]

    def test_filter_by_text_case_insensitive(self, client, sample_messages):
        """Test text search is case-insensitive"""
        response = client.get("/messages?q=alice")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3

    def test_filter_by_message_id(self, client, sample_messages):
        """Test filtering by exact message_id"""
        response = client.get("/messages?message_id=m3")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["message_id"] == "m3"

    def test_combined_filters(self, client, sample_messages):
        """Test combining multiple filters"""
        response = client.get("/messages?from=%2B919876543210&since=2025-01-15T12:00:00.000Z")

        assert response.status_code == 200
        data = response.json()

        # Alice's messages after 12:00 (m3, m5)
        assert data["total"] == 2
        assert len(data["data"]) == 2

        for msg in data["data"]:
            assert msg["from"] == "+919876543210"
            assert msg["ts"] >= "2025-01-15T12:00:00.000Z"

    def test_filter_with_pagination(self, client, sample_messages):
        """Test filters combined with pagination"""
        response = client.get("/messages?from=%2B919876543210&limit=2&offset=1")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3  # Total matching filter
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["data"]) == 2  # Second page

        # Should return m3 and m5 (skipping m1)
        assert data["data"][0]["message_id"] == "m3"
        assert data["data"][1]["message_id"] == "m5"

    def test_no_results_filter(self, client, sample_messages):
        """Test filter that matches no messages"""
        response = client.get("/messages?from=%2B910000000000")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert len(data["data"]) == 0


class TestMessagesOrdering:
    """Test message ordering"""

    def test_messages_ordered_by_timestamp(self, client, sample_messages):
        """Test messages are ordered by timestamp ascending"""
        response = client.get("/messages")

        assert response.status_code == 200
        data = response.json()

        # Verify ascending order
        timestamps = [msg["ts"] for msg in data["data"]]
        assert timestamps == sorted(timestamps)

    def test_ordering_with_filters(self, client, sample_messages):
        """Test ordering is maintained with filters"""
        response = client.get("/messages?from=%2B919876543210")

        assert response.status_code == 200
        data = response.json()

        # Verify ascending order
        timestamps = [msg["ts"] for msg in data["data"]]
        assert timestamps == sorted(timestamps)


class TestMessagesResponseFormat:
    """Test response format"""

    def test_message_fields(self, client, sample_messages):
        """Test message objects contain correct fields"""
        response = client.get("/messages?limit=1")

        assert response.status_code == 200
        data = response.json()

        message = data["data"][0]
        assert "message_id" in message
        assert "from" in message
        assert "to" in message
        assert "ts" in message
        assert "text" in message

        # Should NOT include created_at (server timestamp)
        assert "created_at" not in message

    def test_empty_database(self, client):
        """Test response when database is empty"""
        response = client.get("/messages")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["data"] == []
        assert data["limit"] == 50
        assert data["offset"] == 0
