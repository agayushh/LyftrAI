import os

from dotenv import load_dotenv

load_dotenv()

webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
database_url = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
log_level = os.environ.get("LOG_LEVEL", "INFO")
