from ..persistence import actions as repo

def get_state(user_id: int, action: str) -> dict:
    return repo.get_state(str(user_id), action)
