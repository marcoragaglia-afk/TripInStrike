"""Audit treni regionali Marche."""
import sqlite3
from pathlib import Path
DB = Path(__file__).parent.parent / "db" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# Regioni disponibili
print("=== Regioni nel DB ===")
for r in conn.execute(
    "SELECT region, COUNT(*) c FROM guaranteed_trains WHERE table_type='regionale' GROUP BY region ORDER BY c DESC"
):
    print(f"  {r['c']:4d}  {r['region']!r}")

# Treni Marche (cerca con LIKE)
print("\n=== Treni MARCHE ===")
marche_rows = conn.execute(
    "SELECT train_number, origin, destination, dep_time, day_type, line FROM guaranteed_trains "
    "WHERE table_type='regionale' AND (region LIKE '%MARCHE%' OR region LIKE '%Marche%' OR region LIKE '%marche%') "
    "ORDER BY day_type, dep_time"
).fetchall()
print(f"Totale: {len(marche_rows)}")
for r in marche_rows[:30]:
    print(f"  {r['train_number']:6s}  {r['origin']:30s} -> {r['destination']:30s}  dep={r['dep_time']}  day={r['day_type']}")

# Conta tabella_a / tabella_b
print("\n=== Tabella A / B ===")
for r in conn.execute(
    "SELECT table_type, day_type, COUNT(*) c FROM guaranteed_trains WHERE table_type IN ('tabella_a','tabella_b') GROUP BY table_type, day_type"
):
    print(f"  {r['table_type']:12s} {r['day_type']:10s}  {r['c']}")

# Stazioni duplicate (per normalized_name)
print("\n=== Stazioni con nomi simili (lower) ===")
dups = conn.execute("""
    SELECT lower(name) low, GROUP_CONCAT(name, ' | ') names, COUNT(*) c
    FROM stations GROUP BY lower(name) HAVING c > 1
    ORDER BY c DESC LIMIT 20
""").fetchall()
for r in dups:
    print(f"  {r['c']}x  '{r['low']}' -> {r['names']}")

conn.close()
