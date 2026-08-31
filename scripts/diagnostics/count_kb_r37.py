import sqlite3
from pathlib import Path

path = Path(str(Path(__file__).resolve().parent.parent / "data" / "kb_evolve.sqlite"))
con = sqlite3.connect(path)
try:
    for (name,) in con.execute("select name from sqlite_master where type='table' order by name"):
        try:
            count = con.execute(f"select count(*) from [{name}]").fetchone()[0]
            print(f"{name}={count}")
        except Exception as exc:
            print(f"{name}=ERROR:{type(exc).__name__}")
finally:
    con.close()
