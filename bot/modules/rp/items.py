from __future__ import annotations

# Tous les montants sont en CENTIMES (ex: 150 = 1,50€)
ITEMS: dict[str, dict] = {
    "cup": {
        "name": "Gobelet en plastique",
        "price": 150,  # 1,50 €
        "desc": "Un gobelet propre. +10% sur mendier.",
        "tags": ["mendier"],
        "bonus": {"mendier_mult": 1.10},
        "unlock_at": 0,  # pas de palier requis
    },
    "sign": {
        "name": "Pancarte marrante",
        "price": 600,  # 6,00 €
        "desc": "Marqué “J’code pour manger”. +0,01€ à +0,03€ sur mendier.",
        "tags": ["mendier"],
        # NB: ces flats s'interprètent côté boosts comme des CENTIMES ajoutés avant multiplicateur
        "bonus": {"mendier_flat_min": 1, "mendier_flat_max": 3},  # 1c à 3c
        "unlock_at": 400,  # 4,00 € de patrimoine
    },
    "dog": {
        "name": "Chien complice",
        "price": 2000,  # 20,00 €
        "desc": "Regard triste assuré. +20% mendier, +10% fouiller.",
        "tags": ["mendier", "fouiller"],
        "bonus": {"mendier_mult": 1.20, "fouiller_mult": 1.10},
        "unlock_at": 1500,  # 15,00 €
    },
    # Tu pourras étendre ici, par ex.:
    # "thermos": {
    #     "name": "Thermos tiède",
    #     "price": 900,  # 9,00 €
    #     "desc": "Tu fais pitié mais organisé. +5% mendier.",
    #     "tags": ["mendier"],
    #     "bonus": {"mendier_mult": 1.05},
    #     "unlock_at": 500,  # 5,00 €
    # },
}