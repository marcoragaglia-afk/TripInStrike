"""
Ripristina manualmente le fermate dei 6 treni AV cancellati per errore.
Orari ricostruiti dal percorso AV standard Trenitalia.
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"

# Per ogni treno, lista di fermate intermedie come (sequence, station, arr, dep).
# I tempi sono basati su Trenitalia: Roma-Firenze 1h30, Firenze-Bologna 35min,
# Bologna-Milano 1h, Milano-Torino 1h, Bologna-Salerno 3h30, ecc.
TRAINS = {
    # 9508: Roma Termini 06:00 -> Torino Porta Nuova 11:05
    # Roma-Firenze 1:30, Firenze-Bologna 35min, Bologna-Milano 1h, Milano-Torino 1h
    "9508": [
        ("Firenze S.M.N.",       "07:30", "07:35"),
        ("Bologna Centrale",     "08:10", "08:15"),
        ("Reggio Emilia AV",     "08:39", "08:41"),
        ("Milano Centrale",      "09:30", "09:35"),
    ],
    # 9512: Roma Termini 07:10 -> Milano Centrale 10:50
    # via Firenze - Bologna
    "9512": [
        ("Firenze S.M.N.",       "08:40", "08:45"),
        ("Bologna Centrale",     "09:20", "09:25"),
        ("Reggio Emilia AV",     "09:49", "09:51"),
    ],
    # 9405: Venezia S.L. 07:26 -> Napoli C.le 12:48
    # via Padova - Bologna - Firenze - Roma
    "9405": [
        ("Padova",               "07:50", "07:52"),
        ("Bologna Centrale",     "08:55", "09:00"),
        ("Firenze S.M.N.",       "09:35", "09:40"),
        ("Roma Termini",         "11:05", "11:15"),
    ],
    # 9559: Torino 17:00 -> Roma Termini 21:54
    # Torino-Milano-Bologna-Firenze-Roma
    "9559": [
        ("Milano Centrale",      "18:00", "18:05"),
        ("Reggio Emilia AV",     "18:54", "18:56"),
        ("Bologna Centrale",     "19:20", "19:25"),
        ("Firenze S.M.N.",       "20:00", "20:05"),
    ],
    # 9567: Torino 19:00 -> Roma Termini 23:54
    "9567": [
        ("Milano Centrale",      "20:00", "20:05"),
        ("Reggio Emilia AV",     "20:54", "20:56"),
        ("Bologna Centrale",     "21:20", "21:25"),
        ("Firenze S.M.N.",       "22:00", "22:05"),
    ],
    # 9584: Reggio Calabria 06:33 -> Torino 18:00
    # via Salerno - Napoli - Roma - Firenze - Bologna - Milano - Torino
    "9584": [
        ("Lamezia Terme Centrale", "07:05", "07:08"),
        ("Paola",                  "07:35", "07:37"),
        ("Salerno",                "09:30", "09:35"),
        ("Napoli Centrale",        "10:15", "10:28"),
        ("Roma Termini",           "11:30", "11:45"),
        ("Firenze S.M.N.",         "13:15", "13:20"),
        ("Bologna Centrale",       "13:55", "14:00"),
        ("Milano Centrale",        "15:00", "15:05"),
    ],
}

conn = sqlite3.connect(str(DB))

for tn, stops in TRAINS.items():
    # Verifica esistenza
    row = conn.execute(
        "SELECT origin, destination, dep_time, arr_time FROM guaranteed_trains "
        "WHERE train_number=? LIMIT 1", (tn,)
    ).fetchone()
    if not row:
        print(f"  {tn}: NON IN DB, salto")
        continue

    # Pulisce eventuali fermate residue
    conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))
    # Inserisce le fermate intermedie
    for i, (st, arr, dep) in enumerate(stops):
        conn.execute(
            "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) "
            "VALUES (?, ?, ?, ?, ?)",
            (tn, st, i, arr, dep)
        )
    print(f"  {tn}: aggiunte {len(stops)} fermate ({row[0]} -> {row[1]})")

conn.commit()

# Verifica
print("\n=== Verifica ===")
for tn in TRAINS:
    n = conn.execute("SELECT COUNT(*) FROM train_stops WHERE train_number=?", (tn,)).fetchone()[0]
    print(f"  {tn}: {n} fermate")

conn.close()
print("\nFatto.")
