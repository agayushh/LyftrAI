

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["WEBHOOK_SECRET"] = "test_secret_key_12345"

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture
def test_engine():
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
    from app import main, models, storage

    original_engine = models.engine
    models.engine = test_engine
    storage.engine = test_engine

    with TestClient(main.app) as test_client:
        yield test_client

    models.engine = original_engine
    storage.engine = original_engine


@pytest.fixture
def webhook_secret():
    return "test_secret_key_12345"


def generate_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def insert_test_message(client, webhook_secret, message):
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

    def test_total_messages_count(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_messages" in data
        assert data["total_messages"] == 6

    def test_senders_count(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "senders_count" in data
        assert data["senders_count"] == 3

    def test_empty_database_stats(self, client):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["total_messages"] == 0
        assert data["senders_count"] == 0
        assert data["messages_per_sender"] == []
        assert data["first_message_ts"] is None
        assert data["last_message_ts"] is None


class TestStatsMessagesPerSender:

    def test_messages_per_sender_structure(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "messages_per_sender" in data
        assert isinstance(data["messages_per_sender"], list)


        for item in data["messages_per_sender"]:
            assert "from" in item
            assert "count" in item
            assert isinstance(item["count"], int)

    def test_messages_per_sender_counts(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        messages_per_sender = {item["from"]: item["count"] for item in data["messages_per_sender"]}

        assert messages_per_sender["+919876543210"] == 3
        assert messages_per_sender["+919123456789"] == 2
        assert messages_per_sender["+919999999999"] == 1

    def test_messages_per_sender_ordering(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        counts = [item["count"] for item in data["messages_per_sender"]]


        assert counts == sorted(counts, reverse=True)


        assert data["messages_per_sender"][0]["from"] == "+919876543210"
        assert data["messages_per_sender"][0]["count"] == 3

    def test_messages_per_sender_limit_10(self, client, webhook_secret):


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


        assert len(data["messages_per_sender"]) <= 10


class TestStatsTimestamps:

    def test_first_message_timestamp(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "first_message_ts" in data
        assert data["first_message_ts"] == "2025-01-15T10:00:00.000Z"

    def test_last_message_timestamp(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "last_message_ts" in data
        assert data["last_message_ts"] == "2025-01-15T15:00:00.000Z"

    def test_single_message_timestamps(self, client, webhook_secret):

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


        assert data["first_message_ts"] == "2025-01-15T12:00:00.000Z"
        assert data["last_message_ts"] == "2025-01-15T12:00:00.000Z"


class TestStatsDuplicateHandling:

    def test_duplicate_not_counted_twice(self, client, webhook_secret):

        message = {
            "message_id": "dup_stats",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T10:00:00.000Z",
            "text": "Test message",
        }


        insert_test_message(client, webhook_secret, message)
        insert_test_message(client, webhook_secret, message)

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()


        assert data["total_messages"] == 1
        assert data["senders_count"] == 1

        messages_per_sender = {item["from"]: item["count"] for item in data["messages_per_sender"]}
        assert messages_per_sender["+919876543210"] == 1


class TestStatsResponseFormat:

    def test_stats_response_fields(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()


        assert "total_messages" in data
        assert "senders_count" in data
        assert "messages_per_sender" in data
        assert "first_message_ts" in data
        assert "last_message_ts" in data

    def test_stats_data_types(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["total_messages"], int)
        assert isinstance(data["senders_count"], int)
        assert isinstance(data["messages_per_sender"], list)
        assert isinstance(data["first_message_ts"], str)
        assert isinstance(data["last_message_ts"], str)


class TestStatsConsistency:

    def test_stats_consistent_with_messages(self, client, stats_test_messages):

        stats_response = client.get("/stats")
        messages_response = client.get("/messages")

        assert stats_response.status_code == 200
        assert messages_response.status_code == 200

        stats_data = stats_response.json()
        messages_data = messages_response.json()


        assert stats_data["total_messages"] == messages_data["total"]

    def test_stats_sender_counts_accurate(self, client, stats_test_messages):

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()


        total_from_senders = sum(item["count"] for item in data["messages_per_sender"])
        assert total_from_senders == data["total_messages"]
