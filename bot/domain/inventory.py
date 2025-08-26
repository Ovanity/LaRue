from ..persistence import inventory as repo

def get(user_id: int) -> dict[str, int]:
    return repo.get_inventory(str(user_id))

def add_item(user_id: int, item_id: str, qty: int = 1) -> None:
    repo.add_item(str(user_id), item_id, int(qty))
