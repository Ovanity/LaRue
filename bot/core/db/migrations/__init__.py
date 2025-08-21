from . import v0001_base, v0002_recycler, v0003_idx, v0004_ledger

def migrate_if_needed(con):
    (ver,) = con.execute("PRAGMA user_version").fetchone()
    ver = int(ver or 0)

    if ver < 1:
        v0001_base.apply(con);  con.execute("PRAGMA user_version=1"); ver = 1
    if ver < 2:
        v0002_recycler.apply(con); con.execute("PRAGMA user_version=2"); ver = 2
    if ver < 3:
        v0003_idx.apply(con); con.execute("PRAGMA user_version=3"); ver = 3
    if ver < 4:
        v0004_ledger.apply(con); con.execute("PRAGMA user_version=4"); ver = 4
