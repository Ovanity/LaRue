from __future__ import annotations

# Petit catalogue (tu pourras l’étendre)
ITEMS: dict[str, dict] = {
    "cup": {
        "name": "Gobelet en plastique",
        "price": 15,
        "desc": "Un gobelet propre. +10% sur mendier.",
        "tags": ["mendier"],
        "bonus": {"mendier_mult": 1.10},
        "unlock_at": 0,
    },
    "sign": {
        "name": "Pancarte marrante",
        "price": 60,
        "desc": "Marqué “J’code pour manger”. +1 à +3 sur mendier.",
        "tags": ["mendier"],
        "bonus": {"mendier_flat_min": 1, "mendier_flat_max": 3},
        "unlock_at": 40,
    },
    "dog": {
        "name": "Chien complice",
        "price": 200,
        "desc": "Regard triste assuré. +20% mendier, +10% fouiller.",
        "tags": ["mendier", "fouiller"],
        "bonus": {"mendier_mult": 1.20, "fouiller_mult": 1.10},
        "unlock_at": 150,
    },
}