"""Digital pets: adopt, hatch, raise with looted items, and auto-battle."""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from .. import config
from ..artgen import ensure_sprite
from ..battle import Combatant, condensed_log, simulate
from ..items import CATALOG
from ..pets import (
    EGGS,
    FEED_XP_PER_POWER,
    MAX_LEVEL,
    PET_CATALOG,
    STAGE_LEVELS,
    level_from_xp,
    stage_index,
    xp_for_level,
)

BATTLE_COOLDOWN = 180          # seconds between battles per user
BATTLE_WIN_COINS = 50
BATTLE_WIN_XP = 120
BATTLE_LOSS_XP = 40

EGG_CHOICES = [
    app_commands.Choice(name=f"{egg.name} — {egg.price:,} coins", value=egg.id)
    for egg in EGGS.values()
]


def pet_line(row, species) -> str:
    level = level_from_xp(row["xp"])
    active = " ⭐" if row["is_active"] else ""
    return (
        f"`#{row['id']}` {species.element_emoji} **{row['name']}** "
        f"({species.stage_name(level)}) — Lv.{level}{active}"
    )


class StarterView(discord.ui.View):
    def __init__(self, cog: "Pets", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        for species in PET_CATALOG.starters():
            self.add_item(self._button(species))

    def _button(self, species):
        button = discord.ui.Button(
            label=species.stages[0], emoji=species.element_emoji,
            style=discord.ButtonStyle.primary,
        )

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Run `/pet adopt` to pick your own!", ephemeral=True)
                return
            if await self.cog.db.get_pets(interaction.guild_id, self.user_id):
                await interaction.response.send_message("You already adopted a starter!", ephemeral=True)
                return
            pet_id = await self.cog.db.create_pet(
                interaction.guild_id, self.user_id, species.id, species.stages[0]
            )
            self.stop()
            embed, file = await self.cog.pet_embed(interaction.guild_id, self.user_id, pet_id)
            embed.title = f"🎉 Welcome, {species.stages[0]}!"
            embed.description = (
                f"*{species.description}*\n\n"
                f"Feed it looted items with `/pet feed` to level it up — it evolves at "
                f"levels {STAGE_LEVELS[0]} and {STAGE_LEVELS[1]}. Fight with `/pet battle`!"
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None, attachments=[file])

        button.callback = callback
        return button


class BattleChallengeView(discord.ui.View):
    def __init__(self, cog: "Pets", challenger: discord.Member, opponent: discord.Member, wager: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.wager = wager
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept(self, interaction: discord.Interaction, _):
        self.stop()
        await self.cog.run_battle(interaction, self.challenger, self.opponent, self.wager)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(
            content=f"{self.opponent.mention} declined the challenge. 🕊️", embed=None, view=None
        )

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="The challenge expired unanswered. 💤", embed=None, view=None)
            except discord.HTTPException:
                pass


@app_commands.guild_only()
class Pets(commands.GroupCog, group_name="pet"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._battle_cooldowns: dict[tuple[int, int], float] = {}

    @property
    def db(self):
        return self.bot.db

    # --- helpers ------------------------------------------------------------

    async def pet_embed(self, guild_id: int, user_id: int, pet_id: int) -> tuple[discord.Embed, discord.File]:
        row = await self.db.get_pet(guild_id, user_id, pet_id)
        species = PET_CATALOG.get(row["species_id"])
        level = level_from_xp(row["xp"])
        stage = stage_index(level)
        stats = species.stats_at(level)
        if level < MAX_LEVEL:
            need = xp_for_level(level + 1) - row["xp"]
            xp_text = f"{row['xp']:,} xp (next level in {need:,})"
        else:
            xp_text = f"{row['xp']:,} xp (MAX)"

        embed = discord.Embed(
            title=f"{species.element_emoji} {row['name']} — {species.stage_name(level)}",
            description=(
                f"{species.rarity_emoji} **{species.rarity_label}** · "
                f"{species.element_emoji} {species.element_label} · stage {stage + 1}/3\n"
                f"Lv.**{level}** · {xp_text}\n"
                f"❤️ {stats['hp']} · ⚔️ {stats['atk']} · 🛡️ {stats['def']} · 💨 {stats['spd']}\n"
                f"🏆 {row['wins']}W / {row['losses']}L"
            ),
            color=species.color,
        )
        sprite = ensure_sprite(species, stage)
        file = discord.File(sprite, filename="pet.png")
        embed.set_thumbnail(url="attachment://pet.png")
        return embed, file

    async def _active_pet_or_complain(self, interaction, member: discord.Member):
        row = await self.db.get_active_pet(interaction.guild_id, member.id)
        if row is None:
            msg = (
                "You need an active pet — get one with `/pet adopt` or `/pet hatch`."
                if member.id == interaction.user.id
                else f"{member.display_name} doesn't have an active pet yet."
            )
            await interaction.response.send_message(msg, ephemeral=True)
        return row

    # --- commands -----------------------------------------------------------

    @app_commands.command(name="adopt", description="Adopt your free starter pet (one per member).")
    async def adopt(self, interaction: discord.Interaction):
        if await self.db.get_pets(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "You already have a pet! Hatch more with `/pet hatch`.", ephemeral=True
            )
            return
        starters = PET_CATALOG.starters()
        lines = [
            f"{s.element_emoji} **{s.stages[0]}** ({s.element_label}) — *{s.description}*"
            for s in starters
        ]
        await interaction.response.send_message(
            "Choose your starter:\n" + "\n".join(lines),
            view=StarterView(self, interaction.user.id),
        )

    @app_commands.command(name="hatch", description="Buy and hatch an egg for a new pet.")
    @app_commands.choices(egg=EGG_CHOICES)
    async def hatch(self, interaction: discord.Interaction, egg: app_commands.Choice[str]):
        egg_def = EGGS[egg.value]
        if not await self.db.try_spend(interaction.guild_id, interaction.user.id, egg_def.price):
            bal = await self.db.get_balance(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"A {egg_def.name} costs **{egg_def.price:,}** {config.CURRENCY_SYMBOL}; "
                f"you have **{bal:,}**.",
                ephemeral=True,
            )
            return
        species = PET_CATALOG.hatch(egg_def)
        pet_id = await self.db.create_pet(
            interaction.guild_id, interaction.user.id, species.id, species.stages[0]
        )
        embed, file = await self.pet_embed(interaction.guild_id, interaction.user.id, pet_id)
        embed.title = f"{egg_def.emoji} The egg hatched — it's {species.stages[0]}!"
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="info", description="Show your active pet (or another member's).")
    @app_commands.describe(user="Whose pet to show (defaults to you)")
    async def info(self, interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        row = await self._active_pet_or_complain(interaction, target)
        if row is None:
            return
        embed, file = await self.pet_embed(interaction.guild_id, target.id, row["id"])
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="list", description="List all your pets.")
    async def list_pets(self, interaction: discord.Interaction):
        rows = await self.db.get_pets(interaction.guild_id, interaction.user.id)
        if not rows:
            await interaction.response.send_message(
                "No pets yet — `/pet adopt` your free starter!", ephemeral=True
            )
            return
        lines = [pet_line(row, PET_CATALOG.get(row["species_id"])) for row in rows]
        embed = discord.Embed(
            title=f"🐾 {interaction.user.display_name}'s pets",
            description="\n".join(lines) + "\n\n⭐ = active. Switch with `/pet activate`.",
            color=0x9b59b6,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="activate", description="Choose which pet battles for you.")
    @app_commands.describe(pet_id="The pet's number from /pet list")
    async def activate(self, interaction: discord.Interaction, pet_id: int):
        row = await self.db.get_pet(interaction.guild_id, interaction.user.id, pet_id)
        if row is None:
            await interaction.response.send_message("That's not one of your pets.", ephemeral=True)
            return
        await self.db.set_active_pet(interaction.guild_id, interaction.user.id, pet_id)
        await interaction.response.send_message(f"⭐ **{row['name']}** is now your active pet!")

    @app_commands.command(name="rename", description="Rename your active pet.")
    @app_commands.describe(name="The new name (max 32 characters)")
    async def rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 32]):
        row = await self._active_pet_or_complain(interaction, interaction.user)
        if row is None:
            return
        await self.db.rename_pet(row["id"], name)
        await interaction.response.send_message(f"Your pet is now called **{name}**!")

    @app_commands.command(name="feed", description="Feed looted items to your active pet for XP.")
    @app_commands.describe(item="Item from your inventory", quantity="How many to feed (default 1)")
    async def feed(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1, 100] = 1,
    ):
        pet_row = await self._active_pet_or_complain(interaction, interaction.user)
        if pet_row is None:
            return
        item_def = CATALOG.find_by_name(item)
        if item_def is None:
            await interaction.response.send_message(f"No item matching **{item}**.", ephemeral=True)
            return
        if not await self.db.try_consume_item(
            interaction.guild_id, interaction.user.id, item_def.id, quantity
        ):
            await interaction.response.send_message(
                f"You don't have {quantity}× {item_def.emoji} **{item_def.name}**.", ephemeral=True
            )
            return

        gained = item_def.power * FEED_XP_PER_POWER * quantity
        old_level = level_from_xp(pet_row["xp"])
        await self.db.add_pet_xp(pet_row["id"], gained)
        new_xp = pet_row["xp"] + gained
        new_level = level_from_xp(new_xp)
        species = PET_CATALOG.get(pet_row["species_id"])

        desc = (
            f"**{pet_row['name']}** munched {quantity}× {item_def.emoji} "
            f"**{item_def.name}** and gained **{gained:,} xp**!"
        )
        if new_level > old_level:
            desc += f"\n📈 Level up! **Lv.{old_level} → Lv.{new_level}**"
        if stage_index(new_level) > stage_index(old_level):
            evolved = species.stage_name(new_level)
            if pet_row["name"] in species.stages:  # keep custom names through evolution
                await self.db.rename_pet(pet_row["id"], evolved)
            desc += f"\n\n# ✨ EVOLUTION! ✨\n**{species.stage_name(old_level)}** evolved into **{evolved}**!"

        embed, file = await self.pet_embed(interaction.guild_id, interaction.user.id, pet_row["id"])
        embed.description = desc + "\n\n" + embed.description
        await interaction.response.send_message(embed=embed, file=file)

    @feed.autocomplete("item")
    async def feed_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await self.db.get_inventory(interaction.guild_id, interaction.user.id)
        current = current.lower()
        choices = []
        for row in rows:
            item = CATALOG.get(row["item_id"])
            if item and current in item.name.lower():
                choices.append(
                    app_commands.Choice(
                        name=f"{item.name} ×{row['count']} (⚡{item.power} → {item.power * FEED_XP_PER_POWER} xp)",
                        value=item.name,
                    )
                )
        return choices[:25]

    @app_commands.command(name="battle", description="Challenge another member to an auto-battle!")
    @app_commands.describe(opponent="Who to challenge", wager="Optional coin wager (winner takes all)")
    async def battle(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        wager: app_commands.Range[int, 0, 1_000_000] = 0,
    ):
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.response.send_message("Challenge a (human) someone else!", ephemeral=True)
            return
        now = time.monotonic()
        key = (interaction.guild_id, interaction.user.id)
        if now - self._battle_cooldowns.get(key, 0) < BATTLE_COOLDOWN:
            wait = int(BATTLE_COOLDOWN - (now - self._battle_cooldowns[key]))
            await interaction.response.send_message(
                f"Your pet is still catching its breath — try again in {wait}s.", ephemeral=True
            )
            return

        mine = await self._active_pet_or_complain(interaction, interaction.user)
        if mine is None:
            return
        theirs = await self.db.get_active_pet(interaction.guild_id, opponent.id)
        if theirs is None:
            await interaction.response.send_message(
                f"{opponent.display_name} has no active pet to battle.", ephemeral=True
            )
            return

        my_species = PET_CATALOG.get(mine["species_id"])
        their_species = PET_CATALOG.get(theirs["species_id"])
        embed = discord.Embed(
            title="⚔️ Battle challenge!",
            description=(
                f"{interaction.user.mention}'s {my_species.element_emoji} "
                f"**{mine['name']}** (Lv.{level_from_xp(mine['xp'])}) challenges "
                f"{opponent.mention}'s {their_species.element_emoji} "
                f"**{theirs['name']}** (Lv.{level_from_xp(theirs['xp'])})!"
                + (f"\n💰 Wager: **{wager:,}** {config.CURRENCY_SYMBOL} each — winner takes all!" if wager else "")
            ),
            color=0xe74c3c,
        )
        view = BattleChallengeView(self, interaction.user, opponent, wager)
        await interaction.response.send_message(content=opponent.mention, embed=embed, view=view)
        view.message = await interaction.original_response()

    async def run_battle(
        self,
        interaction: discord.Interaction,
        challenger: discord.Member,
        opponent: discord.Member,
        wager: int,
    ):
        guild_id = interaction.guild_id
        mine = await self.db.get_active_pet(guild_id, challenger.id)
        theirs = await self.db.get_active_pet(guild_id, opponent.id)
        if mine is None or theirs is None:
            await interaction.response.edit_message(
                content="One of the pets vanished before the fight. Battle cancelled.",
                embed=None, view=None,
            )
            return

        if wager:
            if not await self.db.try_spend(guild_id, challenger.id, wager):
                await interaction.response.edit_message(
                    content=f"{challenger.mention} can't cover the wager anymore. Battle cancelled.",
                    embed=None, view=None,
                )
                return
            if not await self.db.try_spend(guild_id, opponent.id, wager):
                await self.db.add_coins(guild_id, challenger.id, wager)  # refund
                await interaction.response.edit_message(
                    content=f"{opponent.mention} can't cover the wager. Battle cancelled.",
                    embed=None, view=None,
                )
                return

        self._battle_cooldowns[(guild_id, challenger.id)] = time.monotonic()
        self._battle_cooldowns[(guild_id, opponent.id)] = time.monotonic()

        pets = {
            challenger.id: Combatant(
                challenger.id, mine["name"], PET_CATALOG.get(mine["species_id"]),
                level_from_xp(mine["xp"]),
            ),
            opponent.id: Combatant(
                opponent.id, theirs["name"], PET_CATALOG.get(theirs["species_id"]),
                level_from_xp(theirs["xp"]),
            ),
        }
        result = simulate(pets[challenger.id], pets[opponent.id])
        rows = {challenger.id: mine, opponent.id: theirs}
        winner_row = rows[result.winner.owner_id]
        loser_row = rows[result.loser.owner_id]

        prize = BATTLE_WIN_COINS + wager * 2
        await self.db.record_battle(winner_row["id"], loser_row["id"])
        await self.db.add_pet_xp(winner_row["id"], BATTLE_WIN_XP)
        await self.db.add_pet_xp(loser_row["id"], BATTLE_LOSS_XP)
        await self.db.add_coins(guild_id, result.winner.owner_id, prize)

        stage = stage_index(result.winner.level)
        sprite = ensure_sprite(result.winner.species, stage)
        file = discord.File(sprite, filename="winner.png")
        embed = discord.Embed(
            title=f"⚔️ {result.winner.name} wins in {result.rounds} rounds!",
            description=(
                condensed_log(result)
                + f"\n\n🏆 <@{result.winner.owner_id}> wins **{prize:,}** {config.CURRENCY_SYMBOL} "
                f"and **{BATTLE_WIN_XP}** xp · <@{result.loser.owner_id}> gets **{BATTLE_LOSS_XP}** xp."
            ),
            color=result.winner.species.color,
        )
        embed.set_thumbnail(url="attachment://winner.png")
        await interaction.response.edit_message(content=None, embed=embed, view=None, attachments=[file])


async def setup(bot: commands.Bot):
    await bot.add_cog(Pets(bot))
