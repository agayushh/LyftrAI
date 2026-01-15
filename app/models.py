from sqlmodel import Field, SQLModel, create_engine
from datetime import datetime
from .config import databaseUrl
class MessageTable(SQLModel, table=True):
    message_id: int | None = Field(default=None, primary_key=True)
    sender: str
    receiver: str
    ts: datetime
    text: str 
    createdAt: datetime
    
engine = create_engine(databaseUrl)