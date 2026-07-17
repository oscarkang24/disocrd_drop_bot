"""Inventory viewing and item lookups."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..items import CATALOG, RARITY_META, RARITY_ORDER


class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    @app_commands.command(name="inventory", description="View your (or someone's) item collection.")
    @app_commands.describe(user="Whose inventory to view (defaults to you)")
    async def inventory(self, interaction: discord.Interaction, user: discord.User | None = None):
        target = user or interaction.user
        rows = await self.db.get_inventory(interaction.guild_id, target.id)
        owned = {row["item_id"]: row["count"] for row in rows}
        if not owned:
            await interaction.response.send_message(
                f"{target.display_name} has no items yet. Open a lootbox with `/open`!",
                ephemeral=True,
            )
            return

        total_power = 0
        embed = discord.Embed(color=0x9b59b6)
        for rarity in reversed(RARITY_ORDER):
            lines = []
            for item in CATALOG.by_rarity[rarity]:
                count = owned.get(item.id, 0)
                if count:
                    suffix = f" × {count}" if count > 1 else ""
                    lines.append(f"{item.emoji} **{item.name}**{suffix} · ⚡{item.power:,}")
                    total_power += item.power * count
            if lines:
                meta = RARITY_META[rarity]
                embed.add_field(
                    name=f"{meta['emoji']} {meta['label']}",
                    value="\n".join(lines),
                    inline=False,
                )
        unique = len(owned)
        embed.title = f"🎒 {target.display_name}'s collection"
        embed.description = (
            f"⚡ Total power: **{total_power:,}** · "
            f"Unique items: **{unique}/{len(CATALOG.items)}**"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="iteminfo", description="Look up an item's rarity and power.")
    @app_commands.describe(name="Item name to look up")
    async def iteminfo(self, interaction: discord.Interaction, name: str):
        item = CATALOG.find_by_name(name)
        if item is None:
            await interaction.response.send_message(f"No item matching **{name}**.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"{item.emoji} {item.name}",
            description=(
                f"{item.rarity_emoji} **{item.rarity_label}** · ⚡ Power **{item.power:,}**\n"
                f"*{item.description}*"
            ),
            color=item.color,
        )
        await interaction.response.send_message(embed=embed)

    @iteminfo.autocomplete("name")
    async def iteminfo_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        matches = [
            item for item in CATALOG.items.values() if current in item.name.lower()
        ][:25]
        return [app_commands.Choice(name=item.name, value=item.name) for item in matches]


async def setup(bot: commands.Bot):
    await bot.add_cog(Inventory(bot))
