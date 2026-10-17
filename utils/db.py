"""
utils/db.py
-----------
Single shared Motor (async MongoDB) client for the entire bot.
Every cog imports from here instead of creating its own connection.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "bot")

_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)

# The database
db = _client[MONGO_DB]

# Collections – add new ones here as the bot grows
servers_col = db["servers"]   # Per-guild config (roles, prefix, settings)
warns_col   = db["warns"]     # Strike / warning records
antinuke_col = db["antinuke"] # Antinuke event logs
