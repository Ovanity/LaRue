from ..persistence import players as repo

def get(user_id: int) -> dict:
    return repo.get_or_create(str(user_id))

def update(user_id: int, **fields) -> dict:
    cur = repo.get_or_create(str(user_id))
    has_started = int(bool(fields.get("has_started", cur["has_started"])))
    money = int(fields.get("money", cur.get("money", 0)))  # legacy miroir, bientôt ignoré
    return repo.upsert(str(user_id), has_started, money)

def count() -> int:
    return repo.count_players()
