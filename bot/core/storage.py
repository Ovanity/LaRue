from __future__ import annotations
from pathlib import Path
from typing import TypedDict
import sqlite3
from contextlib import contextmanager
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ───────── Types de données
class Player(TypedDict, total=False):
    has_started: bool
    money: int  # en centimes

# ───────── Interface
class Storage:
    # joueurs
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...
    def add_money(self, user_id: int, amount: int) -> Player: ...
    def top_richest(self, limit: int = 10) -> list[tuple[str, int]]: ...
    def count_players(self) -> int: ...

    # inventaire
    def get_inventory(self, user_id: int) -> dict[str, int]: ...
    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None: ...
    def get_money(self, user_id: int) -> int: ...
    def try_spend(self, user_id: int, amount: int) -> bool: ...

    # cooldowns / quotas
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int) -> tuple[bool, int, int]: ...
    def get_action_state(self, user_id: int, action: str) -> dict: ...

    # stats (NOUVEAU)
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int: ...
    def get_stat(self, user_id: int, key: str, default: int = 0) -> int: ...
    def get_stats(self, user_id: int) -> dict[str, int]: ...

    # admin
    def reset_players(self) -> None: ...
    def reset_actions(self) -> None: ...
    def reset_inventory(self) -> None: ...
    def reset_stats(self) -> None: ...

# ───────── Implémentation SQLite
class SQLiteStorage(Storage):
    def __init__(self, root: str):
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        self.db_path = root_path / "larue.db"
        self._init_db()

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
            yield con
            con.commit()
        finally:
            con.close()

    def _init_db(self):
        with self._conn() as con:
            # Joueurs
            con.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id     TEXT PRIMARY KEY,
                    has_started INTEGER NOT NULL DEFAULT 0 CHECK (has_started IN (0,1)),
                    money       INTEGER NOT NULL DEFAULT 0
                );
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_players_money ON players(money DESC);")

            # Cooldowns / quotas
            con.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    user_id  TEXT NOT NULL,
                    action   TEXT NOT NULL,
                    last_ts  INTEGER NOT NULL DEFAULT 0,
                    day      TEXT NOT NULL DEFAULT '',
                    count    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, action)
                );
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_actions_day ON actions(day);")

            # Inventaire
            con.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    qty     INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, item_id)
                );
            """)

            # Stats (NOUVEAU) — pour compter les usages, paliers, etc.
            con.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    user_id TEXT NOT NULL,
                    key     TEXT NOT NULL,
                    value   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, key)
                );
            """)

    # ── API joueurs
    def get_player(self, user_id: int) -> Player:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO players(user_id, has_started, money) VALUES(?,?,?)",
                    (uid, 0, 0)
                )
                return {"has_started": False, "money": 0}
            has_started, money = row
            return {"has_started": bool(int(has_started)), "money": int(money)}

    def update_player(self, user_id: int, **fields) -> Player:
        p = self.get_player(user_id)
        if "has_started" in fields:
            fields["has_started"] = int(bool(fields["has_started"]))
        if "money" in fields:
            fields["money"] = int(fields["money"])
        p.update(fields)

        uid = str(user_id)
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO players(user_id, has_started, money)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    has_started = excluded.has_started,
                    money       = excluded.money
                """,
                (uid, int(p.get("has_started", 0)), int(p.get("money", 0)))
            )
        return p

    def add_money(self, user_id: int, amount: int) -> Player:
        uid = str(user_id)
        amt = int(amount)
        with self._conn() as con:
            con.execute(
                "INSERT INTO players(user_id, has_started, money) VALUES(?, 0, 0) ON CONFLICT(user_id) DO NOTHING",
                (uid,)
            )
            con.execute("UPDATE players SET money = money + ? WHERE user_id = ?", (amt, uid))
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
        return {"has_started": bool(int(row[0])), "money": int(row[1])}

    def top_richest(self, limit: int = 10) -> list[tuple[str, int]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT user_id, money
                FROM players
                WHERE has_started = 1
                ORDER BY money DESC, user_id ASC
                LIMIT ?
                """,
                (int(limit),)
            ).fetchall()
        return [(user_id, int(money)) for (user_id, money) in rows]

    def count_players(self) -> int:
        with self._conn() as con:
            (n,) = con.execute("SELECT COUNT(*) FROM players").fetchone()
        return int(n)

    # ── Jour logique Europe/Paris, reset 08:00
    def _today_str(self) -> str:
        tz = ZoneInfo("Europe/Paris")
        now = datetime.now(tz)
        reset_hour = 8
        anchor = now if now.hour >= reset_hour else (now - timedelta(days=1))
        return anchor.strftime("%Y-%m-%d")

    # ── Cooldowns / quotas
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int) -> tuple[bool, int, int]:
        uid = str(user_id)
        now = int(time.time())
        today = self._today_str()
        with self._conn() as con:
            row = con.execute(
                "SELECT last_ts, day, count FROM actions WHERE user_id=? AND action=?",
                (uid, action)
            ).fetchone()

            if row is None:
                con.execute(
                    "INSERT INTO actions(user_id, action, last_ts, day, count) VALUES(?,?,?,?,?)",
                    (uid, action, now, today, 1)
                )
                return True, 0, max(0, daily_cap - 1)

            last_ts, day, count = int(row[0]), str(row[1]), int(row[2])

            if day != today:
                day = today
                count = 0

            if count >= daily_cap:
                return False, 0, 0

            wait = (last_ts + cooldown_s) - now
            if wait > 0:
                return False, wait, max(0, daily_cap - count)

            count += 1
            con.execute(
                "UPDATE actions SET last_ts=?, day=?, count=? WHERE user_id=? AND action=?",
                (now, day, count, uid, action)
            )
            return True, 0, max(0, daily_cap - count)

    def get_action_state(self, user_id: int, action: str) -> dict:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT last_ts, day, count FROM actions WHERE user_id=? AND action=?",
                (uid, action)
            ).fetchone()
        if row is None:
            return {"day": self._today_str(), "count": 0, "last_ts": 0}
        return {"last_ts": int(row[0]), "day": str(row[1]), "count": int(row[2])}

    # ── Inventaire (shop)
    def get_inventory(self, user_id: int) -> dict[str, int]:
        uid = str(user_id)
        with self._conn() as con:
            rows = con.execute("SELECT item_id, qty FROM inventory WHERE user_id=?", (uid,)).fetchall()
        return {item_id: int(qty) for (item_id, qty) in rows}

    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None:
        if qty <= 0:
            return
        uid = str(user_id)
        with self._conn() as con:
            con.execute("""
                INSERT INTO inventory(user_id, item_id, qty)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET qty = qty + excluded.qty
            """, (uid, item_id, int(qty)))

    def get_money(self, user_id: int) -> int:
        return int(self.get_player(user_id)["money"])

    def try_spend(self, user_id: int, amount: int) -> bool:
        """Débit atomique si solde suffisant. Retourne True/False."""
        uid = str(user_id)
        amt = int(amount)
        if amt <= 0:
            return True
        with self._conn() as con:
            row = con.execute("SELECT money FROM players WHERE user_id=?", (uid,)).fetchone()
            if not row:
                return False
            cur = int(row[0])
            if cur < amt:
                return False
            con.execute("UPDATE players SET money = money - ? WHERE user_id=?", (amt, uid))
        return True

    # ── Stats (paliers / progression)
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int:
        """Incrémente et retourne la nouvelle valeur."""
        uid = str(user_id)
        d = int(delta)
        with self._conn() as con:
            con.execute("""
                INSERT INTO stats(user_id, key, value) VALUES(?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value = value + excluded.value
            """, (uid, key, d))
            (val,) = con.execute("SELECT value FROM stats WHERE user_id=? AND key=?", (uid, key)).fetchone()
        return int(val)

    def get_stat(self, user_id: int, key: str, default: int = 0) -> int:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute("SELECT value FROM stats WHERE user_id=? AND key=?", (uid, key)).fetchone()
        return int(row[0]) if row else int(default)

    def get_stats(self, user_id: int) -> dict[str, int]:
        uid = str(user_id)
        with self._conn() as con:
            rows = con.execute("SELECT key, value FROM stats WHERE user_id=?", (uid,)).fetchall()
        return {k: int(v) for (k, v) in rows}

    # ── Admin helpers
    def reset_players(self) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM players;")

    def reset_actions(self) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM actions;")

    def reset_inventory(self) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM inventory;")

    def reset_stats(self) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM stats;")