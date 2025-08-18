# bot/modules/common/money.py
from __future__ import annotations

# ID et nom exact de l'emoji custom (uploadé dans ton app Discord)
MONEY_EMOJI_ID = 1407077638975127694
MONEY_EMOJI_NAME = "BiffCoins"
MONEY_EMOJI = f"<:{MONEY_EMOJI_NAME}:{MONEY_EMOJI_ID}>"

def fmt_eur(cents: int) -> str:
    """
    Formatte un montant en centimes → string avec ton emoji custom.
    Exemple: 1530 → '15,30<:BiffCoins:123456789>'
    """
    s = int(cents)
    euros = s // 100
    cents_part = abs(s) % 100
    sign = "-" if s < 0 else ""
    return f"{sign}{euros},{cents_part:02d} {MONEY_EMOJI}"