# bot/core/storage.py — legacy shim (compat uniquement, zéro SQL)
from __future__ import annotations
from typing import TypedDict, cast
import os, warnings

from bot.domain import quotas as d_quotas
from bot.domain import economy as d_economy
from bot.domain import players as d_players
from bot.domain import inventory as d_inventory
from bot.domain import stats as d_stats
from bot.domain import actions as d_actions
from bot.domain import recycler as d_recycler

# ── Garde-fou
_WARN = os.getenv("STORAGE_DEPR_WARN", "1") != "0"
_STRICT = os.getenv("STORAGE_STRICT", "0") == "1"

def _note(method: str):
    if _STRICT:
        raise RuntimeError(f"storage.{method} appelé — utilise bot.domain.* directement")
    if _WARN:
        warnings.warn(
            f"storage.{method} est un shim legacy — migre vers bot.domain.*",
            DeprecationWarning, stacklevel=2
        )

class Player(TypedDict, total=False):
    has_started: bool
    money: int  # legacy, non utilisé pour le solde réel

class Storage:
    # Surface minimale pour compat modules restants
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...
    def get_inventory(self, user_id: int) -> dict[str, int]: ...
    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None: ...
    def get_money(self, user_id: int) -> int: ...
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int): ...
    def get_action_state(self, user_id: int, action: str) -> dict: ...
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int: ...
    def get_stat(self, user_id: int, key: str, default: int = 0) -> int: ...
    def get_stats(self, user_id: int) -> dict[str, int]: ...
    def top_richest(self, limit: int = 10): ...
    # Recyclerie
    def get_recycler_state(self, user_id: int) -> dict: ...
    def update_recycler_state(self, user_id: int, **fields) -> dict: ...
    def add_recycler_canettes(self, user_id: int, qty: int) -> int: ...
    def add_recycler_sacs(self, user_id: int, qty: int) -> int: ...
    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None: ...

class SQLiteStorage(Storage):
    def __init__(self, root: str):
        # Migrations/DB gérées ailleurs au boot.
        pass

    # ── Joueurs
    def get_player(self, user_id: int) -> Player:
        _note("get_player")
        return cast(Player, d_players.get(user_id))

    def update_player(self, user_id: int, **fields) -> Player:
        _note("update_player")
        return cast(Player, d_players.update(user_id, **fields))

    # ── Inventaire
    def get_inventory(self, user_id: int) -> dict[str, int]:
        _note("get_inventory")
        return d_inventory.get(user_id)

    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None:
        _note("add_item")
        d_inventory.add_item(user_id, item_id, qty)

    # ── Argent (ledger)
    def get_money(self, user_id: int) -> int:
        _note("get_money")
        return int(d_economy.balance(user_id))

    # ── Cooldowns / actions
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int):
        _note("check_and_touch_action")
        return d_quotas.check_and_touch(user_id, action, int(cooldown_s), int(daily_cap))

    def get_action_state(self, user_id: int, action: str) -> dict:
        _note("get_action_state")
        return d_actions.get_state(user_id, action)

    # ── Stats
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int:
        _note("increment_stat")
        return d_stats.incr(user_id, key, int(delta))

    def get_stat(self, user_id: int, key: str, default: int = 0) -> int:
        _note("get_stat")
        return d_stats.get(user_id, key, int(default))

    def get_stats(self, user_id: int) -> dict[str, int]:
        _note("get_stats")
        return d_stats.all_for(user_id)

    # ── Classement (utile pour /hess classement)
    def top_richest(self, limit: int = 10):
        _note("top_richest")
        return d_economy.top_richest(int(limit))

    # ── Recyclerie
    def get_recycler_state(self, user_id: int) -> dict:
        _note("get_recycler_state")
        return d_recycler.get_state(user_id)

    def update_recycler_state(self, user_id: int, **fields) -> dict:
        _note("update_recycler_state")
        return d_recycler.upsert_state(user_id, **fields)

    def add_recycler_canettes(self, user_id: int, qty: int) -> int:
        _note("add_recycler_canettes")
        return d_recycler.add_canettes(user_id, qty)

    def add_recycler_sacs(self, user_id: int, qty: int) -> int:
        _note("add_recycler_sacs")
        return d_recycler.add_sacs(user_id, qty)

    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None:
        _note("log_recycler_claim")
        d_recycler.log_claim(user_id, day_key, sacs_used, gross, tax, net)
