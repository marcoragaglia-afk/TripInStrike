"""Corregge il treno 3904 nel database."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"

conn = sqlite3.connect(str(DB_PATH))

# 1. Rimuovi il duplicato errato (ID 548, linea TTPER - non pertinente)
conn.execute("DELETE FROM guaranteed_trains WHERE id=548")

# 2. Destinazione: solo fino a Bologna Centrale (il resto non è garantito)
conn.execute("UPDATE guaranteed_trains SET destination='Bologna Centrale', arr_time='08:26' WHERE id=1525")

# 3. Rimuovi fermate contaminate dal PDF
conn.execute("DELETE FROM train_stops WHERE train_number='3904'")

# 4. Inserisci le fermate corrette (da screenshot Trenitalia)
stops = [
    ("3904", "Ancona Torrette",              0,  "05:50", "05:50"),
    ("3904", "Falconara Marittima",          1,  "05:55", "05:55"),
    ("3904", "Senigallia",                   2,  "06:05", "06:05"),
    ("3904", "Marotta-Mondolfo",             3,  "06:12", "06:12"),
    ("3904", "Fano",                         4,  "06:20", "06:20"),
    ("3904", "Pesaro",                       5,  "06:28", "06:28"),
    ("3904", "Cattolica S.Giovanni Gabicce", 6,  "06:39", "06:39"),
    ("3904", "Riccione",                     7,  "06:45", "06:45"),
    ("3904", "Rimini",                       8,  "06:53", "06:53"),
    ("3904", "Cesena",                       9,  "07:09", "07:09"),
    ("3904", "Forli",                       10,  "07:20", "07:20"),
    ("3904", "Faenza",                      11,  "07:36", "07:36"),
    ("3904", "Castelbolognese-Riolo Terme", 12,  "07:42", "07:42"),
    ("3904", "Imola",                       13,  "08:00", "08:00"),
    ("3904", "Castel S.Pietro Terme",       14,  "08:09", "08:09"),
    ("3904", "Bologna Centrale",            15,  "08:26", "08:26"),
    # Bologna Centrale è la destinazione garantita — fermate successive non incluse
]
conn.executemany(
    "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) VALUES (?,?,?,?,?)",
    stops,
)

conn.commit()

# Verifica
print("Treno aggiornato:")
r = conn.execute("SELECT * FROM guaranteed_trains WHERE train_number='3904'").fetchone()
print(r)
count = conn.execute("SELECT COUNT(*) FROM train_stops WHERE train_number='3904'").fetchone()[0]
print(f"\nFermate ({count}):")
for s in conn.execute(
    "SELECT station, arrival, departure FROM train_stops WHERE train_number='3904' ORDER BY sequence"
):
    print(f"  {s[0]:35s}  arr={s[1] or '':5s}  dep={s[2] or '':5s}")
conn.close()
print("\nFatto.")
