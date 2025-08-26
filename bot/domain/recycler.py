from ..persistence import recycler as repo

def get_state(user_id: int) -> dict:
    return repo.get_state(str(user_id))

def upsert_state(user_id: int, **fields) -> dict:
    return repo.upsert_state(str(user_id), **fields)

def add_canettes(user_id: int, qty: int) -> int:
    st = repo.get_state(str(user_id))
    st2 = repo.upsert_state(str(user_id), canettes=st["canettes"] + int(qty))
    return st2["canettes"]

def add_sacs(user_id: int, qty: int) -> int:
    st = repo.get_state(str(user_id))
    st2 = repo.upsert_state(str(user_id), sacs=st["sacs"] + int(qty))
    return st2["sacs"]

def log_claim(user_id: int, day_key: int, sacs_used: int, gross: int, tax: int, net: int) -> None:
    repo.log_claim(str(user_id), int(day_key), int(sacs_used), int(gross), int(tax), int(net))
