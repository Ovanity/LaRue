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
            con.execute("CREATE INDEX IF NOT EXISTS idx_players_money ON players(money DESC);")

            # ── NEW: table pour cooldowns / quotas journaliers
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

    def _today_str(self) -> str:
        """
        Jour de jeu basé sur Europe/Paris avec coupure à 08:00.
        Avant 08:00, on considère que ça appartient encore à la veille.
        """
        tz = ZoneInfo("Europe/Paris")
        now = datetime.now(tz)
        reset_hour = 8
        anchor = now if now.hour >= reset_hour else (now - timedelta(days=1))
        return anchor.strftime("%Y-%m-%d")

    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int) -> tuple[
        bool, int, int]:
        """
        Vérifie cooldown + quota et consomme 1 utilisation si OK.
        Retourne (ok, wait_seconds, remaining_today).
          - ok=False & wait>0  -> cooldown restant
          - ok=False & remaining_today=0 -> quota du jour atteint
        """
        uid = str(user_id)
        now = int(time.time())
        today = self._today_str()
        with self._conn() as con:
            row = con.execute(
                "SELECT last_ts, day, count FROM actions WHERE user_id=? AND action=?",
                (uid, action)
            ).fetchone()

            if row is None:
                # première utilisation -> crée l’entrée et consomme 1
                con.execute(
                    "INSERT INTO actions(user_id, action, last_ts, day, count) VALUES(?,?,?,?,?)",
                    (uid, action, now, today, 1)
                )
                return True, 0, max(0, daily_cap - 1)

            last_ts, day, count = int(row[0]), str(row[1]), int(row[2])

            # nouveau jour -> reset du compteur
            if day != today:
                day = today
                count = 0

            # quota ?
            if count >= daily_cap:
                return False, 0, 0

            # cooldown ?
            wait = (last_ts + cooldown_s) - now
            if wait > 0:
                return False, wait, max(0, daily_cap - count)

            # OK -> consomme 1
            count += 1
            con.execute(
                "UPDATE actions SET last_ts=?, day=?, count=? WHERE user_id=? AND action=?",
                (now, day, count, uid, action)
            )
            return True, 0, max(0, daily_cap - count)

    def get_action_state(self, user_id: int, action: str) -> dict:
        """
        Petit helper de debug/affichage.
        Retourne: { 'day': str, 'count': int, 'last_ts': int } ou défauts.
        """
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT last_ts, day, count FROM actions WHERE user_id=? AND action=?",
                (uid, action)
            ).fetchone()
        if row is None:
            return {"day": self._today_str(), "count": 0, "last_ts": 0}
        return {"last_ts": int(row[0]), "day": str(row[1]), "count": int(row[2])}