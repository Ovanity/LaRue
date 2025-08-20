ITEMS = {
    "gobelet": {
        "name": "Gobelet en plastique",
        "price": 150,  # 1,50 €
        "desc": "Un petit plus quand tu mendies.",
        "bonus": {"mendier_mult": 1.15},
        "unlock_cmd": {"mendier_count": 5},
    },
    "pancarte": {
        "name": "Pancarte marrante",
        "price": 600,  # 6,00 €
        "desc": "Ton message fait sourire et donner plus.",
        "bonus": {"mendier_flat_min": 8, "mendier_flat_max": 15},
        "unlock_cmd": {"mendier_count": 20},
    },
    "chien": {
        "name": "Chien complice",
        "price": 2000,  # 20,00 €
        "desc": "Ta mascotte du trottoir : plus de BiffCoins, fouilles plus juteuses, et bonus de canettes.",
        "bonus": {
            "mendier_mult": 1.20,
            "fouiller_mult": 1.10,
            "recy_canette_prob_mult": 1.15,  # (synergie recyclerie)
            "recy_canette_roll_bonus": 10
        },
        "unlock_cmd": {"fouiller_count": 5},
    },
}