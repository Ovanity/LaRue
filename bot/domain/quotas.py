import time
from .clock import today_key
from ..persistence import actions as actions_repo  # ← snake_case

def check_and_touch(user_id: int, action: str, cooldown_s: int, daily_cap: int):
    uid = str(user_id)
    now = int(time.time())
    today = today_key()

    st = actions_repo.get_state(uid, action)  # ← maj ici
    last_ts, day, count = st["last_ts"], st["day"], st["count"]

    if day != today:
        day, count = today, 0

    if count >= daily_cap:
        return (False, 0, 0)

    wait = (last_ts + cooldown_s) - now
    if wait > 0:
        return (False, int(wait), max(0, daily_cap - count))

    new_count = count + 1
    actions_repo.touch(uid, action, now, day, new_count)  # ← maj ici
    return (True, 0, max(0, daily_cap - new_count))
