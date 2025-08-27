from __future__ import annotations
from typing import Optional, Dict
from bot.core.db.base import get_conn, atomic

def was_broadcasted(event_key: str) -> bool:
    con = get_conn()
    row = con.execute("SELECT 1 FROM broadcast_log WHERE event_key=? LIMIT 1", (event_key,)).fetchone()
    return bool(row)

def record_broadcast(event_key: str, guild_id: str, channel_id: str, message_id: str, jump_url: str) -> None:
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT OR IGNORE INTO broadcast_log(event_key,guild_id,channel_id,message_id,jump_url) "
            "VALUES(?,?,?,?,?)",
            (event_key, str(guild_id), str(channel_id), str(message_id), str(jump_url)),
        )

def get_broadcast(event_key: str) -> Optional[Dict]:
    con = get_conn()
    row = con.execute(
        "SELECT event_key,guild_id,channel_id,message_id,jump_url,ts FROM broadcast_log WHERE event_key=?",
        (event_key,),
    ).fetchone()
    if not row: return None
    return {
        "event_key": row[0], "guild_id": row[1], "channel_id": row[2],
        "message_id": row[3], "jump_url": row[4], "ts": int(row[5]),
    }
