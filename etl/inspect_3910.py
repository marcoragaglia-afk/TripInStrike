import sqlite3
from pathlib import Path
DB = Path(__file__).parent.parent / "db" / "sciopero.db"
conn = sqlite3.connect(str(DB))
for tn in ["3910", "23836", "23838", "23754"]:
    t = conn.execute(
        "SELECT origin, destination, dep_time, arr_time FROM guaranteed_trains WHERE train_number=?",
        (tn,),
    ).fetchall()
    print(f"\n=== Treno {tn} ===")
    for r in t:
        print(f"  {r}")
    stops = conn.execute(
        "SELECT sequence, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence",
        (tn,),
    ).fetchall()
    print(f"  fermate ({len(stops)}):")
    for s in stops:
        arr = s[2] or ""
        dep = s[3] or ""
        print(f"    seq={s[0]:2d}  {s[1]:40s}  arr={arr:5s}  dep={dep:5s}")
