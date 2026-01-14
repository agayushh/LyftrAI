import os 

webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
databaseUrl = os.environ.get("DATABASE_URL", "")
logLevel = os.environ.get("LOG_LEVEL", "INFO")