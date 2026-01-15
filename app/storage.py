from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from .models import Message, engine


def save_message(data: dict) -> dict:
    """
    Insert a message into the database.
    Handles duplicate message_id gracefully (idempotent).

    Returns: {"status": "ok", "duplicate": bool}
    """
    try:
        # Create message with server timestamp
        message = Message(
            message_id=data["message_id"],
            from_msisdn=data["from"],
            to_msisdn=data["to"],
            ts=data["ts"],
            text=data.get("text", ""),
            created_at=datetime.utcnow().isoformat() + "Z",
        )

        with Session(engine) as session:
            session.add(message)
            session.commit()

        return {"status": "ok", "duplicate": False}

    except IntegrityError:
        # Duplicate message_id - this is OK, idempotent behavior
        return {"status": "ok", "duplicate": True}


def get_messages(filters: Optional[dict] = None, limit: int = 50, offset: int = 0) -> list:
    """
    Query messages with optional filters and pagination.

    Filters:
    - from: filter by from_msisdn (exact match)
    - since: filter by ts >= since (ISO-8601 timestamp)
    - q: free-text search in text field (case-insensitive substring)
    - message_id: filter by exact message_id

    Returns: List of message dicts
    """
    filters = filters or {}

    with Session(engine) as session:
        statement = select(Message)

        # Apply filters
        if "from" in filters:
            statement = statement.where(Message.from_msisdn == filters["from"])

        if "since" in filters:
            statement = statement.where(Message.ts >= filters["since"])

        if "q" in filters:
            # Case-insensitive substring search
            statement = statement.where(Message.text.ilike(f"%{filters['q']}%"))

        if "message_id" in filters:
            statement = statement.where(Message.message_id == filters["message_id"])

        # Order by ts ASC for deterministic ordering
        statement = statement.order_by(Message.ts.asc())

        # Apply pagination
        statement = statement.offset(offset).limit(limit)

        results = session.exec(statement).all()

        # Convert to dicts
        return [
            {
                "message_id": msg.message_id,
                "from": msg.from_msisdn,
                "to": msg.to_msisdn,
                "ts": msg.ts,
                "text": msg.text,
            }
            for msg in results
        ]


def count_messages(filters: Optional[dict] = None) -> int:
    """
    Count total messages matching the given filters.
    """
    filters = filters or {}

    with Session(engine) as session:
        statement = select(func.count()).select_from(Message)

        # Apply same filters as get_messages
        if "from" in filters:
            statement = statement.where(Message.from_msisdn == filters["from"])

        if "since" in filters:
            statement = statement.where(Message.ts >= filters["since"])

        if "q" in filters:
            statement = statement.where(Message.text.ilike(f"%{filters['q']}%"))

        if "message_id" in filters:
            statement = statement.where(Message.message_id == filters["message_id"])

        count = session.exec(statement).one()
        return count


def get_stats() -> dict:
    """
    Get aggregated statistics about messages.

    Returns:
    {
        "total_messages": int,
        "senders_count": int,
        "messages_per_sender": [{"from": str, "count": int}, ...],
        "first_message_ts": str or None,
        "last_message_ts": str or None
    }
    """
    with Session(engine) as session:
        # Total messages
        total = session.exec(select(func.count()).select_from(Message)).one()

        # Unique senders count
        senders_count = session.exec(select(func.count(func.distinct(Message.from_msisdn)))).one()

        # Messages per sender (top 10, sorted by count desc)
        sender_stats = session.exec(
            select(Message.from_msisdn, func.count(Message.message_id).label("count"))
            .group_by(Message.from_msisdn)
            .order_by(func.count(Message.message_id).desc())
            .limit(10)
        ).all()

        messages_per_sender = [{"from": sender, "count": count} for sender, count in sender_stats]

        # First and last message timestamps
        first_ts = session.exec(select(Message.ts).order_by(Message.ts.asc()).limit(1)).first()

        last_ts = session.exec(select(Message.ts).order_by(Message.ts.desc()).limit(1)).first()

        return {
            "total_messages": total,
            "senders_count": senders_count,
            "messages_per_sender": messages_per_sender,
            "first_message_ts": first_ts,
            "last_message_ts": last_ts,
        }


def check_db_health() -> bool:
    """
    Check if database is reachable by executing a simple query.
    Returns True if healthy, False otherwise.
    """
    try:
        with Session(engine) as session:
            # Simple query to check connectivity
            session.exec(select(func.count()).select_from(Message)).one()
        return True
    except Exception:
        return False
