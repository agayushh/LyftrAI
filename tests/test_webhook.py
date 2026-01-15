"""Test webhook endpoint - valid insert, duplicate, signature cases"""

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


class TestWebhookValidInsert:
    """Test valid webhook message insertion"""

    def test_valid_message_insert(self, client, webhook_secret):
        """Test inserting a valid message with correct signature"""
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
        """Test inserting a message without text field"""
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
    """Test duplicate message handling"""

    def test_duplicate_message_idempotent(self, client, webhook_secret):
        """Test that duplicate message_id returns 200 (idempotent)"""
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

        # First insert
        response1 = client.post("/webhook", data=body, headers=headers)
        assert response1.status_code == 200
        assert response1.json() == {"status": "ok"}

        # Duplicate insert - should still return 200
        response2 = client.post("/webhook", data=body, headers=headers)
        assert response2.status_code == 200
        assert response2.json() == {"status": "ok"}

    def test_duplicate_with_different_content(self, client, webhook_secret):
        """Test duplicate message_id with different content still returns 200"""
        message1 = {
            "message_id": "msg_dup_002",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T13:00:00.000Z",
            "text": "Original text",
        }

        body1 = json.dumps(message1).encode()
        signature1 = generate_signature(webhook_secret, body1)

        # First insert
        response1 = client.post(
            "/webhook",
            data=body1,
            headers={"Content-Type": "application/json", "X-Signature": signature1},
        )
        assert response1.status_code == 200

        # Same message_id but different text
        message2 = {
            "message_id": "msg_dup_002",  # Same ID
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
    """Test signature validation cases"""

    def test_missing_signature_header(self, client):
        """Test webhook without X-Signature header returns 401"""
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
        """Test webhook with invalid signature returns 401"""
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
        """Test webhook with signature from wrong secret returns 401"""
        message = {
            "message_id": "msg_005",
            "from": "+919876543210",
            "to": "+14155558100",
            "ts": "2025-01-15T17:00:00.000Z",
            "text": "Test",
        }

        body = json.dumps(message).encode()
        # Generate signature with wrong secret
        wrong_signature = generate_signature("wrong_secret", body)

        response = client.post(
            "/webhook",
            data=body,
            headers={"Content-Type": "application/json", "X-Signature": wrong_signature},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}

    def test_empty_signature(self, client):
        """Test webhook with empty signature returns 401"""
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
    """Test request validation"""

    def test_missing_required_field(self, client, webhook_secret):
        """Test webhook with missing required field"""
        message = {
            "message_id": "msg_008",
            "from": "+919876543210",
            # Missing "to" field
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
