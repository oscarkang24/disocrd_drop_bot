# 🐮 NSZN Drop Bot

A Discord bot that rewards channel participation with **NSZN coins (牛币)** and lets
members spend them on **tiered lootboxes** full of rarity-graded items with power stats.

## Features

### 💰 Earning NSZN coins
- **Chatting** — 3–8 coins per message (60s per-user cooldown, anti-spam).
- **Daily bonus** — `/daily` for 200 coins + a growing streak bonus.
- **Random drops** — active channels randomly spawn coin pouches (or lootboxes!)
  with a first-come-first-served **Claim** button.
- **Event rewards** — admins pay out everyone who reacted to an event post
  (`/event reward-reaction`) or everyone in a voice channel (`/event reward-voice`).

### 🎁 Lootboxes
| Box | Price | Highlights |
|---|---|---|
| 📦 Bronze Ox Crate | 250 | Mostly common/uncommon, tiny legendary chance |
| 🧰 Golden Bull Chest | 1,000 | Solid rare/epic odds, 0.5% mythic |
| 🎇 Celestial Niu Vault | 5,000 | No commons; 12% legendary, 3% mythic |

### 🐾 Digital pets & auto-battles
- **Adopt** a free starter (`/pet adopt`) or **hatch** rarer species from eggs
  (`/pet hatch` — Speckled 500, Storm-Marked 2,500, Celestial 10,000 coins).
- 13 species across five elements (🌿 Earth, 🔥 Flame, 💧 Aqua, ⚡ Storm, 👻 Spirit)
  and all six rarities, each with a **3-stage evolution chain** (evolves at Lv.15 / Lv.35).
- **Feed looted items** to your pet (`/pet feed`) — every point of item ⚡power = 4 XP,
  so that Mythic pull is 4,000 XP of pet food.
- **Auto-battles** (`/pet battle @user [wager]`) — challenge flow with an Accept button,
  then a fully simulated turn-based fight: speed order, crits, elemental
  advantages (Flame > Earth > Storm > Aqua > Flame), HP bars, and a round-by-round log.
  Winner takes coins + XP (and the wager pot, if any).

### 🎨 Generated pet art
Every species/stage gets deterministic procedural **pixel-art sprites**
(`dropbot/artgen.py`) — mirrored-symmetry sprites with element-based palettes that
grow bigger and spikier at each evolution. Sprites render on demand and are embedded
in pet cards and battle results. Regenerate all art + a contact sheet with
`python -m dropbot.artgen`.

### ⚔️ Items & rarities
37 themed items across six tiers — ⚪ Common, 🟢 Uncommon, 🔵 Rare, 🟣 Epic,
🟠 Legendary, 🔴 Mythic — each with a **⚡ power** stat (2 up to 1,000 for the
NSZN Singularity). Collect items to climb the power leaderboard.

## Commands

| Command | What it does |
|---|---|
| `/balance` `/daily` `/pay` | Wallet basics |
| `/leaderboard coins\|power` | Top members by wealth or collection power |
| `/shop` `/buy` `/boxes` `/open` | Lootbox economy |
| `/inventory` `/iteminfo` | Collection browsing |
| `/pet adopt` `/pet hatch` `/pet info` `/pet list` | Get and inspect pets |
| `/pet feed` `/pet rename` `/pet activate` | Raise and manage pets |
| `/pet battle @user [wager]` | Auto-battle another member's pet |
| `/event reward-reaction` `/event reward-voice` | Admin: event payouts |
| `/coins give` `/coins take` | Admin: manual adjustments |
| `/drop spawn` | Admin: force a drop in the current channel |

Admin commands require the **Manage Server** permission.

## Setup

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications),
   add a **Bot**, and copy its token.
2. Under **Privileged Gateway Intents**, enable **Message Content Intent** and
   **Server Members Intent**.
3. Invite the bot with the `bot` + `applications.commands` scopes and permissions to
   send messages/embeds and read message history.
4. Install and run:

```bash
pip install -r requirements.txt
cp .env.example .env      # then paste your token into .env
python bot.py
```

Set `DEV_GUILD_ID` in `.env` to your server's ID while developing — slash commands
sync instantly to that guild instead of taking up to an hour globally.

## Customizing

- **Earning rates, drop frequency, daily bonus** — tweak `dropbot/config.py`.
- **Items** — edit `data/items.json` (id, name, emoji, rarity, power, description).
- **Boxes & odds** — edit `LOOTBOXES` in `dropbot/items.py`.
- **Pet species & stats** — edit `data/pets.json`; leveling/evolution rules in `dropbot/pets.py`.
- **Battle balance** — tweak `dropbot/battle.py` (crit rate, round cap, damage formula).
- **Art style** — palettes and sprite parameters in `dropbot/artgen.py`.

Data is stored in a local SQLite file (`dropbot.db` by default); balances and
inventories are kept **per guild**.
