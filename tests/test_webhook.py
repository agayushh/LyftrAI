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


class TestWebhookValidInsert:

    def test_valid_message_insert(self, client, webhook_secret):
        message = {
            "message_id": "msg_001",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T10:00:00.000Z",
            "text": "Hello World",
        }

        body = json.dumps(message).encode()
        signature = generate_signature(webhook_secret, body)

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": signature},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_valid_message_without_text(self, client, webhook_secret):
        message = {
            "message_id": "msg_002",
            "from": "+919123456789",
            "to": "+14155558100",
            "ts": "2025-01-15T11:00:00.000Z",
        }

        body = json.dumps(message).encode()
        signature = generate_signature(webhook_secret, body)

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": signature},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestWebhookDuplicate:

    def test_duplicate_message_idempotent(self, client, webhook_secret):
        message = {
            "message_id": "msg_dup_001",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T12:00:00.000Z",
            "text": "First message",
        }

        body = json.dumps(message).encode()
        signature = generate_signature(webhook_secret, body)

        headers = {"Content-Type": "application/json", "X-Signature": signature}

        response1 = client.post("/webhook", data=body, headers=headers)
        assert response1.status_code == 200
        assert response1.json() == {"status": "ok"}

        response2 = client.post("/webhook", data=body, headers=headers)
        assert response2.status_code == 200
        assert response2.json() == {"status": "ok"}

    def test_duplicate_with_different_content(self, client, webhook_secret):
        message1 = {
            "message_id": "msg_dup_002",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T13:00:00.000Z",
            "text": "Original text",
        }

        body1 = json.dumps(message1).encode()
        signature1 = generate_signature(webhook_secret, body1)

        response1 = client.post(
            "/webhook",
            data=body1,
            headers={"Content-Type": "application/json", "X-Signature": signature1},
        )
        assert response1.status_code == 200

        message2 = {
            "message_id": "msg_dup_002",
            "from": "+919999999999",
            "to": "+14155558100",
            "ts": "2025-01-15T14:00:00.000Z",
            "text": "Different text",
        }

        body2 = json.dumps(message2).encode()
        signature2 = generate_signature(webhook_secret, body2)

        response2 = client.post(
            "/webhook",
            data=body2,
            headers={"Content-Type": "application/json", "X-Signature": signature2},
        )
        assert response2.status_code == 200


class TestWebhookSignature:

    def test_missing_signature_header(self, client):
        message = {
            "message_id": "msg_003",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T15:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()

        response = client.post("/webhook", data=body, headers={"Content-Type": "application/json"})

        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}

    def test_invalid_signature(self, client):
        message = {
            "message_id": "msg_004",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T16:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": "invalid_signature_12345"},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}

    def test_wrong_secret_signature(self, client):
        message = {
            "message_id": "msg_005",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T17:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()

        wrong_signature = generate_signature("wrong_secret", body)

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": wrong_signature},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}

    def test_empty_signature(self, client):
        message = {
            "message_id": "msg_006",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T18:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()

        response = client.post(
            "/webhook", data=body, headers={"Content-Type": "application/json", "X-Signature": ""}
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}


class TestWebhookValidation:

    def test_missing_required_field(self, client, webhook_secret):
        message = {
            "message_id": "msg_008",
            "from": "+919876543210",
            "ts": "2025-01-15T20:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()
        signature = generate_signature(webhook_secret, body)

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": signature},
        )

        assert response.status_code == 422
