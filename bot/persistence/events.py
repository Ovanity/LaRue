from __future__ import annotations
from typing import Optional, Dict, List
import json, time
from bot.core.db.base import get_conn, atomic

def upsert_event(event_id: str, kind: str, title: str = "", starts_at: int = 0,
                 ends_at: int = 0, payload: dict | None = None, status: str = "scheduled") -> Dict:
    pj = json.dumps(payload or {}, ensure_ascii=False)
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT OR IGNORE INTO events(id,kind,title,starts_at,ends_at,payload_json,status) "
            "VALUES(?,?,?,?,?,?,?)",
            (event_id, kind, title or "", int(starts_at), int(ends_at), pj, status)
        )
        con.execute(
            "UPDATE events SET kind=?, title=?, starts_at=?, ends_at=?, payload_json=?, status=? WHERE id=?",
            (kind, title or "", int(starts_at), int(ends_at), pj, status, event_id)
        )
        row = con.execute("SELECT id,kind,title,starts_at,ends_at,payload_json,status,jump_url,created_ts "
                          "FROM events WHERE id=?", (event_id,)).fetchone()
    return _row_to_event(row)

def set_published(event_id: str, jump_url: str) -> None:
    with atomic():
        con = get_conn()
        con.execute("UPDATE events SET status='published', jump_url=? WHERE id=?", (jump_url, event_id))

def get(event_id: str) -> Optional[Dict]:
    con = get_conn()
    row = con.execute("SELECT id,kind,title,starts_at,ends_at,payload_json,status,jump_url,created_ts "
                      "FROM events WHERE id=?", (event_id,)).fetchone()
    return _row_to_event(row) if row else None

def list_recent(limit: int = 3) -> List[Dict]:
    # Les 3 derniers events publiés ou en cours (ends_at futur ou 0)
    now = int(time.time())
    con = get_conn()
    rows = con.execute(
        "SELECT id,kind,title,starts_at,ends_at,payload_json,status,jump_url,created_ts "
        "FROM events WHERE status='published' AND (ends_at=0 OR ends_at>=?) "
        "ORDER BY starts_at DESC, created_ts DESC LIMIT ?",
        (now, int(limit))
    ).fetchall()
    return [_row_to_event(r) for r in rows]

def _row_to_event(row) -> Dict:
    return {
        "id": row[0], "kind": row[1], "title": row[2],
        "starts_at": int(row[3]), "ends_at": int(row[4]),
        "payload": json.loads(row[5] or "{}"),
        "status": row[6], "jump_url": row[7] or "",
        "created_ts": int(row[8]),
    }

def list_due(now: int, limit: int = 10) -> List[Dict]:
    con = get_conn()
    rows = con.execute(
        "SELECT id,kind,title,starts_at,ends_at,payload_json,status,jump_url,created_ts "
        "FROM events WHERE status='scheduled' AND starts_at>0 AND starts_at<=? "
        "ORDER BY starts_at ASC LIMIT ?",
        (int(now), int(limit))
    ).fetchall()
    return [_row_to_event(r) for r in rows]
