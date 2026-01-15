"""Test /stats endpoint - statistics correctness"""

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
def stats_test_messages(client, webhook_secret):
    """Insert messages for stats testing"""
    messages = [
        {
            "message_id": "s1",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T10:00:00.000Z",
            "text": "Message 1 from Alice",
        },
        {
            "message_id": "s2",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T11:00:00.000Z",
            "text": "Message 2 from Alice",
        },
        {
            "message_id": "s3",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T12:00:00.000Z",
            "text": "Message 3 from Alice",
        },
        {
            "message_id": "s4",
            "from": "+919123456789",
            "to": "+14155558100",
            "ts": "2025-01-15T13:00:00.000Z",
            "text": "Message 1 from Bob",
        },
        {
            "message_id": "s5",
            "from": "+919123456789",
            "to": "+14155558100",
            "ts": "2025-01-15T14:00:00.000Z",
            "text": "Message 2 from Bob",
        },
        {
            "message_id": "s6",
            "from": "+919999999999",
            "to": "+14155558100",
            "ts": "2025-01-15T15:00:00.000Z",
            "text": "Message from Charlie",
        },
    ]

    for msg in messages:
        insert_test_message(client, webhook_secret, msg)

    return messages


class TestStatsBasicCounts:
    """Test basic statistics counts"""

    def test_total_messages_count(self, client, stats_test_messages):
        """Test total_messages count is correct"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_messages" in data
        assert data["total_messages"] == 6

    def test_senders_count(self, client, stats_test_messages):
        """Test senders_count is correct"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "senders_count" in data
        assert data["senders_count"] == 3  # Alice, Bob, Charlie

    def test_empty_database_stats(self, client):
        """Test stats when database is empty"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["total_messages"] == 0
        assert data["senders_count"] == 0
        assert data["messages_per_sender"] == []
        assert data["first_message_ts"] is None
        assert data["last_message_ts"] is None


class TestStatsMessagesPerSender:
    """Test messages_per_sender statistics"""

    def test_messages_per_sender_structure(self, client, stats_test_messages):
        """Test messages_per_sender has correct structure"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "messages_per_sender" in data
        assert isinstance(data["messages_per_sender"], list)

        # Each item should have 'from' and 'count'
        for item in data["messages_per_sender"]:
            assert "from" in item
            assert "count" in item
            assert isinstance(item["count"], int)

    def test_messages_per_sender_counts(self, client, stats_test_messages):
        """Test messages_per_sender has correct counts"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        messages_per_sender = {item["from"]: item["count"] for item in data["messages_per_sender"]}

        assert messages_per_sender["+919876543210"] == 3  # Alice
        assert messages_per_sender["+919123456789"] == 2  # Bob
        assert messages_per_sender["+919999999999"] == 1  # Charlie

    def test_messages_per_sender_ordering(self, client, stats_test_messages):
        """Test messages_per_sender is ordered by count descending"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        counts = [item["count"] for item in data["messages_per_sender"]]

        # Should be in descending order
        assert counts == sorted(counts, reverse=True)

        # First should be Alice (3 messages)
        assert data["messages_per_sender"][0]["from"] == "+919876543210"
        assert data["messages_per_sender"][0]["count"] == 3

    def test_messages_per_sender_limit_10(self, client, webhook_secret):
        """Test messages_per_sender returns top 10 senders only"""
        # Insert messages from 15 different senders
        for i in range(15):
            message = {
                "message_id": f"limit_test_{i}",
                "from": f"+9191234567{i:02d}",
                "to": "+14155558100",
                "ts": f"2025-01-15T{10+i:02d}:00:00.000Z",
                "text": f"Message from sender {i}",
            }
            insert_test_message(client, webhook_secret, message)

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # Should return at most 10 senders
        assert len(data["messages_per_sender"]) <= 10


class TestStatsTimestamps:
    """Test timestamp statistics"""

    def test_first_message_timestamp(self, client, stats_test_messages):
        """Test first_message_ts is correct"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "first_message_ts" in data
        assert data["first_message_ts"] == "2025-01-15T10:00:00.000Z"

    def test_last_message_timestamp(self, client, stats_test_messages):
        """Test last_message_ts is correct"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "last_message_ts" in data
        assert data["last_message_ts"] == "2025-01-15T15:00:00.000Z"

    def test_single_message_timestamps(self, client, webhook_secret):
        """Test timestamps when only one message exists"""
        message = {
            "message_id": "single",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T12:00:00.000Z",
            "text": "Only message",
        }
        insert_test_message(client, webhook_secret, message)

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # First and last should be the same
        assert data["first_message_ts"] == "2025-01-15T12:00:00.000Z"
        assert data["last_message_ts"] == "2025-01-15T12:00:00.000Z"


class TestStatsDuplicateHandling:
    """Test stats with duplicate messages"""

    def test_duplicate_not_counted_twice(self, client, webhook_secret):
        """Test duplicate messages are not counted twice in stats"""
        message = {
            "message_id": "dup_stats",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T10:00:00.000Z",
            "text": "Test message",
        }

        # Insert same message twice
        insert_test_message(client, webhook_secret, message)
        insert_test_message(client, webhook_secret, message)

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # Should only count once
        assert data["total_messages"] == 1
        assert data["senders_count"] == 1

        messages_per_sender = {item["from"]: item["count"] for item in data["messages_per_sender"]}
        assert messages_per_sender["+919876543210"] == 1


class TestStatsResponseFormat:
    """Test stats response format"""

    def test_stats_response_fields(self, client, stats_test_messages):
        """Test stats response contains all required fields"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "total_messages" in data
        assert "senders_count" in data
        assert "messages_per_sender" in data
        assert "first_message_ts" in data
        assert "last_message_ts" in data

    def test_stats_data_types(self, client, stats_test_messages):
        """Test stats response has correct data types"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["total_messages"], int)
        assert isinstance(data["senders_count"], int)
        assert isinstance(data["messages_per_sender"], list)
        assert isinstance(data["first_message_ts"], str)
        assert isinstance(data["last_message_ts"], str)


class TestStatsConsistency:
    """Test stats consistency with other endpoints"""

    def test_stats_consistent_with_messages(self, client, stats_test_messages):
        """Test stats total matches /messages total"""
        stats_response = client.get("/stats")
        messages_response = client.get("/messages")

        assert stats_response.status_code == 200
        assert messages_response.status_code == 200

        stats_data = stats_response.json()
        messages_data = messages_response.json()

        # Total should match
        assert stats_data["total_messages"] == messages_data["total"]

    def test_stats_sender_counts_accurate(self, client, stats_test_messages):
        """Test messages_per_sender counts are accurate"""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # Sum of all sender counts should equal total messages
        total_from_senders = sum(item["count"] for item in data["messages_per_sender"])
        assert total_from_senders == data["total_messages"]
