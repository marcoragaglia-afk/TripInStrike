"""
ETL pipeline principale: esegue tutti i parser e popola il database SQLite.

Uso:
  python build_db.py [--skip-timetable] [--db PATH]

Opzioni:
  --skip-timetable  Salta il parsing dell'orario completo (più veloce)
  --db PATH         Percorso del database SQLite (default: ../db/sciopero.db)
"""

import argparse
import sqlite3
import re
import sys
from pathlib import Path

# Assicura che etl/ sia nel path
sys.path.insert(0, str(Path(__file__).parent))

from parse_guaranteed import parse_all, GuaranteedTrain
from parse_timetable import parse_timetable, TrainStop

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"
DB_DEFAULT = Path(__file__).parent.parent / "db" / "sciopero.db"


def normalize_station_name(name: str) -> str:
    """Normalizza nome stazione per ricerche fuzzy."""
    n = name.upper().strip()
    n = re.sub(r"\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?", "SANTA MARIA NOVELLA", n)
    for pat in [r"\bCENTRALE\b", r"\bC\.LE\b", r"\bCLE\b", r"\bCENTR\b"]:
        n = re.sub(pat, "CENTRALE", n)
    n = re.sub(r"\bP\.NUOVA\b|\bPN\b|\bP\.N\.\b", "PORTA NUOVA", n)
    n = re.sub(r"\bP\.GARIBALDI\b", "PORTA GARIBALDI", n)
    n = re.sub(r"\bSTA\.?\s*LUCIA\b|\bS\.LUCIA\b", "SANTA LUCIA", n)
    n = re.sub(r"\bS\.\s*", "SAN ", n)
    n = re.sub(r"\bD\.T\.?\b", "DEL TRONTO", n)
    n = re.sub(r"['\-]", " ", n)
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def build_db(trains: list[GuaranteedTrain],
             stops_map: dict[str, list[TrainStop]],
             db_path: Path) -> None:
    """Crea e popola il database SQLite."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Rimuovi db esistente
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_PATH.read_text())

    # ── Stazioni ─────────────────────────────────────────────────────────────
    station_set: set[str] = set()
    for t in trains:
        station_set.add(t.origin)
        station_set.add(t.destination)
    for stops in stops_map.values():
        for s in stops:
            station_set.add(s.station)

    station_set.discard("")
    station_rows = [(s, normalize_station_name(s)) for s in sorted(station_set)]
    conn.executemany(
        "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?,?)",
        station_rows
    )

    # ── Treni garantiti ───────────────────────────────────────────────────────
    train_rows = [
        (
            t.train_number, t.category or None, t.origin, t.destination,
            t.dep_time or None, t.arr_time or None,
            t.day_type, t.table_type,
            t.region or None, t.line or None,
            t.notes or None, t.validity or None,
        )
        for t in trains if t.train_number and t.origin and t.destination
    ]
    conn.executemany(
        """INSERT INTO guaranteed_trains
           (train_number, category, origin, destination, dep_time, arr_time,
            day_type, table_type, region, line, notes, validity)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        train_rows
    )

    # ── Fermate ───────────────────────────────────────────────────────────────
    stop_rows = []
    for train_num, stops in stops_map.items():
        for s in stops:
            stop_rows.append((
                s.train_number, s.station, s.sequence,
                s.arrival or None, s.departure or None,
            ))
    if stop_rows:
        conn.executemany(
            """INSERT OR IGNORE INTO train_stops
               (train_number, station, sequence, arrival, departure)
               VALUES (?,?,?,?,?)""",
            stop_rows
        )

    conn.commit()
    conn.close()

    print(f"\nDatabase creato: {db_path}")
    print(f"  Stazioni:        {len(station_rows)}")
    print(f"  Treni garantiti: {len(train_rows)}")
    print(f"  Fermate:         {len(stop_rows)}")


def main():
    parser = argparse.ArgumentParser(description="Build Sciopero Treni database")
    parser.add_argument("--skip-timetable", action="store_true",
                        help="Salta parsing orario completo")
    parser.add_argument("--db", default=str(DB_DEFAULT),
                        help="Percorso database SQLite")
    args = parser.parse_args()

    db_path = Path(args.db)

    # Step 1: parse treni garantiti
    print("=" * 60)
    print("STEP 1: Parsing treni garantiti")
    print("=" * 60)
    trains = parse_all()

    # Step 2: parsing orario completo
    stops_map: dict[str, list] = {}
    if not args.skip_timetable:
        print("\n" + "=" * 60)
        print("STEP 2: Parsing orario completo (fermate intermedie)")
        print("=" * 60)
        target_nums = {t.train_number for t in trains}
        stops_map = parse_timetable(target_nums)
    else:
        print("\nSkip: parsing orario completo")

    # Step 3: build database
    print("\n" + "=" * 60)
    print("STEP 3: Costruzione database")
    print("=" * 60)
    build_db(trains, stops_map, db_path)

    print("\nDone!")


if __name__ == "__main__":
    main()
