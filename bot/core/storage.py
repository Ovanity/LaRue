# bot/core/storage.py
from __future__ import annotations
from typing import TypedDict, cast

from ..core.db.base import get_conn
from ..core.db.migrations import migrate_if_needed
from ..domain import quotas
from ..persistence import players, inventory, stats, profiles, respect, recycler
from ..persistence import actions as actions_repo
from bot.domain.economy import balance


class Player(TypedDict, total=False):
    has_started: bool
    money: int  # legacy (non utilisé pour le solde effectif)


class Storage:
    # API de stockage (sans argent direct : utiliser credit_once/debit_once)
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...
    def count_players(self) -> int: ...
    def get_inventory(self, user_id: int) -> dict[str, int]: ...
    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None: ...
    def get_money(self, user_id: int) -> int: ...
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int) -> tuple[bool, int, int]: ...
    def get_action_state(self, user_id: int, action: str) -> dict: ...
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int: ...
    def get_stat(self, user_id: int, key: str, default: int = 0) -> int: ...
    def get_stats(self, user_id: int) -> dict[str, int]: ...
    def reset_players(self) -> None: ...
    def reset_actions(self) -> None: ...
    def reset_inventory(self) -> None: ...
    def reset_stats(self) -> None: ...
    def get_profile(self, user_id: int) -> dict: ...
    def upsert_profile(self, user_id: int, **fields) -> dict: ...
    def can_give_respect(self, from_id: int, to_id: int) -> tuple[bool, str | None]: ...
    def give_respect(self, from_id: int, to_id: int) -> int: ...
    def top_profiles_by_cred(self, limit: int = 10) -> list[tuple[str, int]]: ...
    def get_recycler_state(self, user_id: int) -> dict: ...
    def update_recycler_state(self, user_id: int, **fields) -> dict: ...
    def add_recycler_canettes(self, user_id: int, qty: int) -> int: ...
    def add_recycler_sacs(self, user_id: int, qty: int) -> int: ...
    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None: ...


class SQLiteStorage(Storage):
    def __init__(self, root: str):
        # root ignoré: on lit DATA_DIR via base.py
        with get_conn() as con:
            migrate_if_needed(con)

    # ── Joueurs ────────────────────────────────────────────────────
    def get_player(self, user_id: int) -> Player:
        return cast(Player, players.get_or_create(str(user_id)))

    def update_player(self, user_id: int, **fields) -> Player:
        cur = players.get_or_create(str(user_id))
        has_started = int(bool(fields.get("has_started", cur["has_started"])))
        money = int(fields.get("money", cur["money"]))  # legacy
        return cast(Player, players.upsert(str(user_id), has_started, money))

    def count_players(self) -> int:
        return players.count_players()

    # ── Inventaire ────────────────────────────────────────────────
    def get_inventory(self, user_id: int) -> dict[str, int]:
        return inventory.get_inventory(str(user_id))

    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None:
        inventory.add_item(str(user_id), item_id, int(qty))

    # ── Argent (source de vérité: ledger via balance()) ───────────
    def get_money(self, user_id: int) -> int:
        return int(balance(user_id))

    # ── Cooldowns / quotas ────────────────────────────────────────
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int):
        return quotas.check_and_touch(user_id, action, int(cooldown_s), int(daily_cap))

    def get_action_state(self, user_id: int, action: str) -> dict:
        return actions_repo.get_state(str(user_id), action)

    # ── Stats ─────────────────────────────────────────────────────
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int:
        return stats.incr(str(user_id), key, int(delta))

    def get_stat(self, user_id: int, key: str, default: int = 0) -> int:
        return stats.get(str(user_id), key, int(default))

    def get_stats(self, user_id: int) -> dict[str, int]:
        return stats.all_for(str(user_id))

    # ── Admin (reset) ─────────────────────────────────────────────
    def reset_players(self) -> None:
        con = get_conn(); con.execute("DELETE FROM players;")

    def reset_actions(self) -> None:
        con = get_conn(); con.execute("DELETE FROM actions;")

    def reset_inventory(self) -> None:
        con = get_conn(); con.execute("DELETE FROM inventory;")

    def reset_stats(self) -> None:
        con = get_conn(); con.execute("DELETE FROM stats;")

    # ── Profils / respect ─────────────────────────────────────────
    def get_profile(self, user_id: int) -> dict:
        return profiles.get_or_create(str(user_id))

    def upsert_profile(self, user_id: int, **fields) -> dict:
        return profiles.upsert(str(user_id), **fields)

    def can_give_respect(self, from_id: int, to_id: int):
        from ..domain.clock import today_key
        day = today_key()
        return respect.can_give(str(from_id), str(to_id), day)

    def give_respect(self, from_id: int, to_id: int) -> int:
        from ..domain.clock import today_key
        return respect.give(str(from_id), str(to_id), today_key())

    def top_profiles_by_cred(self, limit: int = 10):
        return profiles.top_by_cred(int(limit))

    # ── Recyclerie ────────────────────────────────────────────────
    def get_recycler_state(self, user_id: int) -> dict:
        return recycler.get_state(str(user_id))

    def update_recycler_state(self, user_id: int, **fields) -> dict:
        return recycler.upsert_state(str(user_id), **fields)

    def add_recycler_canettes(self, user_id: int, qty: int) -> int:
        st = recycler.get_state(str(user_id))
        st2 = recycler.upsert_state(str(user_id), canettes=st["canettes"] + int(qty))
        return st2["canettes"]

    def add_recycler_sacs(self, user_id: int, qty: int) -> int:
        st = recycler.get_state(str(user_id))
        st2 = recycler.upsert_state(str(user_id), sacs=st["sacs"] + int(qty))
        return st2["sacs"]

    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None:
        recycler.log_claim(str(user_id), int(day_key), int(sacs_used), int(gross), int(tax), int(net))
