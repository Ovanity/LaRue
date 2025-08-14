from __future__ import annotations
from pathlib import Path
from typing import TypedDict
import sqlite3
from contextlib import contextmanager

# ───────── Types de données
class Player(TypedDict, total=False):
    has_started: bool
    money: int

# ───────── Interface
class Storage:
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...
    # (optionnel) helpers courants
    def add_money(self, user_id: int, amount: int) -> Player: ...
    def top_richest(self, limit: int = 10) -> list[tuple[str, int]]: ...

# ───────── Implémentation SQLite
class SQLiteStorage(Storage):
    def __init__(self, root: str):
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        self.db_path = root_path / "larue.db"
        self._init_db()

    @contextmanager
    def _conn(self):
        # Connexion courte par opération : simple et sûr
        con = sqlite3.connect(self.db_path)
        try:
            # Modes recommandés pour app Discord
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
            yield con
            con.commit()
        finally:
            con.close()

    def _init_db(self):
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id TEXT PRIMARY KEY,
                    has_started INTEGER NOT NULL DEFAULT 0,
                    money INTEGER NOT NULL DEFAULT 0
                );
            """)

    # ── API
    def get_player(self, user_id: int) -> Player:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
            if row is None:
                # initialise
                con.execute(
                    "INSERT INTO players(user_id, has_started, money) VALUES(?,?,?)",
                    (uid, 0, 0)
                )
                return {"has_started": False, "money": 0}
            has_started, money = row
            return {"has_started": bool(has_started), "money": int(money)}

    def update_player(self, user_id: int, **fields) -> Player:
        # lecture actuelle
        p = self.get_player(user_id)
        p.update(fields)
        uid = str(user_id)
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO players(user_id, has_started, money)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    has_started = excluded.has_started,
                    money = excluded.money
                """,
                (uid, int(p.get("has_started", False)), int(p.get("money", 0)))
            )
        return p

    # Helpers pratiques (facultatifs mais utiles)
    def add_money(self, user_id: int, amount: int) -> Player:
        uid = str(user_id)
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO players(user_id, has_started, money)
                VALUES(?, 0, 0)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (uid,)
            )
            con.execute(
                "UPDATE players SET money = money + ? WHERE user_id = ?",
                (int(amount), uid)
            )
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
        return {"has_started": bool(row[0]), "money": int(row[1])}

    def top_richest(self, limit: int = 10) -> list[tuple[str, int]]:
        with self._conn() as con:
            return [
                (user_id, money)
                for (user_id, money) in con.execute(
                    "SELECT user_id, money FROM players ORDER BY money DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            ]