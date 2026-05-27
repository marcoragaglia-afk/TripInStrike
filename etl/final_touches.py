"""Aggiunge stazioni dalle fermate e verifica rotte mancanti."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"
conn = sqlite3.connect(str(DB))

# Aggiungi stazioni dalle fermate
seen = {r[0] for r in conn.execute("SELECT name FROM stations").fetchall()}
added = 0
for (st,) in conn.execute("SELECT DISTINCT station FROM train_stops").fetchall():
    if st and st not in seen:
        conn.execute(
            "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
            (st, normalize_station_name(st))
        )
        seen.add(st)
        added += 1
conn.commit()
n = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
print(f"Stazioni aggiunte: {added}, totale: {n}")

# Verifica AV passanti per Foggia / Pescara
print("\n=== Treni con Foggia (origine/dest/fermate) ===")
trains_with_foggia = conn.execute("""
    SELECT DISTINCT t.train_number, t.origin, t.destination, t.dep_time
    FROM guaranteed_trains t
    LEFT JOIN train_stops s ON t.train_number = s.train_number
    WHERE t.table_type IN ('tabella_a', 'tabella_b')
      AND (t.origin LIKE '%FOGGIA%' OR t.destination LIKE '%FOGGIA%' OR s.station LIKE '%FOGGIA%')
    ORDER BY t.dep_time LIMIT 20
""").fetchall()
for r in trains_with_foggia:
    print(f"  {r[0]:6s}  {r[1]:25s} -> {r[2]:25s}  dep={r[3]}")

print("\n=== Treni con Pescara (origine/dest/fermate) ===")
trains_with_pescara = conn.execute("""
    SELECT DISTINCT t.train_number, t.origin, t.destination, t.dep_time, t.table_type
    FROM guaranteed_trains t
    LEFT JOIN train_stops s ON t.train_number = s.train_number
    WHERE t.table_type IN ('tabella_a', 'tabella_b')
      AND (t.origin LIKE '%PESCARA%' OR t.destination LIKE '%PESCARA%' OR s.station LIKE '%PESCARA%' OR s.station LIKE '%Pescara%')
    ORDER BY t.dep_time LIMIT 20
""").fetchall()
for r in trains_with_pescara:
    print(f"  {r[0]:6s}  [{r[4]}] {r[1]:25s} -> {r[2]:25s}  dep={r[3]}")

# Fermate del 8315 (Roma -> Lecce, dovrebbe passare per Foggia)
print("\n=== Fermate del 8315 (Roma->Lecce) ===")
for r in conn.execute("SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number='8315' ORDER BY sequence"):
    print(f"  seq={r[0]:2d}  {r[1]:30s}  arr={r[2] or '':5s}  dep={r[3] or '':5s}")

conn.close()
