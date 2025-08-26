# bot/domain/economy.py
from __future__ import annotations

from ..persistence import ledger as Ledger

# Toutes les valeurs d'argent sont en centimes (int).

def balance(user_id: int) -> int:
    """Solde courant (source de vérité = ledger)."""
    return int(Ledger.sum_balance(str(user_id)))

def credit_once(user_id: int, amount: int, *, reason: str, idem_key: str) -> int:
    """
    Crédit idempotent: applique +amount une seule fois pour un idem_key donné.
    Renvoie le solde après application.
    """
    Ledger.add_once(str(user_id), idem_key, int(amount), reason or "credit")
    return balance(user_id)

def debit_once(user_id: int, amount: int, *, reason: str, idem_key: str) -> int:
    """
    Débit idempotent: applique -amount une seule fois pour un idem_key donné.
    Renvoie le solde après application.
    """
    if amount <= 0:
        raise ValueError("amount must be > 0")
    Ledger.add_once(str(user_id), idem_key, -int(amount), reason or "debit")
    return balance(user_id)

def top_richest(limit: int = 10) -> list[tuple[str, int]]:
    """Classement par solde (ledger)."""
    return [(uid, int(bal)) for uid, bal in Ledger.top_richest(int(limit))]
