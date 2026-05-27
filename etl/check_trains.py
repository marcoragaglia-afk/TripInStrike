import sqlite3
from pathlib import Path
DB = Path(__file__).parent.parent / "db" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

for tn in ("8814", "3904", "2908"):
    print(f"\n=== Treno {tn} ===")
    rows = conn.execute(
        "SELECT id, origin, destination, dep_time, arr_time, day_type, table_type, line "
        "FROM guaranteed_trains WHERE train_number=?", (tn,)
    ).fetchall()
    for r in rows:
        print(f"  id={r['id']}  [{r['table_type']}] {r['origin']:25s} -> {r['destination']:25s}  "
              f"dep={r['dep_time']} arr={r['arr_time']} day={r['day_type']}")
        print(f"    line={r['line']!r}")
    print(f"  Fermate:")
    stops = conn.execute(
        "SELECT sequence, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    for s in stops:
        print(f"    seq={s['sequence']:2d}  {s['station']:30s}  arr={s['arrival'] or '':5s}  dep={s['departure'] or '':5s}")
    if not stops:
        print(f"    (nessuna fermata)")
conn.close()
