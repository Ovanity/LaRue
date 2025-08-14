from __future__ import annotations
from bot.modules.rp.items import ITEMS

def compute_power(storage, user_id: int) -> dict[str, float | int]:
    """
    Calcule les bonus cumulés à partir de l’inventaire.
    - multiplicateurs se multiplient par stack
    - bonus plats s’additionnent par stack
    """
    inv = storage.get_inventory(user_id)
    power: dict[str, float | int] = {
        "mendier_mult": 1.0,
        "mendier_flat_min": 0,
        "mendier_flat_max": 0,
        "fouiller_mult": 1.0,
    }
    for item_id, qty in inv.items():
        it = ITEMS.get(item_id)
        if not it or qty <= 0:
            continue
        b = it.get("bonus", {})
        if "mendier_mult" in b:
            power["mendier_mult"] *= (float(b["mendier_mult"]) ** qty)
        if "fouiller_mult" in b:
            power["fouiller_mult"] *= (float(b["fouiller_mult"]) ** qty)
        if "mendier_flat_min" in b:
            power["mendier_flat_min"] += int(b["mendier_flat_min"]) * qty
        if "mendier_flat_max" in b:
            power["mendier_flat_max"] += int(b["mendier_flat_max"]) * qty
    return power