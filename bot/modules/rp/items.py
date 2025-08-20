ITEMS = {
    "cup": {
        "name": "Gobelet en plastique",
        "price": 150,  # 1,50 €
        "desc": "Un petit plus à chaque mendier. Basique. Efficace.",
        "bonus": {"mendier_mult": 1.15},
        "unlock_cmd": {"mendier_count": 5},
    },
    "sign": {
        "name": "Pancarte marrante",
        "price": 600,  # 6,00 €
        "desc": "Ton message fait sourire — et donner. Chaque mendier tape plus haut.",
        "bonus": {"mendier_flat_min": 8, "mendier_flat_max": 15},
        "unlock_cmd": {"mendier_count": 20},
    },
    "dog": {
        "name": "Chien complice",
        "price": 2000,  # 20,00 €
        "desc": "Ta mascotte du trottoir : plus de pièces, fouilles plus juteuses, et davantage de canettes.",
        "bonus": {
            "mendier_mult": 1.20,
            "fouiller_mult": 1.10,
            "recy_canette_prob_mult": 1.15,  # (synergie recyclerie)
            "recy_canette_roll_bonus": 10
        },
        "unlock_cmd": {"fouiller_count": 5},
    },
}