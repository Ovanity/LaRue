# bot/modules/rp/boosts.py
from __future__ import annotations

from bot.modules.rp.items import ITEMS  # même schéma que ton shop
from bot.domain import inventory as d_inventory

def compute_power(user_id: int) -> dict:
    """
    Agrège les bonus de l'inventaire:
      - *_flat_* : somme
      - *_mult   : produit
    Retourne un dict avec des valeurs par défaut sûres.
    """
    inv = d_inventory.get(user_id) or {}

    total = {
        "mendier_flat_min": 0,
        "mendier_flat_max": 0,
        "fouiller_flat_min": 0,
        "fouiller_flat_max": 0,
        "mendier_mult": 1.0,
        "fouiller_mult": 1.0,
    }

    for iid, qty in inv.items():
        it = ITEMS.get(iid)
        if not it:
            continue
        bonus = it.get("bonus") or {}
        q = max(0, int(qty))

        # Les boosts du shop sont mono-achat (cap 1) par sécurité.
        boost_keys = (
            "mendier_flat_min", "mendier_flat_max", "mendier_mult",
            "fouiller_flat_min", "fouiller_flat_max", "fouiller_mult",
        )
        if any(k in bonus for k in boost_keys):
            q = min(q, 1)

        for k, v in bonus.items():
            if k.endswith("_mult"):
                total[k] *= float(v) ** q
            elif k.endswith("_flat_min") or k.endswith("_flat_max"):
                total[k] += int(v) * q

    return total
