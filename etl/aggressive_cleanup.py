"""
Pulizia aggressiva finale: elimina junk evidente, fonde residui Civitanova/etc.
"""
import sqlite3
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Stazioni da ELIMINARE completamente (junk PDF)
DELETE_STATIONS = re.compile(
    r"consultarehttps"
    r"|^Milano-Torino"
    r"|^Sicilia/"
    r"|^Venezia -Milano"
    r"|^Roma Terminid$"
    r"|Tiburtina a$"
    r"|d`Ascoli-S\.Benedetto"
    r"|^MILANO P\.GARIBALDI$"  # variante di Milano Porta Garibaldi
    r"|Garibaldia$"  # trailing 'a'
    , re.I
)

# Trailing 'a' o caratteri sospetti alla fine
def remove_trailing_junk(s: str) -> str:
    s = s.strip()
    # rimuovi trailing 'a', 'd', 'q', 'q.', singoli
    s = re.sub(r"\s+[adq]\.?$", "", s)
    # rimuovi numeri appiccicati
    s = re.sub(r"(\b[A-Za-z]+)\d+\b", r"\1", s)
    return s.strip()


# Alias aggiuntivi
EXTRA_ALIASES = {
    "Civitanova- M. Montegr": "Civitanova-M.Montegr.",
    "Civitanova M.- Montegr.": "Civitanova-M.Montegr.",
    "Milano P.G.": "Milano Porta Garibaldi",
    "Milano P.Garibaldi": "Milano Porta Garibaldi",
    "Roma Terminid": "Roma Termini",
    "Roma Tiburtina a": "Roma Tiburtina",
    "MILANO P.GARIBALDI": "Milano Porta Garibaldi",
    "Milano Porta Garibaldia": "Milano Porta Garibaldi",
}


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    print("Step 1: eliminazione stazioni junk evidenti...")
    rows = conn.execute("SELECT name FROM stations").fetchall()
    deleted = 0
    for (name,) in rows:
        if DELETE_STATIONS.search(name):
            # Rimuovi anche i treni/fermate che la usano
            conn.execute("DELETE FROM guaranteed_trains WHERE origin=? OR destination=?", (name, name))
            conn.execute("DELETE FROM train_stops WHERE station=?", (name,))
            conn.execute("DELETE FROM stations WHERE name=?", (name,))
            deleted += 1
            print(f"  ELIMINATA: '{name}'")
    print(f"  Totale eliminate: {deleted}")

    print("\nStep 2: applica alias extra...")
    applied = 0
    for old, new in EXTRA_ALIASES.items():
        c1 = conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old)).rowcount
        c2 = conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old)).rowcount
        c3 = conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old)).rowcount
        if c1+c2+c3 > 0:
            applied += 1
            print(f"  '{old}' -> '{new}'")

    print("\nStep 3: rimozione trailing junk...")
    fix = 0
    for table, col in [("guaranteed_trains", "origin"), ("guaranteed_trains", "destination"), ("train_stops", "station")]:
        rows = conn.execute(f"SELECT rowid AS rid, {col} AS v FROM {table}").fetchall()
        for r in rows:
            new = remove_trailing_junk(r["v"])
            if new and new != r["v"]:
                try:
                    conn.execute(f"UPDATE {table} SET {col}=? WHERE rowid=?", (new, r["rid"]))
                    fix += 1
                except sqlite3.IntegrityError:
                    pass
    print(f"  rimossi trailing junk: {fix}")

    print("\nStep 4: ricostruisci stations + dedup...")
    conn.execute("DELETE FROM stations")
    names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n and n.strip(): names.add(n.strip())
    for n in sorted(names):
        conn.execute("INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                     (n, normalize_station_name(n)))

    conn.execute("""
        DELETE FROM guaranteed_trains WHERE id NOT IN (
            SELECT MIN(id) FROM guaranteed_trains
            GROUP BY train_number, origin, destination, dep_time, day_type, table_type
        )
    """)
    conn.commit()

    print("\n=== Stazioni finali principali ===")
    for kw in ["pescara", "ancona", "verona", "foggia", "civitanova", "vasto", "milano", "roma", "bologna", "termoli", "sulmona", "teramo"]:
        names = [r[0] for r in conn.execute(f"SELECT name FROM stations WHERE lower(name) LIKE '%{kw}%' ORDER BY name")]
        print(f"  {kw:12s}: {names}")

    n_st = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    n_tr = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    print(f"\nStazioni: {n_st}, Treni: {n_tr}")

    conn.close()


if __name__ == "__main__":
    main()
