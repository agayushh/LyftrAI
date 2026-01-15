from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel, create_engine

from .config import database_url


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    message_id: str = Field(primary_key=True)
    from_msisdn: str = Field(index=True)
    to_msisdn: str = Field(index=True)
    ts: str  # ISO-8601 timestamp from webhook
    text: Optional[str] = None
    created_at: str  # Server timestamp ISO-8601

    @field_validator("from_msisdn", "to_msisdn")
    @classmethod
    def validate_e164_format(cls, v: str) -> str:
        """Validate that phone numbers are in E.164-like format: +[digits only]"""
        if not v:
            raise ValueError("Phone number cannot be empty")
        if not v.startswith("+"):
            raise ValueError("Phone number must start with '+'")
        if not v[1:].isdigit():
            raise ValueError("Phone number must contain only digits after '+'")
        return v


engine = create_engine(database_url, echo=False)
