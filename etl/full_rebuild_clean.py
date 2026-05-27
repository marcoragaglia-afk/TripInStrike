"""
Rebuild completo del DB con strategia finale:
1. parse_guaranteed + parse_timetable (FULL)
2. fix_stations (Ri mini -> Rimini)
3. fix dep_time (Linea suffix)
4. filter Marche + AV/IC/ICN
5. validate stops SOLO per regionali (NO per AV — i loro stop sono affidabili)
6. fix manuale 3904
"""
import sqlite3
import sys
import re
import subprocess
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"
ETL = Path(__file__).parent

TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})")


def fix_time(t):
    if not t: return None
    m = TIME_RE.match(t)
    if not m: return None
    h, mm = int(m.group(1)), m.group(2)
    if h > 23 or int(mm) > 59: return None
    return f"{h:02d}:{mm}"


def main():
    py = sys.executable
    print("Step 1: build_db.py FULL (parse + timetable)...")
    r = subprocess.run([py, str(ETL / "build_db.py")], capture_output=True, text=True, timeout=2400)
    print(r.stdout[-1000:])
    if r.returncode != 0:
        print(r.stderr); return

    print("\nStep 2: fix_stations.py...")
    r = subprocess.run([py, str(ETL / "fix_stations.py")], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr); return
    print("  OK")

    print("\nStep 3: pulizia dep_time + dedup esatto...")
    conn = sqlite3.connect(str(DB))
    rows = conn.execute("SELECT id, dep_time FROM guaranteed_trains").fetchall()
    fixed = 0
    for tid, t in rows:
        new_t = fix_time(t)
        if new_t and new_t != t:
            conn.execute("UPDATE guaranteed_trains SET dep_time=? WHERE id=?", (new_t, tid))
            fixed += 1
        elif new_t is None and t:
            conn.execute("DELETE FROM guaranteed_trains WHERE id=?", (tid,))
    # Dedup esatto
    conn.execute("""
        DELETE FROM guaranteed_trains WHERE id NOT IN (
            SELECT MIN(id) FROM guaranteed_trains
            GROUP BY train_number, origin, destination, dep_time, day_type, table_type
        )
    """)
    conn.commit()
    print(f"  dep_time fixed: {fixed}")

    print("\nStep 4: filtra Marche + AV/IC/ICN...")
    conn.close()
    r = subprocess.run([py, str(ETL / "filter_marche.py")], capture_output=True, text=True)
    print(r.stdout[-600:])

    print("\nStep 5: valida stops SOLO per regionali Marche...")
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Carica norm e station_match dalla validate_stops
    sys.path.insert(0, str(ETL))
    from validate_stops import validate_and_truncate

    regionali = conn.execute(
        "SELECT train_number, origin, destination, dep_time, arr_time FROM guaranteed_trains WHERE table_type='regionale'"
    ).fetchall()

    truncated = eliminated = unchanged = no_stops = 0
    seen_tn = set()
    for t in regionali:
        tn = t["train_number"]
        if tn in seen_tn: continue
        seen_tn.add(tn)
        srows = conn.execute(
            "SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number=? ORDER BY sequence",
            (tn,)
        ).fetchall()
        stops = [(s["sequence"], s["station"], s["arrival"], s["departure"]) for s in srows]
        if not stops:
            no_stops += 1
            continue
        cleaned = validate_and_truncate(tn, t["origin"], t["destination"], t["dep_time"], t["arr_time"], stops)
        if cleaned is None:
            conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))
            eliminated += 1
        elif len(cleaned) != len(stops):
            conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))
            for i, (seq, station, arr, dep) in enumerate(cleaned):
                conn.execute(
                    "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) VALUES (?,?,?,?,?)",
                    (tn, station, i, arr, dep)
                )
            truncated += 1
        else:
            unchanged += 1
    conn.commit()
    print(f"  Regionali: unchanged={unchanged}, truncated={truncated}, eliminated={eliminated}, no_stops={no_stops}")

    print("\nStep 6: fix manuale 3904...")
    # Trova un'entry 3904 da mantenere
    rows_3904 = conn.execute(
        "SELECT id, line FROM guaranteed_trains WHERE train_number='3904' AND table_type='regionale'"
    ).fetchall()
    if rows_3904:
        keep_id = rows_3904[0][0]
        for tid, line in rows_3904:
            if line and "Ancona" in line and "Bologna" in line:
                keep_id = tid; break
        conn.execute(
            "DELETE FROM guaranteed_trains WHERE train_number='3904' AND id != ? AND table_type='regionale'",
            (keep_id,)
        )
        conn.execute(
            "UPDATE guaranteed_trains SET destination='Bologna Centrale', arr_time='08:26' WHERE id=?",
            (keep_id,)
        )
        # Riapplica fermate del 3904
        conn.execute("DELETE FROM train_stops WHERE train_number='3904'")
        stops_3904 = [
            ("Ancona Torrette", 0, "05:50", "05:50"),
            ("Falconara Marittima", 1, "05:55", "05:55"),
            ("Senigallia", 2, "06:05", "06:05"),
            ("Marotta-Mondolfo", 3, "06:12", "06:12"),
            ("Fano", 4, "06:20", "06:20"),
            ("Pesaro", 5, "06:28", "06:28"),
            ("Cattolica S.Giovanni Gabicce", 6, "06:39", "06:39"),
            ("Riccione", 7, "06:45", "06:45"),
            ("Rimini", 8, "06:53", "06:53"),
            ("Cesena", 9, "07:09", "07:09"),
            ("Forli", 10, "07:20", "07:20"),
            ("Faenza", 11, "07:36", "07:36"),
            ("Castelbolognese-Riolo Terme", 12, "07:42", "07:42"),
            ("Imola", 13, "08:00", "08:00"),
            ("Castel S.Pietro Terme", 14, "08:09", "08:09"),
            ("Bologna Centrale", 15, "08:26", "08:26"),
        ]
        for station, seq, arr, dep in stops_3904:
            conn.execute(
                "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) VALUES (?,?,?,?,?)",
                ("3904", station, seq, arr, dep)
            )
        conn.commit()
        print(f"  3904 ripristinato con 16 fermate")

    # Statistiche finali
    print("\n" + "=" * 60)
    print("DB FINALE:")
    for r in conn.execute("SELECT table_type, day_type, COUNT(*) c FROM guaranteed_trains GROUP BY table_type, day_type"):
        print(f"  {r[0]:12s} {r[1]:10s}  {r[2]} treni")
    print(f"  Stazioni:   {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]}")
    print(f"  Fermate:    {conn.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]}")
    print(f"  Con stops:  {conn.execute('SELECT COUNT(DISTINCT train_number) FROM train_stops').fetchone()[0]}")
    print(f"  AV con stops: {conn.execute(chr(34)+chr(34)+chr(34)+'SELECT COUNT(DISTINCT t.train_number) FROM guaranteed_trains t JOIN train_stops s ON t.train_number=s.train_number WHERE t.table_type=' + chr(34) + 'tabella_a' + chr(34) + chr(34)+chr(34)+chr(34)).fetchone()[0]}")
    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
