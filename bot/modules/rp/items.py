ITEMS = {
    "cup": {
        "name": "Gobelet en plastique",
        "price": 150,  # 1,50€ en centimes
        "desc": "+10% sur mendier.",
        "bonus": {"mendier_mult": 1.10},
        "unlock_cmd": {"mendier_count": 5},  # ← 5 utilisations de /hess mendier
    },
    "sign": {
        "name": "Pancarte marrante",
        "price": 600,
        "desc": "+1 à +3 sur mendier.",
        "bonus": {"mendier_flat_min": 1, "mendier_flat_max": 3},
        "unlock_cmd": {"mendier_count": 20},
    },
    "dog": {
        "name": "Chien complice",
        "price": 2000,
        "desc": "+20% mendier, +10% fouiller.",
        "bonus": {"mendier_mult": 1.20, "fouiller_mult": 1.10},
        "unlock_cmd": {"mendier_count": 40, "fouiller_count": 5},
    },
}