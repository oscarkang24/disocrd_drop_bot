"""Lootbox shop: buy boxes with NSZN coins and open them for tiered items."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import config
from ..items import CATALOG, LOOTBOXES, LootBox

BOX_CHOICES = [
    app_commands.Choice(name=f"{box.name} — {box.price:,} coins", value=box.id)
    for box in LOOTBOXES.values()
]


class OpenAgainView(discord.ui.View):
    """Lets the opener keep cracking boxes of the same type."""

    def __init__(self, cog: "Lootbox", user_id: int, box: LootBox):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.box = box

    @discord.ui.button(label="Open another", style=discord.ButtonStyle.primary, emoji="🎁")
    async def open_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("These aren't your boxes!", ephemeral=True)
            return
        embed, has_more = await self.cog.open_one(interaction.guild_id, interaction.user, self.box)
        if embed is None:
            await interaction.response.send_message(
                f"You're out of {self.box.name}s! Grab more in `/shop`.", ephemeral=True
            )
            return
        view = OpenAgainView(self.cog, self.user_id, self.box) if has_more else None
        await interaction.response.send_message(embed=embed, view=view)


class Lootbox(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def open_one(
        self, guild_id: int, user: discord.abc.User, box: LootBox
    ) -> tuple[discord.Embed | None, bool]:
        """Consume and open one box. Returns (embed, user_has_more) or (None, False)."""
        if not await self.db.try_consume_box(guild_id, user.id, box.id):
            return None, False
        item = CATALOG.roll_from_box(box)
        await self.db.add_item(guild_id, user.id, item.id)

        embed = discord.Embed(
            title=f"{box.emoji} {box.name} opened!",
            description=(
                f"{user.mention} pulled...\n\n"
                f"# {item.rarity_emoji} {item.emoji} {item.name}\n"
                f"**{item.rarity_label}** · ⚡ Power **{item.power:,}**\n"
                f"*{item.description}*"
            ),
            color=item.color,
        )
        remaining = {row["box_id"]: row["count"] for row in await self.db.get_boxes(guild_id, user.id)}
        left = remaining.get(box.id, 0)
        embed.set_footer(text=f"{left} × {box.name} remaining")
        return embed, left > 0

    @app_commands.command(name="shop", description="Browse the lootbox shop.")
    async def shop(self, interaction: discord.Interaction):
        bal = await self.db.get_balance(interaction.guild_id, interaction.user.id)
        embed = discord.Embed(
            title="🏪 NSZN Lootbox Shop",
            description=f"Your balance: **{bal:,}** {config.CURRENCY_SYMBOL} {config.CURRENCY_EMOJI}\nBuy with `/buy`, open with `/open`.",
            color=0xf1c40f,
        )
        for box in LOOTBOXES.values():
            embed.add_field(
                name=f"{box.emoji} {box.name} — {box.price:,} {config.CURRENCY_SYMBOL}",
                value=f"*{box.description}*\n{box.odds_text()}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Buy lootboxes with NSZN coins.")
    @app_commands.describe(box="Which lootbox to buy", quantity="How many (default 1)")
    @app_commands.choices(box=BOX_CHOICES)
    async def buy(
        self,
        interaction: discord.Interaction,
        box: app_commands.Choice[str],
        quantity: app_commands.Range[int, 1, 25] = 1,
    ):
        lootbox = LOOTBOXES[box.value]
        cost = lootbox.price * quantity
        ok = await self.db.try_spend(interaction.guild_id, interaction.user.id, cost)
        if not ok:
            bal = await self.db.get_balance(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"That costs **{cost:,}** {config.CURRENCY_SYMBOL} but you only have **{bal:,}**.",
                ephemeral=True,
            )
            return
        await self.db.add_box(interaction.guild_id, interaction.user.id, lootbox.id, quantity)
        bal = await self.db.get_balance(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            f"🛒 Bought **{quantity}× {lootbox.emoji} {lootbox.name}** for **{cost:,}** "
            f"{config.CURRENCY_SYMBOL}. Balance: **{bal:,}**. Crack them with `/open`!"
        )

    @app_commands.command(name="boxes", description="See the lootboxes you own.")
    async def boxes(self, interaction: discord.Interaction):
        rows = await self.db.get_boxes(interaction.guild_id, interaction.user.id)
        if not rows:
            await interaction.response.send_message(
                "You don't own any lootboxes yet. Visit `/shop` or catch a channel drop!",
                ephemeral=True,
            )
            return
        lines = []
        for row in rows:
            box = LOOTBOXES.get(row["box_id"])
            if box:
                lines.append(f"{box.emoji} **{box.name}** × {row['count']}")
        embed = discord.Embed(
            title=f"🎁 {interaction.user.display_name}'s lootboxes",
            description="\n".join(lines),
            color=0xe67e22,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="open", description="Open one of your lootboxes.")
    @app_commands.describe(box="Which lootbox to open")
    @app_commands.choices(box=BOX_CHOICES)
    async def open(self, interaction: discord.Interaction, box: app_commands.Choice[str]):
        lootbox = LOOTBOXES[box.value]
        embed, has_more = await self.open_one(interaction.guild_id, interaction.user, lootbox)
        if embed is None:
            await interaction.response.send_message(
                f"You don't have a {lootbox.emoji} {lootbox.name}. Buy one in `/shop`!",
                ephemeral=True,
            )
            return
        view = OpenAgainView(self, interaction.user.id, lootbox) if has_more else None
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lootbox(bot))
