from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from .models import Message, engine


def save_message(data: dict) -> dict:
    try:
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
        return {"status": "ok", "duplicate": True}


def get_messages(filters: Optional[dict] = None, limit: int = 50, offset: int = 0) -> list:
   
    filters = filters or {}

    with Session(engine) as session:
        statement = select(Message)

        if "from" in filters:
            statement = statement.where(Message.from_msisdn == filters["from"])

        if "since" in filters:
            statement = statement.where(Message.ts >= filters["since"])

        if "q" in filters:

            statement = statement.where(Message.text.ilike(f"%{filters['q']}%"))

        if "message_id" in filters:
            statement = statement.where(Message.message_id == filters["message_id"])

        statement = statement.order_by(Message.ts.asc())

        statement = statement.offset(offset).limit(limit)

        results = session.exec(statement).all()

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
    
    filters = filters or {}

    with Session(engine) as session:
        statement = select(func.count()).select_from(Message)

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
    
    with Session(engine) as session:
        total = session.exec(select(func.count()).select_from(Message)).one()

        senders_count = session.exec(select(func.count(func.distinct(Message.from_msisdn)))).one()

        sender_stats = session.exec(
            select(Message.from_msisdn, func.count(Message.message_id).label("count"))
            .group_by(Message.from_msisdn)
            .order_by(func.count(Message.message_id).desc())
            .limit(10)
        ).all()

        messages_per_sender = [{"from": sender, "count": count} for sender, count in sender_stats]

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

    try:
        with Session(engine) as session:

            session.exec(select(func.count()).select_from(Message)).one()
        return True
    except Exception:
        return False
