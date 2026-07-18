"""NSZN Drop Bot — entry point.

Rewards channel participation with NSZN coins (牛币) and lets members
buy and open tiered lootboxes.
"""

import asyncio
import logging

import discord
from discord.ext import commands

from dropbot import config
from dropbot.db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dropbot")

COGS = [
    "dropbot.cogs.economy",
    "dropbot.cogs.drops",
    "dropbot.cogs.lootbox",
    "dropbot.cogs.inventory",
    "dropbot.cogs.pets",
    "dropbot.cogs.admin",
]


class DropBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # needed for chat rewards & drop triggers
        intents.members = True          # needed for event reward lookups
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(config.DATABASE_PATH)

    async def setup_hook(self):
        await self.db.connect()
        for cog in COGS:
            await self.load_extension(cog)
            log.info("Loaded %s", cog)

        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to dev guild %s", len(synced), config.DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Member of %d guild(s): %s", len(self.guilds), ", ".join(g.name for g in self.guilds))
        # Without a DEV_GUILD_ID, global command sync can take up to an hour to
        # propagate — also push commands directly to each joined guild so they
        # show up immediately.
        if not config.DEV_GUILD_ID and not getattr(self, "_guild_synced", False):
            self._guild_synced = True
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    log.info("Synced %d commands to guild %s", len(synced), guild.name)
                except discord.HTTPException as exc:
                    log.warning("Failed to sync to %s: %s", guild.name, exc)

    async def close(self):
        await self.db.close()
        await super().close()


def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and add your token.")
    asyncio.run(DropBot().start(config.DISCORD_TOKEN))


if __name__ == "__main__":
    main()
