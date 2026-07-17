"""Automatic turn-based battle simulator for pets."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .pets import Species, element_multiplier

MAX_ROUNDS = 30
CRIT_CHANCE = 0.08
CRIT_MULT = 1.6


@dataclass
class Combatant:
    owner_id: int
    name: str
    species: Species
    level: int
    stats: dict[str, int] = field(init=False)
    hp: int = field(init=False)

    def __post_init__(self):
        self.stats = self.species.stats_at(self.level)
        self.hp = self.stats["hp"]

    @property
    def max_hp(self) -> int:
        return self.stats["hp"]

    def hp_bar(self, width: int = 10) -> str:
        filled = max(0, round(width * self.hp / self.max_hp))
        return "█" * filled + "░" * (width - filled)


@dataclass
class BattleResult:
    winner: Combatant
    loser: Combatant
    rounds: int
    log: list[str]
    draw_decided_on_hp: bool


def _attack(attacker: Combatant, defender: Combatant, log: list[str]) -> None:
    elem = element_multiplier(attacker.species.element, defender.species.element)
    raw = attacker.stats["atk"] * random.uniform(0.85, 1.15) * elem
    damage = max(1, int(raw - defender.stats["def"] * 0.5))
    crit = random.random() < CRIT_CHANCE
    if crit:
        damage = int(damage * CRIT_MULT)
    defender.hp = max(0, defender.hp - damage)

    tags = []
    if crit:
        tags.append("💥 CRIT")
    if elem > 1.2:
        tags.append("super effective")
    elif elem < 0.9:
        tags.append("not very effective")
    tag_text = f" ({', '.join(tags)})" if tags else ""
    log.append(
        f"{attacker.species.element_emoji} **{attacker.name}** hits "
        f"**{defender.name}** for `{damage}`{tag_text} — "
        f"{defender.hp_bar()} {defender.hp}/{defender.max_hp}"
    )


def simulate(a: Combatant, b: Combatant) -> BattleResult:
    log: list[str] = []
    rounds = 0
    for rounds in range(1, MAX_ROUNDS + 1):
        first, second = (a, b) if a.stats["spd"] >= b.stats["spd"] else (b, a)
        if a.stats["spd"] == b.stats["spd"]:
            first, second = random.sample([a, b], 2)
        _attack(first, second, log)
        if second.hp <= 0:
            log.append(f"☠️ **{second.name}** is down!")
            return BattleResult(first, second, rounds, log, False)
        _attack(second, first, log)
        if first.hp <= 0:
            log.append(f"☠️ **{first.name}** is down!")
            return BattleResult(second, first, rounds, log, False)

    # Time out: whoever kept more of their health wins.
    a_pct, b_pct = a.hp / a.max_hp, b.hp / b.max_hp
    winner, loser = (a, b) if a_pct >= b_pct else (b, a)
    log.append(f"⏱️ The referee calls it — **{winner.name}** wins on remaining health!")
    return BattleResult(winner, loser, rounds, log, True)


def condensed_log(result: BattleResult, head: int = 4, tail: int = 6, limit: int = 3500) -> str:
    """Trim a long battle log so it fits in one Discord embed."""
    log = result.log
    if len(log) > head + tail + 1:
        skipped = len(log) - head - tail
        log = log[:head] + [f"*... {skipped} exchanges later ...*"] + log[-tail:]
    text = "\n".join(log)
    if len(text) > limit:
        text = text[-limit:]
        text = text[text.index("\n") + 1:]
    return text
