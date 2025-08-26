from ..persistence import profiles as repo

def get(user_id: int) -> dict:
    return repo.get_or_create(str(user_id))

def upsert(user_id: int, **fields) -> dict:
    return repo.upsert(str(user_id), **fields)

def top_by_cred(limit: int = 10):
    return repo.top_by_cred(int(limit))
