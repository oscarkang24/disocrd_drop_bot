"""Pet species catalog, leveling/evolution rules, and egg definitions."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from .items import RARITY_META

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "pets.json"

MAX_LEVEL = 50
STAGE_LEVELS = (15, 35)          # evolve when reaching these levels
STAGE_MULT = (1.0, 1.3, 1.7)     # stat multiplier per evolution stage
FEED_XP_PER_POWER = 4            # xp gained per point of item power fed

ELEMENT_META = {
    "earth":  {"label": "Earth",  "emoji": "🌿"},
    "flame":  {"label": "Flame",  "emoji": "🔥"},
    "aqua":   {"label": "Aqua",   "emoji": "💧"},
    "storm":  {"label": "Storm",  "emoji": "⚡"},
    "spirit": {"label": "Spirit", "emoji": "👻"},
}

# flame > earth > storm > aqua > flame; spirit hits everything else a bit harder.
ELEMENT_BEATS = {"flame": "earth", "earth": "storm", "storm": "aqua", "aqua": "flame"}


def element_multiplier(attacker: str, defender: str) -> float:
    if attacker == "spirit" and defender != "spirit":
        return 1.15
    if ELEMENT_BEATS.get(attacker) == defender:
        return 1.3
    if ELEMENT_BEATS.get(defender) == attacker:
        return 0.77
    return 1.0


def xp_for_level(level: int) -> int:
    """Total xp required to reach `level` (level 1 = 0 xp)."""
    return sum(int(80 * (l ** 1.5)) for l in range(1, level))


def level_from_xp(xp: int) -> int:
    level = 1
    while level < MAX_LEVEL and xp >= xp_for_level(level + 1):
        level += 1
    return level


def stage_index(level: int) -> int:
    return sum(1 for threshold in STAGE_LEVELS if level >= threshold)


@dataclass(frozen=True)
class Species:
    id: str
    stages: tuple[str, ...]
    element: str
    rarity: str
    emoji: str
    base: dict[str, int]
    description: str

    @property
    def rarity_emoji(self) -> str:
        return RARITY_META[self.rarity]["emoji"]

    @property
    def rarity_label(self) -> str:
        return RARITY_META[self.rarity]["label"]

    @property
    def color(self) -> int:
        return RARITY_META[self.rarity]["color"]

    @property
    def element_emoji(self) -> str:
        return ELEMENT_META[self.element]["emoji"]

    @property
    def element_label(self) -> str:
        return ELEMENT_META[self.element]["label"]

    def stage_name(self, level: int) -> str:
        return self.stages[stage_index(level)]

    def stats_at(self, level: int) -> dict[str, int]:
        mult = (1 + 0.06 * (level - 1)) * STAGE_MULT[stage_index(level)]
        return {stat: max(1, int(value * mult)) for stat, value in self.base.items()}


@dataclass(frozen=True)
class Egg:
    id: str
    name: str
    emoji: str
    price: int
    description: str
    odds: dict[str, float]  # species rarity -> weight

    def odds_text(self) -> str:
        total = sum(self.odds.values())
        return " · ".join(
            f"{RARITY_META[r]['emoji']} {RARITY_META[r]['label']} {w / total:.0%}"
            for r, w in self.odds.items()
        )


EGGS: dict[str, Egg] = {
    egg.id: egg
    for egg in [
        Egg("basic_egg", "Speckled Egg", "🥚", 500,
            "Warm to the touch. Something small and hungry inside.",
            {"common": 70, "uncommon": 30}),
        Egg("rare_egg", "Storm-Marked Egg", "🐣", 2500,
            "The shell hums faintly. Handle with oven mitts.",
            {"uncommon": 25, "rare": 55, "epic": 20}),
        Egg("mythic_egg", "Celestial Egg", "🌠", 10000,
            "It glows with starlight and judges your net worth.",
            {"epic": 40, "legendary": 45, "mythic": 15}),
    ]
}


class PetCatalog:
    def __init__(self, path: Path = DATA_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.species: dict[str, Species] = {}
        self.by_rarity: dict[str, list[Species]] = {}
        for entry in raw["species"]:
            entry["stages"] = tuple(entry["stages"])
            sp = Species(**entry)
            self.species[sp.id] = sp
            self.by_rarity.setdefault(sp.rarity, []).append(sp)

    def get(self, species_id: str) -> Species | None:
        return self.species.get(species_id)

    def starters(self) -> list[Species]:
        return self.by_rarity.get("common", [])

    def hatch(self, egg: Egg) -> Species:
        rarities = [r for r, w in egg.odds.items() if w > 0 and self.by_rarity.get(r)]
        weights = [egg.odds[r] for r in rarities]
        rarity = random.choices(rarities, weights=weights, k=1)[0]
        return random.choice(self.by_rarity[rarity])


PET_CATALOG = PetCatalog()
