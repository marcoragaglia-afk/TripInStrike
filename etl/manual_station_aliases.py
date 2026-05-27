"""
Fonde stazioni note con varianti diverse (Pescara/Pescara Centrale, ecc.)
"""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# alias -> canonico
ALIASES = {
    "Pescara": "Pescara Centrale",
    "S. Benedetto": "S. Benedetto d.T",
    "Ascoli": "Ascoli Piceno",
    "Civitanova": "Civitanova-M.Montegr.",
    "Civitanova- M. Montegr.": "Civitanova-M.Montegr.",
    "Civitanova M.- Montegr.": "Civitanova-M.Montegr.",
    "CIVITANOVA M.- MONTEGR.": "Civitanova-M.Montegr.",
    "S. BENEDETTO D. T": "S. Benedetto d.T",
    "S. Benedetto d.T.": "S. Benedetto d.T",
    "Castelplanio-Cupra": "Castelplanio-Cupra m.",
    "Castelplanio-Cupra m.": "Castelplanio-Cupra m.",
    "Bologna": "Bologna Centrale",
    "BOLOGNA": "Bologna Centrale",
    "BOLOGNA C.LE": "Bologna Centrale",
    "Bologna C.le": "Bologna Centrale",
    "BOLOGNA CENTRALE": "Bologna Centrale",
    "ANCONA": "Ancona",
    "ROMA TERMINI": "Roma Termini",
    "MILANO CENTRALE": "Milano Centrale",
    "NAPOLI CENTRALE": "Napoli Centrale",
    "BARI CENTRALE": "Bari Centrale",
    "FIRENZE S.M.N.": "Firenze S.M.N.",
    "TORINO PORTA NUOVA": "Torino Porta Nuova",
    "VENEZIA SANTA LUCIA": "Venezia Santa Lucia",
    "Venezia S.Lucia": "Venezia Santa Lucia",
    "VENEZIA S.LUCIA": "Venezia Santa Lucia",
    "Venezia S. Lucia": "Venezia Santa Lucia",
    "SALERNO": "Salerno",
    "LECCE": "Lecce",
    "FOGGIA": "Foggia",
    "REGGIO CALABRIA CENTRALE": "Reggio Calabria Centrale",
    "DI CALABRIA CENTRALE": "Reggio Calabria Centrale",
    "REGGIO DI CALABRIA CENTRALE": "Reggio Calabria Centrale",
    "Reggio Cal.": "Reggio Calabria Centrale",
    "Verona P.N": "Verona P.N.",
    "VERONA P.NUOVA": "Verona P.N.",
    "VERONA PORTA NUOVA": "Verona P.N.",
    "PESCARA": "Pescara Centrale",
    "Roma Tibur.": "Roma Tiburtina",
    "ROMA TIBURTINA": "Roma Tiburtina",
    "Vasto-S. Salvo": "Vasto-San Salvo",
    "Vasto- S.Salvo": "Vasto-San Salvo",
    "Vasto-S.Salvo": "Vasto-San Salvo",
}


def main():
    conn = sqlite3.connect(str(DB))
    print("Applico alias manuali...")

    applied = 0
    for old, new in ALIASES.items():
        c1 = conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old)).rowcount
        c2 = conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old)).rowcount
        c3 = conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old)).rowcount
        if c1 + c2 + c3 > 0:
            applied += 1
            print(f"  '{old}' -> '{new}'  ({c1+c2} trains, {c3} stops)")

    # Ricostruisci stations
    conn.execute("DELETE FROM stations")
    names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n and n.strip(): names.add(n.strip())
    for n in sorted(names):
        conn.execute("INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)", (n, normalize_station_name(n)))

    # Dedup post-merge
    n_before = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    conn.execute("""
        DELETE FROM guaranteed_trains WHERE id NOT IN (
            SELECT MIN(id) FROM guaranteed_trains
            GROUP BY train_number, origin, destination, dep_time, day_type, table_type
        )
    """)
    n_after = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]

    conn.commit()
    print(f"\nAlias applicati: {applied}")
    print(f"Treni dedup-eliminati: {n_before - n_after}")
    print(f"Stazioni finali: {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]}")

    print("\n--- Verifica stazioni chiave ---")
    for kw in ["pescara", "benedetto", "ancona", "verona", "foggia", "civitanova", "vasto", "milano", "roma", "bologna"]:
        names = [r[0] for r in conn.execute(f"SELECT name FROM stations WHERE lower(name) LIKE '%{kw}%' ORDER BY name")]
        print(f"  {kw}: {names}")

    conn.close()


if __name__ == "__main__":
    main()
