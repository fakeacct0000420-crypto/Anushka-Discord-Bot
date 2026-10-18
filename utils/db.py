"""
utils/db.py
-----------
Single shared Motor (async MongoDB) client for the entire bot.
Every cog imports from here instead of creating its own connection.
Falls back to mongomock if MongoDB is offline or not yet configured.
"""
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("db")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "bot")

try:
    import pymongo
    probe = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=1200)
    probe.admin.command("ping")
    probe.close()
    _client = AsyncIOMotorClient(MONGO_URI)
    log.info("Connected to MongoDB at %s", MONGO_URI)
except Exception as e:
    log.warning("MongoDB not reachable (%s). Falling back to in-memory database.", e)
    from mongomock_motor import AsyncMongoMockClient
    _client = AsyncMongoMockClient()

# The database
db = _client[MONGO_DB]

# Collections – add new ones here as the bot grows
servers_col = db["servers"]   # Per-guild config (roles, prefix, settings)
warns_col   = db["warns"]     # Strike / warning records
antinuke_col = db["antinuke"] # Antinuke event logs
