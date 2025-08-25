# bot/domain/economy.py
from __future__ import annotations

from ..persistence import players as Players

# Ledger peut ne pas être dispo pendant certaines migrations/branches
try:
    from ..persistence import ledger as Ledger  # type: ignore
    _LEDGER_AVAILABLE = True
except Exception:
    Ledger = None  # type: ignore
    _LEDGER_AVAILABLE = False


def _sum_ledger(uid: str) -> int | None:
    """Somme le solde dans le ledger. None si ledger indisponible/erreur."""
    if not _LEDGER_AVAILABLE:
        return None
    try:
        return int(Ledger.sum_balance(uid))  # type: ignore[attr-defined]
    except Exception:
        return None


def balance(user_id: int) -> int:
    """
    Source de vérité du solde.
    - Si le ledger répond: on renvoie sa somme (même si 0).
    - Sinon fallback legacy: players.money
    """
    uid = str(user_id)
    b = _sum_ledger(uid)
    if b is not None:
        return b
    return int(Players.get_or_create(uid)["money"])


def credit_once(user_id: int, amount: int, key: str, reason: str = "") -> int:
    """
    Crédit idempotent:
    - Tente ledger.add_once(uid, key, amount, reason)
    - Fallback legacy (non idempotent) sur players si ledger indispo
    - Renvoie TOUJOURS balance(uid)
    """
    uid = str(user_id)
    applied = False
    used_ledger = False

    if _LEDGER_AVAILABLE:
        try:
            applied = bool(Ledger.add_once(uid, key, int(amount), reason or "credit"))  # type: ignore[attr-defined]
            used_ledger = True
        except Exception:
            used_ledger = False

    if not used_ledger:
        # Pas de ledger → applique quand même côté players (legacy)
        Players.add_money(uid, int(amount))
        applied = True

    if applied and used_ledger:
        # Garde players.money à peu près en phase pour l'ancien code (best-effort)
        try:
            Players.add_money(uid, int(amount))
        except Exception:
            pass

    # ← TOUJOURS retourner la source de vérité
    b = _sum_ledger(uid)
    return b if b is not None else int(Players.get_or_create(uid)["money"])


def debit_once(user_id: int, amount: int, key: str, reason: str = "") -> int:
    if amount <= 0:
        raise ValueError("amount must be > 0")
    return credit_once(user_id, -int(amount), key, reason or "debit")

def top_richest(limit: int = 10) -> list[tuple[str, int]]:
    """
    Classement par solde.
    - Si le ledger est dispo: SUM(delta) GROUP BY user_id, tri desc.
    - Sinon: fallback legacy players.top_richest().
    """
    if _LEDGER_AVAILABLE:
        try:
            # nécessite une petite fonction côté persistence/ledger
            return [(uid, int(bal)) for uid, bal in Ledger.top_richest(int(limit))]  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        return Players.top_richest(limit=int(limit))
    except Exception:
        return []
