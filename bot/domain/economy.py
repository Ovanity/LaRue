# domain/economy.py
from ..persistence import players as players_repo, ledger as ledger_repo

def balance(user_id: int) -> int:
    uid = str(user_id)
    try:
        b = ledger_repo.sum_balance(uid)
        if b != 0:
            return b
    except Exception:
        pass
    return players_repo.get_or_create(uid)["money"]

def credit_once(user_id: int, amount: int, key: str, reason: str = "") -> int:
    uid = str(user_id)
    applied = False
    try:
        applied = ledger_repo.add_once(uid, key, int(amount), reason or "credit")
    except Exception:
        applied = True
    if applied:
        after = players_repo.add_money(uid, int(amount))["money"]
    else:
        after = players_repo.get_or_create(uid)["money"]
    return int(after)

def debit_once(user_id: int, amount: int, key: str, reason: str = "") -> int:
    if amount <= 0:
        raise ValueError("amount must be > 0")
    return credit_once(user_id, -int(amount), key, reason or "debit")
