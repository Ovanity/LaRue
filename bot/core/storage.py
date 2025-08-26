# bot/core/storage.py  — shim de compat (zéro SQL, zéro repo)
from __future__ import annotations
from typing import TypedDict, cast

from bot.domain import quotas
from bot.domain import economy as d_economy
from bot.domain import players as d_players
from bot.domain import inventory as d_inventory
from bot.domain import stats as d_stats
from bot.domain import profiles as d_profiles
from bot.domain import respect as d_respect
from bot.domain import recycler as d_recycler
from bot.domain import actions as d_actions
from bot.domain import admin as d_admin


class Player(TypedDict, total=False):
    has_started: bool
    money: int  # legacy, non utilisé pour le solde réel


class Storage:
    # API de stockage (sans argent direct: utiliser credit_once/debit_once côté domain.economy)
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...
    def count_players(self) -> int: ...
    def get_inventory(self, user_id: int) -> dict[str, int]: ...
    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None: ...
    def get_money(self, user_id: int) -> int: ...
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int): ...
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
    def can_give_respect(self, from_id: int, to_id: int): ...
    def give_respect(self, from_id: int, to_id: int) -> int: ...
    def top_profiles_by_cred(self, limit: int = 10): ...
    def get_recycler_state(self, user_id: int) -> dict: ...
    def update_recycler_state(self, user_id: int, **fields) -> dict: ...
    def add_recycler_canettes(self, user_id: int, qty: int) -> int: ...
    def add_recycler_sacs(self, user_id: int, qty: int) -> int: ...
    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None: ...


class SQLiteStorage(Storage):
    def __init__(self, root: str):
        # Ne fait plus de migrations ni d'accès DB ici.
        # Les migrations sont déclenchées au boot (voir __main__.py).
        pass

    # Joueurs
    def get_player(self, user_id: int) -> Player:
        return cast(Player, d_players.get(user_id))

    def update_player(self, user_id: int, **fields) -> Player:
        return cast(Player, d_players.update(user_id, **fields))

    def count_players(self) -> int:
        return d_players.count()

    # Inventaire
    def get_inventory(self, user_id: int) -> dict[str, int]:
        return d_inventory.get(user_id)

    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None:
        d_inventory.add_item(user_id, item_id, qty)

    # Argent (source de vérité: ledger)
    def get_money(self, user_id: int) -> int:
        return int(d_economy.balance(user_id))

    # Cooldowns / quotas
    def check_and_touch_action(self, user_id: int, action: str, cooldown_s: int, daily_cap: int):
        return quotas.check_and_touch(user_id, action, int(cooldown_s), int(daily_cap))

    def get_action_state(self, user_id: int, action: str) -> dict:
        return d_actions.get_state(user_id, action)

    # Stats
    def increment_stat(self, user_id: int, key: str, delta: int = 1) -> int:
        return d_stats.incr(user_id, key, delta)

    def get_stat(self, user_id: int, key: str, default: int = 0) -> int:
        return d_stats.get(user_id, key, default)

    def get_stats(self, user_id: int) -> dict[str, int]:
        return d_stats.all_for(user_id)

    # Admin (reset)
    def reset_players(self) -> None:
        d_admin.reset_players()

    def reset_actions(self) -> None:
        d_admin.reset_actions()

    def reset_inventory(self) -> None:
        d_admin.reset_inventory()

    def reset_stats(self) -> None:
        d_admin.reset_stats()

    # Profils / respect
    def get_profile(self, user_id: int) -> dict:
        return d_profiles.get(user_id)

    def upsert_profile(self, user_id: int, **fields) -> dict:
        return d_profiles.upsert(user_id, **fields)

    def can_give_respect(self, from_id: int, to_id: int):
        return d_respect.can_give(from_id, to_id)

    def give_respect(self, from_id: int, to_id: int) -> int:
        return d_respect.give(from_id, to_id)

    def top_profiles_by_cred(self, limit: int = 10):
        return d_profiles.top_by_cred(limit)

    # Recyclerie
    def get_recycler_state(self, user_id: int) -> dict:
        return d_recycler.get_state(user_id)

    def update_recycler_state(self, user_id: int, **fields) -> dict:
        return d_recycler.upsert_state(user_id, **fields)

    def add_recycler_canettes(self, user_id: int, qty: int) -> int:
        return d_recycler.add_canettes(user_id, qty)

    def add_recycler_sacs(self, user_id: int, qty: int) -> int:
        return d_recycler.add_sacs(user_id, qty)

    def log_recycler_claim(self, user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None:
        d_recycler.log_claim(user_id, day_key, sacs_used, gross, tax, net)
