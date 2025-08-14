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
                    user_id     TEXT PRIMARY KEY,
                    has_started INTEGER NOT NULL DEFAULT 0 CHECK (has_started IN (0,1)),
                    money       INTEGER NOT NULL DEFAULT 0
                );
            """)
            # Utile pour le classement
            con.execute("CREATE INDEX IF NOT EXISTS idx_players_money ON players(money DESC);")

    # ── API
    def get_player(self, user_id: int) -> Player:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
            if row is None:
                # initialise le joueur
                con.execute(
                    "INSERT INTO players(user_id, has_started, money) VALUES(?,?,?)",
                    (uid, 0, 0)
                )
                return {"has_started": False, "money": 0}
            has_started, money = row
            return {"has_started": bool(int(has_started)), "money": int(money)}

    def update_player(self, user_id: int, **fields) -> Player:
        # lecture & merge en mémoire
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

    # Helpers pratiques (facultatifs mais utiles)
    def add_money(self, user_id: int, amount: int) -> Player:
        uid = str(user_id)
        amt = int(amount)
        with self._conn() as con:
            # s'assure que le joueur existe
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

    # Bonus : utile pour /debug (ne casse rien si non utilisé)
    def count_players(self) -> int:
        with self._conn() as con:
            (n,) = con.execute("SELECT COUNT(*) FROM players").fetchone()
        return int(n)