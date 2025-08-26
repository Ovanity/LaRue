from ..persistence import respect as repo
from .clock import today_key

def can_give(from_id: int, to_id: int):
    day = today_key()
    return repo.can_give(str(from_id), str(to_id), day)

def give(from_id: int, to_id: int) -> int:
    day = today_key()
    return repo.give(str(from_id), str(to_id), day)
