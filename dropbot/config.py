"""Central configuration for the NSZN drop bot."""

import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID") or 0) or None
DATABASE_PATH = os.getenv("DATABASE_PATH", "dropbot.db")

# --- Currency ---------------------------------------------------------------
CURRENCY_NAME = "NSZN coins"
CURRENCY_SYMBOL = "牛币"
CURRENCY_EMOJI = "🐮"

# --- Passive chat rewards ---------------------------------------------------
CHAT_REWARD_MIN = 3
CHAT_REWARD_MAX = 8
CHAT_REWARD_COOLDOWN = 60  # seconds per user

# --- Daily bonus ------------------------------------------------------------
DAILY_BASE = 200
DAILY_STREAK_BONUS = 25    # extra coins per consecutive day
DAILY_STREAK_CAP = 20      # streak bonus stops growing after this many days

# --- Random channel drops ---------------------------------------------------
DROP_MIN_MESSAGES = 20     # channel must see this many messages before a drop can spawn
DROP_CHANCE = 0.08         # per-message chance once the threshold is reached
DROP_COIN_MIN = 50
DROP_COIN_MAX = 150
DROP_BOX_CHANCE = 0.15     # chance a drop contains a lootbox instead of coins
DROP_EXPIRE_SECONDS = 60
