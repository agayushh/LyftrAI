

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
def sample_messages(client, webhook_secret):
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

    def test_default_pagination(self, client, sample_messages):

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

        response = client.get("/messages?limit=2")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert len(data["data"]) == 2

        assert data["data"][0]["message_id"] == "m1"
        assert data["data"][1]["message_id"] == "m2"

    def test_offset_pagination(self, client, sample_messages):

        response = client.get("/messages?limit=2&offset=2")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 2
        assert len(data["data"]) == 2

        assert data["data"][0]["message_id"] == "m3"
        assert data["data"][1]["message_id"] == "m4"

    def test_offset_beyond_total(self, client, sample_messages):

        response = client.get("/messages?offset=10")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert len(data["data"]) == 0

    def test_limit_max_constraint(self, client, sample_messages):

        response = client.get("/messages?limit=150")


        assert response.status_code == 422

    def test_limit_min_constraint(self, client, sample_messages):

        response = client.get("/messages?limit=0")


        assert response.status_code == 422

    def test_negative_offset(self, client, sample_messages):

        response = client.get("/messages?offset=-1")

        assert response.status_code == 422


class TestMessagesFilters:

    def test_filter_by_from(self, client, sample_messages):

        response = client.get("/messages?from=%2B919876543210")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["data"]) == 3


        for msg in data["data"]:
            assert msg["from"] == "+919876543210"

    def test_filter_by_since(self, client, sample_messages):

        response = client.get("/messages?since=2025-01-15T12:00:00.000Z")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["data"]) == 3


        for msg in data["data"]:
            assert msg["ts"] >= "2025-01-15T12:00:00.000Z"

    def test_filter_by_text_search(self, client, sample_messages):

        response = client.get("/messages?q=Alice")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["data"]) == 3


        for msg in data["data"]:
            assert "Alice" in msg["text"]

    def test_filter_by_text_case_insensitive(self, client, sample_messages):

        response = client.get("/messages?q=alice")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3

    def test_filter_by_message_id(self, client, sample_messages):

        response = client.get("/messages?message_id=m3")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["message_id"] == "m3"

    def test_combined_filters(self, client, sample_messages):

        response = client.get("/messages?from=%2B919876543210&since=2025-01-15T12:00:00.000Z")

        assert response.status_code == 200
        data = response.json()


        assert data["total"] == 2
        assert len(data["data"]) == 2

        for msg in data["data"]:
            assert msg["from"] == "+919876543210"
            assert msg["ts"] >= "2025-01-15T12:00:00.000Z"

    def test_filter_with_pagination(self, client, sample_messages):

        response = client.get("/messages?from=%2B919876543210&limit=2&offset=1")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["data"]) == 2


        assert data["data"][0]["message_id"] == "m3"
        assert data["data"][1]["message_id"] == "m5"

    def test_no_results_filter(self, client, sample_messages):

        response = client.get("/messages?from=%2B910000000000")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert len(data["data"]) == 0


class TestMessagesOrdering:

    def test_messages_ordered_by_timestamp(self, client, sample_messages):

        response = client.get("/messages")

        assert response.status_code == 200
        data = response.json()


        timestamps = [msg["ts"] for msg in data["data"]]
        assert timestamps == sorted(timestamps)

    def test_ordering_with_filters(self, client, sample_messages):

        response = client.get("/messages?from=%2B919876543210")

        assert response.status_code == 200
        data = response.json()


        timestamps = [msg["ts"] for msg in data["data"]]
        assert timestamps == sorted(timestamps)


class TestMessagesResponseFormat:

    def test_message_fields(self, client, sample_messages):

        response = client.get("/messages?limit=1")

        assert response.status_code == 200
        data = response.json()

        message = data["data"][0]
        assert "message_id" in message
        assert "from" in message
        assert "to" in message
        assert "ts" in message
        assert "text" in message


        assert "created_at" not in message

    def test_empty_database(self, client):

        response = client.get("/messages")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["data"] == []
        assert data["limit"] == 50
        assert data["offset"] == 0
