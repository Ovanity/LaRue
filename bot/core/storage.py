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

    # stats
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int: ...
    def get_stat(self, user_id: int, key: str, default: int = 0) -> int: ...
    def get_stats(self, user_id: int) -> dict[str, int]: ...

    # admin
    def reset_players(self) -> None: ...
    def reset_actions(self) -> None: ...
    def reset_inventory(self) -> None: ...
    def reset_stats(self) -> None: ...

    # recyclerie
    def get_recycler_state(self, user_id: int) -> dict: ...
    def update_recycler_state(self, user_id: int, **fields) -> dict: ...
    def add_recycler_canettes(self, user_id: int, qty: int) -> int: ...
    def add_recycler_sacs(self, user_id: int, qty: int) -> int: ...
    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None: ...


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
            con.execute("PRAGMA busy_timeout=5000;")
            yield con
            con.commit()
        finally:
            con.close()

    # ── Migrations versionnées (idempotentes)
    def _apply_migrations(self, con: sqlite3.Connection) -> None:
        (ver,) = con.execute("PRAGMA user_version").fetchone()
        ver = int(ver or 0)

        # v1 — schéma de base
        if ver < 1:
            con.executescript("""
            -- Joueurs
            CREATE TABLE IF NOT EXISTS players (
                user_id     TEXT PRIMARY KEY,
                has_started INTEGER NOT NULL DEFAULT 0 CHECK (has_started IN (0,1)),
                money       INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_players_money ON players(money DESC);

            -- Cooldowns / quotas
            CREATE TABLE IF NOT EXISTS actions (
                user_id  TEXT NOT NULL,
                action   TEXT NOT NULL,
                last_ts  INTEGER NOT NULL DEFAULT 0,
                day      TEXT NOT NULL DEFAULT '',
                count    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, action)
            );
            CREATE INDEX IF NOT EXISTS idx_actions_day ON actions(day);

            -- Inventaire
            CREATE TABLE IF NOT EXISTS inventory (
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                qty     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_id)
            );

            -- Stats
            CREATE TABLE IF NOT EXISTS stats (
                user_id TEXT NOT NULL,
                key     TEXT NOT NULL,
                value   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, key)
            );

            -- Profils
            CREATE TABLE IF NOT EXISTS profiles (
                user_id    TEXT PRIMARY KEY,
                bio        TEXT NOT NULL DEFAULT '',
                color_hex  TEXT NOT NULL DEFAULT 'FFD166',
                title      TEXT NOT NULL DEFAULT '',
                cred       INTEGER NOT NULL DEFAULT 0,
                created_ts INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            -- Respect 1/jour/par paire
            CREATE TABLE IF NOT EXISTS respect_log (
                user_id TEXT NOT NULL,  -- reçoit
                from_id TEXT NOT NULL,  -- donne
                day     TEXT NOT NULL,  -- YYYY-MM-DD
                delta   INTEGER NOT NULL,
                ts      INTEGER NOT NULL,
                PRIMARY KEY (user_id, from_id, day)
            );
            """)
            con.execute("PRAGMA user_version=1")
            ver = 1

        # v2 — recyclerie
        if ver < 2:
            con.executescript("""
            -- État par joueur
            CREATE TABLE IF NOT EXISTS recycler_state (
                user_id    TEXT PRIMARY KEY,
                level      INTEGER NOT NULL DEFAULT 1,
                canettes   INTEGER NOT NULL DEFAULT 0,
                sacs       INTEGER NOT NULL DEFAULT 0,
                streak     INTEGER NOT NULL DEFAULT 0,
                last_day   INTEGER NOT NULL DEFAULT 0, -- AAAAMMJJ (jour logique 08:00)
                updated_ts INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            -- Journal des encaissements
            CREATE TABLE IF NOT EXISTS recycler_claims (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                day_key   INTEGER NOT NULL,  -- AAAAMMJJ encaissé
                sacs_used INTEGER NOT NULL,
                gross     INTEGER NOT NULL,
                tax       INTEGER NOT NULL,
                net       INTEGER NOT NULL,
                ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(user_id, day_key)
            );
            CREATE INDEX IF NOT EXISTS idx_recycler_claims_user ON recycler_claims(user_id);
            """)
            con.execute("PRAGMA user_version=2")
            ver = 2

        # v3 — exemple d’index utile
        if ver < 3:
            con.executescript("""
            CREATE INDEX IF NOT EXISTS idx_actions_user_day ON actions(user_id, day);
            """)
            con.execute("PRAGMA user_version=3")
            ver = 3


        # v4 — journal des transactions (audit)
        if ver < 4:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS ledger (
                user_id TEXT NOT NULL,
                key     TEXT NOT NULL,                -- idempotency key (facultatif au début)
                delta   INTEGER NOT NULL,             -- +crédits / -débits (centimes)
                reason  TEXT NOT NULL DEFAULT '',
                ts      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (user_id, key)
            );
            CREATE INDEX IF NOT EXISTS idx_ledger_user_ts ON ledger(user_id, ts);
            """)
            con.execute("PRAGMA user_version=4")
            ver = 4


    def _init_db(self):
        with self._conn() as con:
            self._apply_migrations(con)

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

        # --- audit: chaque crédit/débit est journalisé
        # key aléatoire pour le moment; ajouterons une vraie idempotence plus tard
        rand = int(time.time() * 1_000_000) % 1_000_000_000
        audit_key = f"auto:{rand}"
        with self._conn() as con:
            # s’assure que le joueur existe
            con.execute(
                "INSERT INTO players(user_id, has_started, money) VALUES(?, 0, 0) "
                "ON CONFLICT(user_id) DO NOTHING",
                (uid,)
            )
            # journalise l’opération (si collision improbable sur la clé, on réessaie)
            try:
                con.execute(
                    "INSERT OR IGNORE INTO ledger(user_id, key, delta, reason) VALUES(?,?,?,?)",
                    (uid, audit_key, amt, "add_money")
                )
                if con.total_changes == 0:
                    # évite une collision rare de clé auto: re-tente avec une autre clé
                    audit_key = f"auto:{rand}:{time.time_ns()}"
                    con.execute(
                        "INSERT OR IGNORE INTO ledger(user_id, key, delta, reason) VALUES(?,?,?,?)",
                        (uid, audit_key, amt, "add_money")
                    )
            except sqlite3.OperationalError:
                # si 'ledger' n'existe pas encore (ancienne DB), on ignore l’audit
                pass

            # applique la modification de solde
            con.execute("UPDATE players SET money = money + ? WHERE user_id = ?", (amt, uid))
            row = con.execute(
                "SELECT has_started, money FROM players WHERE user_id = ?",
                (uid,)
            ).fetchone()
        return {"has_started": bool(int(row[0])), "money": int(row[1])}

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

    # ── Stats
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

    # ── Profils
    def get_profile(self, user_id: int) -> dict:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute(
                "SELECT bio, color_hex, title, cred, created_ts FROM profiles WHERE user_id=?",
                (uid,)
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO profiles(user_id, bio, color_hex, title, cred) VALUES(?,?,?,?,?)",
                    (uid, '', 'FFD166', '', 0)
                )
                return {"bio": "", "color_hex": "FFD166", "title": "", "cred": 0, "created_ts": int(time.time())}
            bio, color_hex, title, cred, created_ts = row
            return {"bio": bio, "color_hex": color_hex, "title": title, "cred": int(cred),
                    "created_ts": int(created_ts)}

    def upsert_profile(self, user_id: int, **fields) -> dict:
        p = self.get_profile(user_id)
        p.update(fields)
        uid = str(user_id)
        with self._conn() as con:
            con.execute("""
                INSERT INTO profiles(user_id, bio, color_hex, title, cred)
                VALUES(?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    bio=excluded.bio, color_hex=excluded.color_hex,
                    title=excluded.title, cred=excluded.cred
            """, (uid, p.get("bio", ""), p.get("color_hex", "FFD166"), p.get("title", ""), int(p.get("cred", 0))))
        return p

    # ── Respect (1/jour/par paire)
    def can_give_respect(self, from_id: int, to_id: int) -> tuple[bool, str | None]:
        if from_id == to_id:
            return False, "😅 Tu peux pas te respecter toi-même."
        day = self._today_str()
        with self._conn() as con:
            row = con.execute(
                "SELECT 1 FROM respect_log WHERE user_id=? AND from_id=? AND day=?",
                (str(to_id), str(from_id), day)
            ).fetchone()
        if row:
            return False, "⏳ Tu as déjà donné du respect à cette personne aujourd’hui."
        return True, None

    def give_respect(self, from_id: int, to_id: int) -> int:
        ok, why = self.can_give_respect(from_id, to_id)
        if not ok:
            raise ValueError(why or "not allowed")
        uid_to = str(to_id)
        with self._conn() as con:
            # s’assure que le profil existe
            con.execute(
                "INSERT INTO profiles(user_id, bio, color_hex, title, cred) VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_id) DO NOTHING",
                (uid_to, '', 'FFD166', '', 0)
            )
            # log 1/jour
            con.execute(
                "INSERT OR IGNORE INTO respect_log(user_id, from_id, day, delta, ts) VALUES(?,?,?,?,strftime('%s','now'))",
                (uid_to, str(from_id), self._today_str(), 1)
            )
            # si le log a été inséré, incrémente
            con.execute("UPDATE profiles SET cred = cred + 1 WHERE user_id=?", (uid_to,))
            (cred,) = con.execute("SELECT cred FROM profiles WHERE user_id=?", (uid_to,)).fetchone()
        return int(cred)

    def top_profiles_by_cred(self, limit: int = 10) -> list[tuple[str, int]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT user_id, cred FROM profiles ORDER BY cred DESC, user_id ASC LIMIT ?",
                (int(limit),)
            ).fetchall()
        return [(uid, int(cred)) for (uid, cred) in rows]

    # ── Recyclerie
    def get_recycler_state(self, user_id: int) -> dict:
        uid = str(user_id)
        with self._conn() as con:
            row = con.execute("""
                SELECT level, canettes, sacs, streak, last_day
                FROM recycler_state WHERE user_id=?
            """, (uid,)).fetchone()
            if row is None:
                con.execute("INSERT INTO recycler_state(user_id) VALUES(?)", (uid,))
                return {"level": 1, "canettes": 0, "sacs": 0, "streak": 0, "last_day": 0}
            level, canettes, sacs, streak, last_day = row
            return {
                "level": int(level), "canettes": int(canettes), "sacs": int(sacs),
                "streak": int(streak), "last_day": int(last_day)
            }

    def update_recycler_state(self, user_id: int, **fields) -> dict:
        st = self.get_recycler_state(user_id)
        allowed = {"level", "canettes", "sacs", "streak", "last_day"}
        for k, v in list(fields.items()):
            if k in allowed:
                st[k] = int(v)
        uid = str(user_id)
        with self._conn() as con:
            con.execute("""
                INSERT INTO recycler_state(user_id, level, canettes, sacs, streak, last_day, updated_ts)
                VALUES(?,?,?,?,?,?, strftime('%s','now'))
                ON CONFLICT(user_id) DO UPDATE SET
                  level=excluded.level,
                  canettes=excluded.canettes,
                  sacs=excluded.sacs,
                  streak=excluded.streak,
                  last_day=excluded.last_day,
                  updated_ts=excluded.updated_ts
            """, (uid, st["level"], st["canettes"], st["sacs"], st["streak"], st["last_day"]))
        return st

    def add_recycler_canettes(self, user_id: int, qty: int) -> int:
        if int(qty) == 0:
            return self.get_recycler_state(user_id)["canettes"]
        st = self.get_recycler_state(user_id)
        st["canettes"] = max(0, st["canettes"] + int(qty))
        self.update_recycler_state(user_id, **st)
        return st["canettes"]

    def add_recycler_sacs(self, user_id: int, qty: int) -> int:
        if int(qty) == 0:
            return self.get_recycler_state(user_id)["sacs"]
        st = self.get_recycler_state(user_id)
        st["sacs"] = max(0, st["sacs"] + int(qty))
        self.update_recycler_state(user_id, **st)
        return st["sacs"]

    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None:
        with self._conn() as con:
            con.execute("""
                INSERT OR IGNORE INTO recycler_claims(user_id, day_key, sacs_used, gross, tax, net)
                VALUES(?,?,?,?,?,?)
            """, (str(user_id), int(day_key), int(sacs_used), int(gross), int(tax), int(net)))