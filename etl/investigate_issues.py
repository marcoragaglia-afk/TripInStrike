"""Investiga i treni problematici per capire la natura dei bug."""
import sqlite3
from pathlib import Path
DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

for tn in ("9702", "9406", "9414", "1963", "4209", "4233", "9583", "8830", "794", "795"):
    print(f"\n=== Treno {tn} ===")
    t = conn.execute(
        "SELECT origin, destination, dep_time, arr_time, table_type "
        "FROM guaranteed_trains WHERE train_number=? LIMIT 1", (tn,)
    ).fetchone()
    if t:
        print(f"  [{t['table_type']}] {t['origin']} {t['dep_time']} -> {t['destination']} {t['arr_time']}")
    stops = conn.execute(
        "SELECT sequence, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    for s in stops:
        print(f"  seq={s['sequence']:2d}  {s['station']:32s}  arr={s['arrival'] or '':5s}  dep={s['departure'] or '':5s}")
conn.close()
