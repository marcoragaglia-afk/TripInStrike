"""
Fix:
1. 8814: ripara "MILAN OCENTRALE 1" -> "Milano Centrale", tempo arrivo corretto
2. Tronca fermate dei regionali oltre la loro destinazione "garantita"
3. Pulisce residui code prefix ("K Ancona Torrette" -> "Ancona Torrette", "Ovest Pesaro" -> "Pesaro")
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"


# Prefix codici PDF da rimuovere dall'inizio dei nomi stazione
CODE_PREFIX_RE = re.compile(r"^(?:K|L|E|A|F|G|T|Ovest|Est)\s+(?=[A-Z])")


def clean_station_name(s: str) -> str:
    """Rimuove residui di code prefix dall'inizio."""
    s = s.strip()
    # Rimuovi prefisso codice (K, L, E, Ovest, Est seguiti da spazio + nome stazione)
    while True:
        new = CODE_PREFIX_RE.sub("", s)
        if new == s:
            break
        s = new
    return s


def normalize_dest(s: str) -> str:
    """Forma canonica per confronto stazione."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # ── 1. Fix 8814 ──────────────────────────────────────────────────────────
    print("Step 1: fix 8814 'MILAN OCENTRALE 1'...")
    conn.execute("""
        UPDATE train_stops
        SET station='Milano Centrale', arrival='14:25', departure=NULL
        WHERE train_number='8814' AND (station LIKE 'MILAN%' OR station LIKE '%OCENTRALE%')
    """)
    print("  OK")

    # ── 2. Pulisci prefix code in tutti i nomi stazione ──────────────────────
    print("\nStep 2: pulizia prefix code (K, L, Ovest, ecc.) nei nomi stazione...")
    rows = conn.execute("SELECT id, station FROM train_stops").fetchall()
    fixed = 0
    deleted = 0
    for r in rows:
        new = clean_station_name(r["station"])
        if new != r["station"]:
            if not new or len(new) < 3:
                conn.execute("DELETE FROM train_stops WHERE id=?", (r["id"],))
                deleted += 1
            else:
                try:
                    conn.execute("UPDATE train_stops SET station=? WHERE id=?", (new, r["id"]))
                    fixed += 1
                except sqlite3.IntegrityError:
                    pass
    print(f"  prefix corretti: {fixed}, eliminati: {deleted}")

    # ── 3. Tronca fermate dei regionali oltre la destinazione "garantita" ───
    print("\nStep 3: troncamento fermate oltre destinazione garantita...")
    trains = conn.execute("""
        SELECT id, train_number, origin, destination
        FROM guaranteed_trains
        WHERE table_type='regionale'
    """).fetchall()

    truncated_count = 0
    for t in trains:
        tn = t["train_number"]
        dest_norm = normalize_dest(t["destination"])
        # Cerca la destinazione nelle fermate
        stops = conn.execute(
            "SELECT id, sequence, station FROM train_stops WHERE train_number=? ORDER BY sequence",
            (tn,)
        ).fetchall()
        if not stops:
            continue

        dest_idx = -1
        for i, s in enumerate(stops):
            if normalize_dest(s["station"]) == dest_norm or dest_norm in normalize_dest(s["station"]):
                dest_idx = i
                break

        if dest_idx == -1:
            continue  # destinazione non trovata, lascia stare

        # Elimina fermate dopo dest_idx
        to_remove = [s["id"] for s in stops[dest_idx + 1:]]
        if to_remove:
            for sid in to_remove:
                conn.execute("DELETE FROM train_stops WHERE id=?", (sid,))
            truncated_count += 1

    print(f"  Treni con fermate troncate: {truncated_count}")

    # ── 4. Stesso per tabella_a/tabella_b (8814 etc) ────────────────────────
    print("\nStep 4: troncamento fermate AV oltre destinazione...")
    trains_av = conn.execute("""
        SELECT id, train_number, origin, destination
        FROM guaranteed_trains
        WHERE table_type IN ('tabella_a', 'tabella_b')
    """).fetchall()

    av_truncated = 0
    for t in trains_av:
        tn = t["train_number"]
        dest_norm = normalize_dest(t["destination"])
        stops = conn.execute(
            "SELECT id, sequence, station FROM train_stops WHERE train_number=? ORDER BY sequence",
            (tn,)
        ).fetchall()
        if not stops:
            continue
        dest_idx = -1
        for i, s in enumerate(stops):
            sn = normalize_dest(s["station"])
            if sn == dest_norm or (len(dest_norm) >= 6 and dest_norm in sn):
                dest_idx = i
                break
        if dest_idx == -1:
            continue
        # Tronca dopo destinazione
        to_remove = [s["id"] for s in stops[dest_idx + 1:]]
        if to_remove:
            for sid in to_remove:
                conn.execute("DELETE FROM train_stops WHERE id=?", (sid,))
            av_truncated += 1
    print(f"  AV con fermate troncate: {av_truncated}")

    # ── 5. Ri-numera sequence di tutti i treni modificati ───────────────────
    print("\nStep 5: ri-numera sequence...")
    train_nums = [r[0] for r in conn.execute("SELECT DISTINCT train_number FROM train_stops").fetchall()]
    for tn in train_nums:
        stops = conn.execute(
            "SELECT id FROM train_stops WHERE train_number=? ORDER BY sequence", (tn,)
        ).fetchall()
        # Step 1: sequence temporanee uniche negative
        for s in stops:
            conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (-s[0], s[0]))
        # Step 2: sequence finali
        for i, s in enumerate(stops):
            conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (i, s[0]))

    conn.commit()

    # ── Verifica finali ──────────────────────────────────────────────────────
    for tn in ("8814", "3904", "3906", "3908", "3930"):
        print(f"\n=== Verifica {tn} ===")
        t = conn.execute(
            "SELECT origin, destination, dep_time, arr_time, table_type FROM guaranteed_trains WHERE train_number=? LIMIT 1",
            (tn,)
        ).fetchone()
        if not t:
            print("  NON IN DB")
            continue
        print(f"  [{t['table_type']}] {t['origin']} {t['dep_time']} -> {t['destination']} {t['arr_time']}")
        for r in conn.execute(
            "SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number=? ORDER BY sequence",
            (tn,)
        ):
            print(f"  seq={r['sequence']:2d}  {r['station']:30s}  arr={r['arrival'] or '':5s}  dep={r['departure'] or '':5s}")

    conn.close()


if __name__ == "__main__":
    main()
