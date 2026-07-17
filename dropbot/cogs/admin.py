"""Admin tools: event rewards, manual coin grants, and forced drops.

All commands here require the Manage Server permission.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import config


@app_commands.default_permissions(manage_guild=True)
class Admin(commands.GroupCog, group_name="event"):
    """Reward members for participating in server events."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    @app_commands.command(
        name="reward-reaction",
        description="Reward everyone who reacted to a message (e.g. an event sign-up post).",
    )
    @app_commands.describe(
        message_link="Link to the message (right-click → Copy Message Link)",
        amount="Coins to award each participant",
        emoji="Only count this reaction emoji (default: any)",
    )
    async def reward_reaction(
        self,
        interaction: discord.Interaction,
        message_link: str,
        amount: app_commands.Range[int, 1, 1_000_000],
        emoji: str | None = None,
    ):
        await interaction.response.defer()
        try:
            parts = message_link.rstrip("/").split("/")
            channel_id, message_id = int(parts[-2]), int(parts[-1])
            channel = interaction.guild.get_channel(channel_id) or await interaction.guild.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
        except (ValueError, IndexError, discord.HTTPException):
            await interaction.followup.send("Couldn't find that message — paste a full message link.")
            return

        participants: set[int] = set()
        for reaction in message.reactions:
            if emoji and str(reaction.emoji) != emoji:
                continue
            async for user in reaction.users():
                if not user.bot:
                    participants.add(user.id)

        if not participants:
            await interaction.followup.send("No (non-bot) reactions found on that message.")
            return

        for user_id in participants:
            await self.db.add_coins(interaction.guild_id, user_id, amount)

        await interaction.followup.send(
            f"🎉 Event payout complete! **{len(participants)}** participants each received "
            f"**{amount:,}** {config.CURRENCY_SYMBOL} {config.CURRENCY_EMOJI}"
        )

    @app_commands.command(
        name="reward-voice",
        description="Reward everyone currently in a voice channel (e.g. movie night, game night).",
    )
    @app_commands.describe(channel="The voice channel", amount="Coins to award each member")
    async def reward_voice(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        amount: app_commands.Range[int, 1, 1_000_000],
    ):
        members = [m for m in channel.members if not m.bot]
        if not members:
            await interaction.response.send_message("Nobody (human) is in that channel.", ephemeral=True)
            return
        for member in members:
            await self.db.add_coins(interaction.guild_id, member.id, amount)
        names = ", ".join(m.mention for m in members[:15])
        extra = f" and {len(members) - 15} more" if len(members) > 15 else ""
        await interaction.response.send_message(
            f"🎉 Rewarded **{amount:,}** {config.CURRENCY_SYMBOL} each to {names}{extra}!"
        )


@app_commands.default_permissions(manage_guild=True)
class Coins(commands.GroupCog, group_name="coins"):
    """Manually grant or remove coins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    @app_commands.command(name="give", description="Give NSZN coins to a member.")
    @app_commands.describe(user="Recipient", amount="Coins to give", reason="Why (shown publicly)")
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, 10_000_000],
        reason: str | None = None,
    ):
        new_bal = await self.db.add_coins(interaction.guild_id, user.id, amount)
        suffix = f" — *{reason}*" if reason else ""
        await interaction.response.send_message(
            f"{config.CURRENCY_EMOJI} Gave **{amount:,}** {config.CURRENCY_SYMBOL} to "
            f"{user.mention}{suffix}. New balance: **{new_bal:,}**."
        )

    @app_commands.command(name="take", description="Remove NSZN coins from a member.")
    @app_commands.describe(user="Target", amount="Coins to remove")
    async def take(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, 10_000_000],
    ):
        new_bal = await self.db.add_coins(interaction.guild_id, user.id, -amount)
        await interaction.response.send_message(
            f"Removed **{amount:,}** {config.CURRENCY_SYMBOL} from {user.mention}. "
            f"New balance: **{new_bal:,}**.",
            ephemeral=True,
        )


@app_commands.default_permissions(manage_guild=True)
class DropAdmin(commands.GroupCog, group_name="drop"):
    """Manually trigger drops."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="spawn", description="Force-spawn a drop in this channel right now.")
    async def spawn(self, interaction: discord.Interaction):
        drops = self.bot.get_cog("Drops")
        if drops is None:
            await interaction.response.send_message("Drops cog is not loaded.", ephemeral=True)
            return
        await interaction.response.send_message("Spawning a drop... 👀", ephemeral=True)
        await drops.spawn_drop(interaction.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
    await bot.add_cog(Coins(bot))
    await bot.add_cog(DropAdmin(bot))
