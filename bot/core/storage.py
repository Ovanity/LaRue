from __future__ import annotations
import json, threading
from pathlib import Path
from typing import TypedDict

class Player(TypedDict, total=False):
    has_started: bool
    money: int

class Storage:
    def get_player(self, user_id: int) -> Player: ...
    def update_player(self, user_id: int, **fields) -> Player: ...

class JSONStorage(Storage):
    def __init__(self, root: str):
        self.path = Path(root) / "players.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self.path.write_text("{}")

    def _load(self) -> dict[str, Player]:
        with self._lock:
            return json.loads(self.path.read_text())

    def _save(self, data: dict[str, Player]) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            tmp.replace(self.path)

    def get_player(self, user_id: int) -> Player:
        data = self._load()
        k = str(user_id)
        if k not in data:
            data[k] = {"has_started": False, "money": 0}
            self._save(data)
        return data[k]

    def update_player(self, user_id: int, **fields) -> Player:
        data = self._load()
        k = str(user_id)
        p = data.get(k, {"has_started": False, "money": 0})
        p.update(fields)
        data[k] = p
        self._save(data)
        return p
