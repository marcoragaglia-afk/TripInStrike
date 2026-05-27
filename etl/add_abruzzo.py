"""
Aggiunge i regionali Abruzzo (linea Adriatica + linea Pescara-Roma via Sulmona).
Riparsa dai PDF originali e aggiunge solo quelli abruzzesi (con stesso criterio Marche).
"""
import sqlite3
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_guaranteed import parse_all
from clean_all_stations import clean_station_name, canonical_name
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Stazioni abruzzesi principali
ABRUZZO_KEYWORDS = {
    "pescara", "chieti", "sulmona", "l'aquila", "teramo", "giulianova",
    "roseto", "atri", "silvi", "montesilvano", "francavilla", "ortona",
    "vasto", "san salvo", "lanciano", "pratola", "popoli", "tagliacozzo",
    "avezzano", "carsoli", "termoli", "alba adriatica",
    "porto d'ascoli",  # confine
}


def is_abruzzo_station(name: str) -> bool:
    if not name:
        return False
    n = name.lower().strip()
    for kw in ABRUZZO_KEYWORDS:
        if kw in n:
            return True
    return False


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Re-parse PDF
    print("Re-parsing PDF treni garantiti...")
    all_trains = parse_all()
    print(f"  Parsati {len(all_trains)} treni totali")

    # Filtra regionali Abruzzo
    abruzzo_trains = []
    for t in all_trains:
        if t.table_type != "regionale":
            continue
        if (t.region and "ABRUZZO" in t.region.upper()) or \
           is_abruzzo_station(t.origin) or is_abruzzo_station(t.destination):
            abruzzo_trains.append(t)
    print(f"  Abruzzo identificati: {len(abruzzo_trains)}")

    # Trova le entry già in DB (per non duplicare)
    existing = set()
    for r in conn.execute("SELECT train_number, origin, destination, dep_time, day_type FROM guaranteed_trains"):
        existing.add((r["train_number"], r["origin"], r["destination"], r["dep_time"], r["day_type"]))

    added = 0
    for t in abruzzo_trains:
        if not t.dep_time:
            continue
        # Pulisci origin/destination
        no = clean_station_name(t.origin)
        nd = clean_station_name(t.destination)
        if not no or not nd:
            continue
        # Normalizza dep_time
        m = re.match(r"^(\d{1,2})[:.](\d{2})", t.dep_time)
        if not m:
            continue
        h, mm = int(m.group(1)), m.group(2)
        if h > 23 or int(mm) > 59:
            continue
        dep_time = f"{h:02d}:{mm}"

        key = (t.train_number, no, nd, dep_time, t.day_type)
        if key in existing:
            continue
        existing.add(key)
        conn.execute("""
            INSERT INTO guaranteed_trains
            (train_number, category, origin, destination, dep_time, arr_time,
             day_type, table_type, region, line, notes, validity)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t.train_number, t.category or None, no, nd,
            dep_time, t.arr_time or None,
            t.day_type, t.table_type,
            t.region or None, t.line or None,
            t.notes or None, t.validity or None,
        ))
        added += 1
    print(f"  Inseriti: {added}")

    # Aggiungi le stazioni Abruzzo a stations
    new_stations = set()
    for (st,) in conn.execute("SELECT DISTINCT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains"):
        if st and st.strip():
            new_stations.add(st.strip())
    existing_stations = {r[0] for r in conn.execute("SELECT name FROM stations").fetchall()}
    for n in sorted(new_stations - existing_stations):
        conn.execute(
            "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
            (n, normalize_station_name(n))
        )

    # Dedup esatto
    conn.execute("""
        DELETE FROM guaranteed_trains WHERE id NOT IN (
            SELECT MIN(id) FROM guaranteed_trains
            GROUP BY train_number, origin, destination, dep_time, day_type, table_type
        )
    """)

    conn.commit()
    n_reg = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
    n_tot = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    n_st = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"\nDB finale: {n_tot} treni ({n_reg} regionali), {n_st} stazioni")

    # Mostra Pescara/Vasto trains
    print("\n=== Treni con Pescara o Vasto ===")
    for r in conn.execute("""
        SELECT train_number, origin, destination, dep_time, day_type
        FROM guaranteed_trains
        WHERE table_type='regionale'
          AND (origin LIKE '%Pescara%' OR destination LIKE '%Pescara%'
            OR origin LIKE '%Vasto%' OR destination LIKE '%Vasto%')
        ORDER BY dep_time LIMIT 30
    """):
        print(f"  {r[0]:6s}  {r[1]:25s} -> {r[2]:25s}  dep={r[3]}  ({r[4]})")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
