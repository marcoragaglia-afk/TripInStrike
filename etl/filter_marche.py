"""
Filtraggio drastico:
1. Mantiene TUTTI i treni tabella_a (AV/IC/ICN feriali+festivi) e tabella_b
2. Per i regionali: mantiene SOLO quelli che operano in territorio Marche
   (origine O destinazione coincide con una stazione marchigiana, oppure
   region='MARCHE')
3. Pulisce duplicati stazione (uppercase/lowercase variants).
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Stazioni Marche principali (forme normalizzate)
MARCHE_KEYWORDS = {
    "ancona", "falconara", "senigallia", "marotta", "fano", "pesaro",
    "civitanova", "macerata", "tolentino", "camerino", "porto recanati",
    "fabriano", "jesi", "chiaravalle", "albacina", "matelica",
    "ascoli piceno", "san benedetto", "s. benedetto", "s.benedetto",
    "grottammare", "porto d'ascoli", "cupra marittima", "pedaso",
    "loreto", "recanati", "osimo", "ancona torrette",
    "fermo", "porto san giorgio", "porto sant'elpidio", "campofilone",
    "monte san vito", "montecosaro",
}


def is_marche_station(name: str) -> bool:
    """True se la stazione è marchigiana."""
    if not name:
        return False
    n = name.lower().strip()
    n = re.sub(r"[._]", " ", n)
    n = re.sub(r"\s+", " ", n)
    for kw in MARCHE_KEYWORDS:
        if kw in n:
            return True
    return False


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FILTRAGGIO MARCHE + AV/IC/ICN")
    print("=" * 70)

    # Step 1: identifica i regionali Marche
    marche_ids: set[int] = set()
    rows = conn.execute(
        "SELECT id, train_number, origin, destination, region FROM guaranteed_trains "
        "WHERE table_type='regionale'"
    ).fetchall()
    for r in rows:
        if r["region"] and "MARCHE" in r["region"].upper():
            marche_ids.add(r["id"])
            continue
        if is_marche_station(r["origin"]) or is_marche_station(r["destination"]):
            marche_ids.add(r["id"])

    print(f"\nRegionali Marche identificati: {len(marche_ids)}")

    # Step 2: cancella tutti gli altri regionali
    n_reg_before = conn.execute(
        "SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'"
    ).fetchone()[0]

    if marche_ids:
        placeholders = ",".join("?" * len(marche_ids))
        conn.execute(
            f"DELETE FROM guaranteed_trains WHERE table_type='regionale' "
            f"AND id NOT IN ({placeholders})",
            list(marche_ids)
        )
    else:
        conn.execute("DELETE FROM guaranteed_trains WHERE table_type='regionale'")

    n_reg_after = conn.execute(
        "SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'"
    ).fetchone()[0]
    print(f"Regionali eliminati: {n_reg_before - n_reg_after} (rimangono {n_reg_after})")

    # Step 3: cancella le fermate dei treni non più presenti
    n_stops_before = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    conn.execute("""
        DELETE FROM train_stops
        WHERE train_number NOT IN (SELECT DISTINCT train_number FROM guaranteed_trains)
    """)
    n_stops_after = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    print(f"Fermate orfane eliminate: {n_stops_before - n_stops_after} (rimangono {n_stops_after})")

    # Step 4: pulizia stazioni duplicate (lower-case merge)
    print("\n--- Pulizia stazioni duplicate ---")
    # Trova gruppi di stazioni con stesso lower(name)
    dup_groups = conn.execute("""
        SELECT lower(name) low, GROUP_CONCAT(name, '|') names
        FROM stations
        GROUP BY lower(name)
        HAVING COUNT(*) > 1
    """).fetchall()

    merged = 0
    for grp in dup_groups:
        names = grp["names"].split("|")
        # Canonico: preferisce quello con maiuscole/minuscole miste (non tutto MAIUSCOLO)
        canonical = sorted(names, key=lambda s: (s == s.upper(), len(s)))[0]
        for n in names:
            if n == canonical:
                continue
            # Aggiorna riferimenti in guaranteed_trains e train_stops
            conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (canonical, n))
            conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (canonical, n))
            conn.execute("UPDATE train_stops SET station=? WHERE station=?", (canonical, n))
            conn.execute("DELETE FROM stations WHERE name=?", (n,))
            merged += 1
    print(f"Stazioni duplicate fuse: {merged}")

    # Step 5: rimuovi stazioni orfane (non usate da nessun treno)
    conn.execute("""
        DELETE FROM stations
        WHERE name NOT IN (SELECT origin FROM guaranteed_trains)
          AND name NOT IN (SELECT destination FROM guaranteed_trains)
          AND name NOT IN (SELECT station FROM train_stops)
    """)

    conn.commit()

    # Statistiche finali
    print("\n" + "=" * 70)
    print("STATO FINALE DB:")
    print("=" * 70)
    for r in conn.execute(
        "SELECT table_type, day_type, COUNT(*) c FROM guaranteed_trains GROUP BY table_type, day_type ORDER BY table_type, day_type"
    ):
        print(f"  {r['table_type']:12s} {r['day_type']:10s}  {r['c']} treni")
    print(f"\n  Stazioni totali:   {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]}")
    print(f"  Fermate:           {conn.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]}")
    print(f"  Treni con fermate: {conn.execute('SELECT COUNT(DISTINCT train_number) FROM train_stops').fetchone()[0]}")

    # Quanti Marche hanno fermate vs no
    n_marche = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
    n_marche_with_stops = conn.execute("""
        SELECT COUNT(DISTINCT train_number) FROM train_stops
        WHERE train_number IN (SELECT train_number FROM guaranteed_trains WHERE table_type='regionale')
    """).fetchone()[0]
    print(f"\n  Marche con fermate: {n_marche_with_stops}/{n_marche}")
    print(f"  Marche SENZA fermate: {n_marche - n_marche_with_stops}")

    print("\n--- Marche SENZA fermate (TODO: aggiungere a mano) ---")
    no_stops = conn.execute("""
        SELECT train_number, origin, destination, dep_time, day_type
        FROM guaranteed_trains
        WHERE table_type='regionale'
          AND train_number NOT IN (SELECT DISTINCT train_number FROM train_stops)
        ORDER BY day_type, dep_time
    """).fetchall()
    for r in no_stops[:50]:
        print(f"  {r['train_number']:6s}  {r['origin']:25s} -> {r['destination']:25s}  dep={r['dep_time']}  ({r['day_type']})")
    if len(no_stops) > 50:
        print(f"  ... e altri {len(no_stops) - 50}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
