from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
TZ = ZoneInfo("Europe/Paris")

def today_key(reset_hour: int = 8) -> str:
    now = datetime.now(TZ)
    if now.hour < reset_hour:
        now = now - timedelta(days=1)
    return now.date().isoformat()  # "YYYY-MM-DD"
