"""Item catalog, rarity tiers, and lootbox definitions."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "items.json"

# Rarity tiers, ordered weakest -> strongest.
RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]

RARITY_META = {
    "common":    {"label": "Common",    "emoji": "⚪", "color": 0x95a5a6},
    "uncommon":  {"label": "Uncommon",  "emoji": "🟢", "color": 0x2ecc71},
    "rare":      {"label": "Rare",      "emoji": "🔵", "color": 0x3498db},
    "epic":      {"label": "Epic",      "emoji": "🟣", "color": 0x9b59b6},
    "legendary": {"label": "Legendary", "emoji": "🟠", "color": 0xe67e22},
    "mythic":    {"label": "Mythic",    "emoji": "🔴", "color": 0xe74c3c},
}


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    emoji: str
    rarity: str
    power: int
    description: str

    @property
    def rarity_label(self) -> str:
        return RARITY_META[self.rarity]["label"]

    @property
    def rarity_emoji(self) -> str:
        return RARITY_META[self.rarity]["emoji"]

    @property
    def color(self) -> int:
        return RARITY_META[self.rarity]["color"]

    def display(self) -> str:
        return f"{self.rarity_emoji} {self.emoji} **{self.name}** · ⚡{self.power}"


@dataclass(frozen=True)
class LootBox:
    id: str
    name: str
    emoji: str
    price: int
    description: str
    # rarity -> weight (weights need not sum to 1; zero means impossible)
    odds: dict[str, float]

    def roll_rarity(self) -> str:
        rarities = [r for r in RARITY_ORDER if self.odds.get(r, 0) > 0]
        weights = [self.odds[r] for r in rarities]
        return random.choices(rarities, weights=weights, k=1)[0]

    def odds_text(self) -> str:
        total = sum(w for w in self.odds.values() if w > 0)
        parts = []
        for rarity in RARITY_ORDER:
            weight = self.odds.get(rarity, 0)
            if weight > 0:
                meta = RARITY_META[rarity]
                parts.append(f"{meta['emoji']} {meta['label']} {weight / total:.1%}")
        return " · ".join(parts)


LOOTBOXES: dict[str, LootBox] = {
    box.id: box
    for box in [
        LootBox(
            id="bronze",
            name="Bronze Ox Crate",
            emoji="📦",
            price=250,
            description="A creaky wooden crate. Smells like hay and hope.",
            odds={"common": 62, "uncommon": 25, "rare": 10, "epic": 2.7, "legendary": 0.3},
        ),
        LootBox(
            id="golden",
            name="Golden Bull Chest",
            emoji="🧰",
            price=1000,
            description="Gilded and heavy. Something glimmers inside.",
            odds={"common": 30, "uncommon": 32, "rare": 24, "epic": 10, "legendary": 3.5, "mythic": 0.5},
        ),
        LootBox(
            id="celestial",
            name="Celestial Niu Vault",
            emoji="🎇",
            price=5000,
            description="Sealed by the Ox constellation itself. No common junk inside.",
            odds={"uncommon": 20, "rare": 38, "epic": 27, "legendary": 12, "mythic": 3},
        ),
    ]
}


class Catalog:
    """Loaded item catalog with lookup and roll helpers."""

    def __init__(self, path: Path = DATA_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.items: dict[str, Item] = {}
        self.by_rarity: dict[str, list[Item]] = {r: [] for r in RARITY_ORDER}
        for entry in raw["items"]:
            item = Item(**entry)
            if item.rarity not in RARITY_META:
                raise ValueError(f"Unknown rarity {item.rarity!r} on item {item.id!r}")
            self.items[item.id] = item
            self.by_rarity[item.rarity].append(item)

    def get(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def find_by_name(self, query: str) -> Item | None:
        query = query.strip().lower()
        for item in self.items.values():
            if item.name.lower() == query or item.id == query:
                return item
        for item in self.items.values():
            if query in item.name.lower():
                return item
        return None

    def roll_from_box(self, box: LootBox) -> Item:
        rarity = box.roll_rarity()
        return random.choice(self.by_rarity[rarity])


CATALOG = Catalog()
