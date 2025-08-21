import os, sqlite3, threading
from contextlib import contextmanager

DATA_DIR = os.getenv("DATA_DIR", "./data")  # en dev: ./data-dev
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "larue.db")

_tls = threading.local()

def _connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-20000;")
    con.execute("PRAGMA busy_timeout=5000;")
    return con

def get_conn():
    con = getattr(_tls, "con", None)
    if con is None:
        con = _connect()
        _tls.con = con
    return con

@contextmanager
def atomic(con=None, immediate=True):
    con = con or get_conn()
    try:
        con.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
        yield con
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise
