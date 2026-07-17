"""Async SQLite persistence for balances, inventories, and lootboxes."""

from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    balance      INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    last_daily   TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    item_id  TEXT    NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, item_id)
);

CREATE TABLE IF NOT EXISTS boxes (
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    box_id   TEXT    NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, box_id)
);

CREATE TABLE IF NOT EXISTS pets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    species_id TEXT    NOT NULL,
    name       TEXT    NOT NULL,
    xp         INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 0,
    wins       INTEGER NOT NULL DEFAULT 0,
    losses     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets (guild_id, user_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() has not been called"
        return self._conn

    # --- coins --------------------------------------------------------------

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT balance FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return row["balance"] if row else 0

    async def add_coins(self, guild_id: int, user_id: int, amount: int) -> int:
        """Add (or with a negative amount, remove) coins. Returns new balance."""
        earned = max(amount, 0)
        await self.conn.execute(
            """
            INSERT INTO users (guild_id, user_id, balance, total_earned)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                balance = MAX(0, balance + excluded.balance),
                total_earned = total_earned + excluded.total_earned
            """,
            (guild_id, user_id, amount, earned),
        )
        await self.conn.commit()
        return await self.get_balance(guild_id, user_id)

    async def try_spend(self, guild_id: int, user_id: int, amount: int) -> bool:
        """Atomically deduct coins; returns False if the balance is too low."""
        cur = await self.conn.execute(
            """
            UPDATE users SET balance = balance - ?
            WHERE guild_id = ? AND user_id = ? AND balance >= ?
            """,
            (amount, guild_id, user_id, amount),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_daily_state(self, guild_id: int, user_id: int) -> tuple[str | None, int]:
        async with self.conn.execute(
            "SELECT last_daily, daily_streak FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None, 0
        return row["last_daily"], row["daily_streak"]

    async def set_daily_state(self, guild_id: int, user_id: int, date_iso: str, streak: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (guild_id, user_id, last_daily, daily_streak)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                last_daily = excluded.last_daily,
                daily_streak = excluded.daily_streak
            """,
            (guild_id, user_id, date_iso, streak),
        )
        await self.conn.commit()

    async def top_balances(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT user_id, balance, total_earned FROM users
            WHERE guild_id = ? ORDER BY balance DESC LIMIT ?
            """,
            (guild_id, limit),
        ) as cur:
            return list(await cur.fetchall())

    # --- inventory ----------------------------------------------------------

    async def add_item(self, guild_id: int, user_id: int, item_id: str, count: int = 1) -> None:
        await self.conn.execute(
            """
            INSERT INTO inventory (guild_id, user_id, item_id, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET
                count = count + excluded.count
            """,
            (guild_id, user_id, item_id, count),
        )
        await self.conn.commit()

    async def get_inventory(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT item_id, count FROM inventory
            WHERE guild_id = ? AND user_id = ? AND count > 0
            """,
            (guild_id, user_id),
        ) as cur:
            return list(await cur.fetchall())

    async def all_inventories(self, guild_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT user_id, item_id, count FROM inventory WHERE guild_id = ? AND count > 0",
            (guild_id,),
        ) as cur:
            return list(await cur.fetchall())

    async def try_consume_item(self, guild_id: int, user_id: int, item_id: str, count: int = 1) -> bool:
        """Atomically remove `count` of an item; returns False if not enough owned."""
        cur = await self.conn.execute(
            """
            UPDATE inventory SET count = count - ?
            WHERE guild_id = ? AND user_id = ? AND item_id = ? AND count >= ?
            """,
            (count, guild_id, user_id, item_id, count),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # --- pets ---------------------------------------------------------------

    async def create_pet(
        self, guild_id: int, user_id: int, species_id: str, name: str
    ) -> int:
        """Insert a pet; it becomes active if the owner has no active pet."""
        async with self.conn.execute(
            "SELECT 1 FROM pets WHERE guild_id = ? AND user_id = ? AND is_active = 1",
            (guild_id, user_id),
        ) as cur:
            has_active = await cur.fetchone() is not None
        cur = await self.conn.execute(
            "INSERT INTO pets (guild_id, user_id, species_id, name, is_active) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, species_id, name, 0 if has_active else 1),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_pets(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM pets WHERE guild_id = ? AND user_id = ? ORDER BY xp DESC",
            (guild_id, user_id),
        ) as cur:
            return list(await cur.fetchall())

    async def get_active_pet(self, guild_id: int, user_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM pets WHERE guild_id = ? AND user_id = ? AND is_active = 1",
            (guild_id, user_id),
        ) as cur:
            return await cur.fetchone()

    async def get_pet(self, guild_id: int, user_id: int, pet_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM pets WHERE id = ? AND guild_id = ? AND user_id = ?",
            (pet_id, guild_id, user_id),
        ) as cur:
            return await cur.fetchone()

    async def set_active_pet(self, guild_id: int, user_id: int, pet_id: int) -> None:
        await self.conn.execute(
            "UPDATE pets SET is_active = 0 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.execute("UPDATE pets SET is_active = 1 WHERE id = ?", (pet_id,))
        await self.conn.commit()

    async def add_pet_xp(self, pet_id: int, xp: int) -> None:
        await self.conn.execute("UPDATE pets SET xp = xp + ? WHERE id = ?", (xp, pet_id))
        await self.conn.commit()

    async def rename_pet(self, pet_id: int, name: str) -> None:
        await self.conn.execute("UPDATE pets SET name = ? WHERE id = ?", (name, pet_id))
        await self.conn.commit()

    async def record_battle(self, winner_pet_id: int, loser_pet_id: int) -> None:
        await self.conn.execute("UPDATE pets SET wins = wins + 1 WHERE id = ?", (winner_pet_id,))
        await self.conn.execute("UPDATE pets SET losses = losses + 1 WHERE id = ?", (loser_pet_id,))
        await self.conn.commit()

    # --- lootboxes ----------------------------------------------------------

    async def add_box(self, guild_id: int, user_id: int, box_id: str, count: int = 1) -> None:
        await self.conn.execute(
            """
            INSERT INTO boxes (guild_id, user_id, box_id, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, user_id, box_id) DO UPDATE SET
                count = count + excluded.count
            """,
            (guild_id, user_id, box_id, count),
        )
        await self.conn.commit()

    async def try_consume_box(self, guild_id: int, user_id: int, box_id: str) -> bool:
        """Atomically consume one box; returns False if the user has none."""
        cur = await self.conn.execute(
            """
            UPDATE boxes SET count = count - 1
            WHERE guild_id = ? AND user_id = ? AND box_id = ? AND count > 0
            """,
            (guild_id, user_id, box_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_boxes(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT box_id, count FROM boxes WHERE guild_id = ? AND user_id = ? AND count > 0",
            (guild_id, user_id),
        ) as cur:
            return list(await cur.fetchall())
