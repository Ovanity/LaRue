from ..core.db.base import get_conn

def reset_players() -> None:
    con = get_conn()
    con.execute("DELETE FROM players;")

def reset_actions() -> None:
    con = get_conn()
    con.execute("DELETE FROM actions;")

def reset_inventory() -> None:
    con = get_conn()
    con.execute("DELETE FROM inventory;")

def reset_stats() -> None:
    con = get_conn()
    con.execute("DELETE FROM stats;")
