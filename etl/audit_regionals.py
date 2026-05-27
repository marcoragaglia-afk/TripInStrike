"""Audit: trova regionali con dati sospetti (origin/destination/dep_time)."""
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"
conn = sqlite3.connect(str(DB_PATH))

print("=" * 70)
print("REGIONALI: statistiche generali")
print("=" * 70)
total = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
print(f"Totale treni regionali: {total}")

# Duplicati per train_number
print("\n--- Duplicati (stesso train_number, più righe) ---")
dups = conn.execute("""
    SELECT train_number, COUNT(*) c
    FROM guaranteed_trains
    WHERE table_type='regionale'
    GROUP BY train_number HAVING c > 1
    ORDER BY c DESC LIMIT 20
""").fetchall()
print(f"Numeri treno duplicati: {len(dups)}")
for tn, c in dups[:10]:
    rows = conn.execute(
        "SELECT origin, destination, dep_time, line FROM guaranteed_trains WHERE train_number=? AND table_type='regionale'",
        (tn,)
    ).fetchall()
    print(f"\n  Treno {tn} ({c} righe):")
    for r in rows:
        print(f"    {r[0]!r:30s} -> {r[1]!r:30s}  dep={r[2]}  line={r[3]!r}")

# Origini sospette (con spazi multipli, parole spezzate, numeri, ecc)
print("\n--- Origini sospette ---")
suspicious = conn.execute("""
    SELECT origin, COUNT(*) c FROM guaranteed_trains
    WHERE table_type='regionale' AND (
        origin LIKE '% % % % %'           -- troppi spazi
        OR origin GLOB '*[0-9][0-9]:[0-9][0-9]*'   -- contiene orari
        OR length(origin) > 35
        OR origin LIKE '%·%' OR origin LIKE '%CIRCOLA%' OR origin LIKE '%Servizio%'
        OR origin LIKE '%-%-%-%'
    )
    GROUP BY origin ORDER BY c DESC LIMIT 30
""").fetchall()
for o, c in suspicious:
    print(f"  {c}x  {o!r}")

# Destinazioni sospette
print("\n--- Destinazioni sospette ---")
suspicious_d = conn.execute("""
    SELECT destination, COUNT(*) c FROM guaranteed_trains
    WHERE table_type='regionale' AND (
        destination LIKE '% % % % %'
        OR destination GLOB '*[0-9][0-9]:[0-9][0-9]*'
        OR length(destination) > 35
        OR destination LIKE '%·%' OR destination LIKE '%CIRCOLA%' OR destination LIKE '%Servizio%'
        OR destination LIKE '%-%-%-%'
    )
    GROUP BY destination ORDER BY c DESC LIMIT 30
""").fetchall()
for d, c in suspicious_d:
    print(f"  {c}x  {d!r}")

# Treni con dep_time o arr_time sospetti
print("\n--- Tempi sospetti ---")
weird_times = conn.execute("""
    SELECT train_number, origin, destination, dep_time, arr_time
    FROM guaranteed_trains
    WHERE table_type='regionale'
      AND (dep_time NOT GLOB '[0-2][0-9]:[0-5][0-9]'
           OR (arr_time IS NOT NULL AND arr_time NOT GLOB '[0-2][0-9]:[0-5][0-9]'))
    LIMIT 20
""").fetchall()
for r in weird_times:
    print(f"  {r}")

conn.close()
