"""
Ripristino DB:
1. Salva le fermate validate (train_stops) in memoria
2. Rebuild guaranteed_trains da PDF (skip timetable)
3. Ripristina le fermate validate
4. Pulisce solo dep_time (NO dedup)
5. Riapplica fix manuale 3904
"""
import sqlite3
import re
import sys
import subprocess
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"

TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})")

def fix_time(t: str) -> str | None:
    if not t:
        return None
    m = TIME_RE.match(t)
    if not m:
        return None
    h, mm = int(m.group(1)), m.group(2)
    if h > 23 or int(mm) > 59:
        return None
    return f"{h:02d}:{mm}"


def main():
    # Step 1: backup train_stops in memoria
    print("Step 1: backup fermate validate...")
    conn = sqlite3.connect(str(DB_PATH))
    stops_backup = conn.execute(
        "SELECT train_number, station, sequence, arrival, departure FROM train_stops"
    ).fetchall()
    print(f"  Salvate {len(stops_backup)} fermate validate")
    conn.close()

    # Step 2: rebuild guaranteed_trains via build_db.py --skip-timetable
    print("\nStep 2: rebuild guaranteed_trains (skip timetable)...")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "build_db.py"), "--skip-timetable"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERRORE build_db:")
        print(result.stdout)
        print(result.stderr)
        return
    print(result.stdout[-500:])

    # Step 3: ripristina fermate validate
    print("\nStep 3: ripristino fermate validate...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.executemany(
        "INSERT OR IGNORE INTO train_stops(train_number, station, sequence, arrival, departure) "
        "VALUES (?, ?, ?, ?, ?)",
        stops_backup
    )
    conn.commit()
    n_stops = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    print(f"  Fermate ripristinate: {n_stops}")

    # Step 4: pulisci dep_time (senza dedup)
    print("\nStep 4: pulizia dep_time (rimuove suffissi 'Linea')...")
    rows = conn.execute(
        "SELECT id, dep_time FROM guaranteed_trains WHERE table_type='regionale'"
    ).fetchall()
    fixed = 0
    deleted = 0
    for tid, t in rows:
        new_t = fix_time(t)
        if new_t is None:
            conn.execute("DELETE FROM guaranteed_trains WHERE id=?", (tid,))
            deleted += 1
        elif new_t != t:
            conn.execute("UPDATE guaranteed_trains SET dep_time=? WHERE id=?", (new_t, tid))
            fixed += 1
    print(f"  dep_time corretti: {fixed}, eliminati per orario invalido: {deleted}")

    # Aggiungi stazioni delle fermate alla tabella stations (nel caso mancassero)
    print("\nStep 5: aggiunta stazioni mancanti...")
    seen = {r[0] for r in conn.execute("SELECT name FROM stations").fetchall()}
    added = 0
    from build_db import normalize_station_name
    for tn, station, seq, arr, dep in stops_backup:
        if station not in seen and station.strip():
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                    (station, normalize_station_name(station))
                )
                seen.add(station)
                added += 1
            except Exception:
                pass
    print(f"  Stazioni aggiunte: {added}")

    # Step 6: riapplica fix 3904
    print("\nStep 6: fix manuale 3904...")
    # 3904 ha duplicati post-rebuild: tieni quello giusto
    rows_3904 = conn.execute(
        "SELECT id, line FROM guaranteed_trains WHERE train_number='3904' AND table_type='regionale'"
    ).fetchall()
    keep_id = None
    for tid, line in rows_3904:
        if line and "Ancona" in line and "Bologna" in line:
            keep_id = tid
            break
    if keep_id:
        conn.execute(
            "DELETE FROM guaranteed_trains WHERE train_number='3904' AND id != ? AND table_type='regionale'",
            (keep_id,)
        )
        conn.execute(
            "UPDATE guaranteed_trains SET destination='Bologna Centrale', arr_time='08:26' WHERE id=?",
            (keep_id,)
        )
        # 3904 stops sono già nel backup ripristinato
        print(f"  Treno 3904 normalizzato (id={keep_id})")

    conn.commit()

    # Statistiche finali
    total_trains = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    total_regionali = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
    total_stops = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    trains_with_stops = conn.execute("SELECT COUNT(DISTINCT train_number) FROM train_stops").fetchone()[0]
    print(f"\n{'=' * 60}")
    print(f"DB finale:")
    print(f"  Treni totali:           {total_trains}")
    print(f"  Treni regionali:        {total_regionali}")
    print(f"  Fermate validate:       {total_stops}")
    print(f"  Treni con fermate:      {trains_with_stops}")
    print(f"{'=' * 60}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
