from ..persistence import stats as repo

def incr(user_id: int, key: str, delta: int = 1) -> int:
    return repo.incr(str(user_id), key, int(delta))

def get(user_id: int, key: str, default: int = 0) -> int:
    return repo.get(str(user_id), key, int(default))

def all_for(user_id: int) -> dict[str, int]:
    return repo.all_for(str(user_id))
