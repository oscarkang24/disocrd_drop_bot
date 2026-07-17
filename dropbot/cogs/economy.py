"""Coin earning, balances, daily bonus, transfers, and leaderboards."""

from __future__ import annotations

import datetime as dt
import random
import time
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from .. import config
from ..items import CATALOG


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_chat_reward: dict[tuple[int, int], float] = {}

    @property
    def db(self):
        return self.bot.db

    # --- passive chat rewards ----------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        last = self._last_chat_reward.get(key, 0.0)
        if now - last < config.CHAT_REWARD_COOLDOWN:
            return
        self._last_chat_reward[key] = now
        amount = random.randint(config.CHAT_REWARD_MIN, config.CHAT_REWARD_MAX)
        await self.db.add_coins(message.guild.id, message.author.id, amount)

    # --- commands -----------------------------------------------------------

    @app_commands.command(name="balance", description="Check your NSZN coin (牛币) balance.")
    @app_commands.describe(user="Whose balance to check (defaults to you)")
    async def balance(self, interaction: discord.Interaction, user: discord.User | None = None):
        target = user or interaction.user
        bal = await self.db.get_balance(interaction.guild_id, target.id)
        embed = discord.Embed(
            title=f"{config.CURRENCY_EMOJI} {target.display_name}'s wallet",
            description=f"**{bal:,}** {config.CURRENCY_SYMBOL}",
            color=0xf1c40f,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily NSZN coin bonus.")
    async def daily(self, interaction: discord.Interaction):
        guild_id, user_id = interaction.guild_id, interaction.user.id
        today = dt.date.today()
        last_iso, streak = await self.db.get_daily_state(guild_id, user_id)
        last = dt.date.fromisoformat(last_iso) if last_iso else None

        if last == today:
            tomorrow = dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min)
            ts = int(tomorrow.timestamp())
            await interaction.response.send_message(
                f"You already claimed today's bonus. Come back <t:{ts}:R>!",
                ephemeral=True,
            )
            return

        streak = streak + 1 if last == today - dt.timedelta(days=1) else 1
        bonus = config.DAILY_STREAK_BONUS * (min(streak, config.DAILY_STREAK_CAP) - 1)
        amount = config.DAILY_BASE + bonus
        await self.db.set_daily_state(guild_id, user_id, today.isoformat(), streak)
        new_bal = await self.db.add_coins(guild_id, user_id, amount)

        embed = discord.Embed(
            title=f"{config.CURRENCY_EMOJI} Daily bonus claimed!",
            description=(
                f"You received **{amount:,}** {config.CURRENCY_SYMBOL}"
                + (f" (streak bonus +{bonus:,})" if bonus else "")
                + f"\n🔥 Streak: **{streak}** day{'s' if streak != 1 else ''}"
                + f"\n💰 Balance: **{new_bal:,}**"
            ),
            color=0xf1c40f,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pay", description="Send NSZN coins to another member.")
    @app_commands.describe(user="Who to pay", amount="How many coins to send")
    async def pay(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        if user.bot or user.id == interaction.user.id:
            await interaction.response.send_message("Pick someone else to pay.", ephemeral=True)
            return
        ok = await self.db.try_spend(interaction.guild_id, interaction.user.id, amount)
        if not ok:
            bal = await self.db.get_balance(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"Not enough coins — you have **{bal:,}** {config.CURRENCY_SYMBOL}.", ephemeral=True
            )
            return
        await self.db.add_coins(interaction.guild_id, user.id, amount)
        await interaction.response.send_message(
            f"{config.CURRENCY_EMOJI} {interaction.user.mention} sent **{amount:,}** "
            f"{config.CURRENCY_SYMBOL} to {user.mention}!"
        )

    @app_commands.command(name="leaderboard", description="Top members by coins or item power.")
    @app_commands.describe(board="Which leaderboard to show")
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        board: Literal["coins", "power"] = "coins",
    ):
        await interaction.response.defer()
        if board == "coins":
            rows = await self.db.top_balances(interaction.guild_id, 10)
            lines = [
                f"**{i}.** <@{row['user_id']}> — {row['balance']:,} {config.CURRENCY_SYMBOL}"
                for i, row in enumerate(rows, 1)
            ]
            title = f"{config.CURRENCY_EMOJI} Coin leaderboard"
        else:
            totals: dict[int, int] = {}
            for row in await self.db.all_inventories(interaction.guild_id):
                item = CATALOG.get(row["item_id"])
                if item:
                    totals[row["user_id"]] = totals.get(row["user_id"], 0) + item.power * row["count"]
            top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
            lines = [f"**{i}.** <@{uid}> — ⚡{power:,}" for i, (uid, power) in enumerate(top, 1)]
            title = "⚡ Power leaderboard"

        embed = discord.Embed(
            title=title,
            description="\n".join(lines) or "Nothing here yet — get chatting!",
            color=0xf1c40f,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
