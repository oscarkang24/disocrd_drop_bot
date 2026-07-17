"""Random channel drops: activity spawns claimable coin bundles or lootboxes."""

from __future__ import annotations

import random

import discord
from discord.ext import commands

from .. import config
from ..items import LOOTBOXES


class DropView(discord.ui.View):
    """A first-come-first-served claim button."""

    def __init__(self, cog: "Drops", *, coins: int = 0, box_id: str | None = None):
        super().__init__(timeout=config.DROP_EXPIRE_SECONDS)
        self.cog = cog
        self.coins = coins
        self.box_id = box_id
        self.claimed_by: int | None = None
        self.message: discord.Message | None = None

    @discord.ui.button(label="Claim!", style=discord.ButtonStyle.success, emoji="🐮")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed_by is not None:
            await interaction.response.send_message("Too slow — already claimed!", ephemeral=True)
            return
        self.claimed_by = interaction.user.id
        button.disabled = True
        self.stop()

        if self.box_id:
            box = LOOTBOXES[self.box_id]
            await self.cog.db.add_box(interaction.guild_id, interaction.user.id, self.box_id)
            text = f"{interaction.user.mention} claimed a **{box.emoji} {box.name}**! Open it with `/open`."
        else:
            await self.cog.db.add_coins(interaction.guild_id, interaction.user.id, self.coins)
            text = (
                f"{interaction.user.mention} claimed **{self.coins:,}** "
                f"{config.CURRENCY_SYMBOL} {config.CURRENCY_EMOJI}"
            )

        embed = interaction.message.embeds[0]
        embed.color = 0x2ecc71
        embed.description = text
        embed.set_footer(text="Claimed")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.claimed_by is None and self.message:
            embed = self.message.embeds[0]
            embed.color = 0x7f8c8d
            embed.set_footer(text="Expired — nobody claimed it in time.")
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class Drops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_activity: dict[int, int] = {}

    @property
    def db(self):
        return self.bot.db

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        count = self._channel_activity.get(message.channel.id, 0) + 1
        self._channel_activity[message.channel.id] = count
        if count < config.DROP_MIN_MESSAGES or random.random() > config.DROP_CHANCE:
            return
        self._channel_activity[message.channel.id] = 0
        await self.spawn_drop(message.channel)

    async def spawn_drop(self, channel: discord.abc.Messageable) -> None:
        if random.random() < config.DROP_BOX_CHANCE:
            box = LOOTBOXES["bronze"]
            view = DropView(self, box_id=box.id)
            embed = discord.Embed(
                title="🎁 A wild lootbox appeared!",
                description=f"A **{box.emoji} {box.name}** tumbled off an ox cart!\nFirst to claim it wins!",
                color=0xe67e22,
            )
        else:
            coins = random.randint(config.DROP_COIN_MIN, config.DROP_COIN_MAX)
            view = DropView(self, coins=coins)
            embed = discord.Embed(
                title=f"{config.CURRENCY_EMOJI} NSZN coin drop!",
                description=f"A pouch of **{coins:,}** {config.CURRENCY_SYMBOL} hit the ground!\nFirst to claim it wins!",
                color=0xf1c40f,
            )
        embed.set_footer(text=f"Disappears in {config.DROP_EXPIRE_SECONDS}s")
        view.message = await channel.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Drops(bot))
