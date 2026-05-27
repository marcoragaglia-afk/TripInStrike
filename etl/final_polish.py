"""Pulizia finale di residui + verifica Ancona->Venezia."""
import sqlite3
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Alias addizionali per residui
FINAL_ALIASES = {
    "Forl�": "Forli",
    "OLOGNA CENT RALE": "Bologna Centrale",
    "PESCARA Centrale": "Pescara Centrale",
    "PESCARA Porta Nuova": "Pescara Porta Nuova",
    "PESCARA Tribunale": "Pescara Tribunale",
    "Cattolica- S.G.-G.": "Cattolica S.Giovanni Gabicce",
    "Castelbolognese": "Castelbolognese-Riolo Terme",
    "S.Benedetto del T.": "S. Benedetto d.T",
    "Civitanova Marche": "Civitanova-M.Montegr.",
    "Castelplanio-C.": "Castelplanio-Cupra m.",
    "Castel S.Pietro T.": "Castel S.Pietro Terme",
    "Genga-S.Vittore T.": "Genga-S.Vittore Terme",
    "Castelfranco E.": "Castelfranco Emilia",
    "Macerata Univers": "Macerata Universita",
    "Macerata Fontesc.": "Macerata Fontescodella",
    "Chiusi-Chianciano T": "Chiusi-Chianciano Terme",
    "Pantiere di C.": "Pantiere di Castelplanio",
    "Reggio Cal.C.le": "Reggio Calabria Centrale",
    "Monsampolo del T": "Monsampolo del Tronto",
    "Monsampolo del T.": "Monsampolo del Tronto",
    "Lamezia Terme C.le": "Lamezia Terme Centrale",
    "Roma Tibur.": "Roma Tiburtina",
    "Roma T iburtina": "Roma Tiburtina",
    "S.Vito-Lanciano": "S. Vito-Lanciano",
    "S.Severino Marche": "San Severino Marche",
    "Massa Centro": "Massa Centro",
    "L'Aquila": "L'Aquila",
    "Padovaq.M": "Padova",
    "Campiglia M.ma": "Campiglia Marittima",
    "Falconara M.ma": "Falconara Marittima",
}


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Applica alias finali
    applied = 0
    for old, new in FINAL_ALIASES.items():
        c1 = conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old)).rowcount
        c2 = conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old)).rowcount
        c3 = conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old)).rowcount
        if c1+c2+c3 > 0:
            applied += 1
            print(f"  {old!r} -> {new!r}  (trains={c1+c2}, stops={c3})")

    # Ricostruisci stations
    conn.execute("DELETE FROM stations")
    names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n and n.strip():
            names.add(n.strip())
    for n in sorted(names):
        conn.execute("INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                     (n, normalize_station_name(n)))
    conn.commit()

    print(f"\nApplied: {applied}")
    print(f"Stazioni finali: {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]}")

    # === Verifica Ancona -> Venezia ===
    print("\n" + "=" * 60)
    print("DIAGNOSI Ancona -> Venezia Santa Lucia")
    print("=" * 60)
    # Cerca quali AV potrebbero collegare
    print("\n1. AV che hanno Ancona nelle fermate o origine:")
    av_ancona = conn.execute("""
        SELECT DISTINCT t.train_number, t.origin, t.destination, t.dep_time,
               s.arrival, s.departure
        FROM guaranteed_trains t
        LEFT JOIN train_stops s ON t.train_number = s.train_number AND s.station LIKE '%Ancona%'
        WHERE t.table_type IN ('tabella_a','tabella_b')
          AND (t.origin LIKE '%Ancona%' OR s.train_number IS NOT NULL)
        ORDER BY t.dep_time
    """).fetchall()
    for r in av_ancona:
        print(f"  {r['train_number']:6s}  {r['origin']:22s} -> {r['destination']:22s}  Ancona arr={r['arrival'] or '':5s} dep={r['departure'] or '':5s}")

    print("\n2. AV/IC che vanno a Venezia (qualsiasi):")
    av_venezia = conn.execute("""
        SELECT train_number, origin, destination, dep_time, arr_time
        FROM guaranteed_trains
        WHERE table_type IN ('tabella_a','tabella_b')
          AND destination LIKE '%Venezia%'
        ORDER BY dep_time
    """).fetchall()
    for r in av_venezia:
        print(f"  {r['train_number']:6s}  {r['origin']:22s} -> {r['destination']:22s}  dep={r['dep_time']} arr={r['arr_time']}")

    print("\n3. AV/IC che hanno Bologna in fermate (per cambio):")
    via_bologna = conn.execute("""
        SELECT DISTINCT t.train_number, t.origin, t.destination, s.arrival, s.departure
        FROM guaranteed_trains t
        JOIN train_stops s ON t.train_number = s.train_number
        WHERE t.table_type IN ('tabella_a','tabella_b')
          AND s.station LIKE '%Bologna%'
          AND t.destination LIKE '%Venezia%'
        ORDER BY t.dep_time
    """).fetchall()
    print(f"  AV verso Venezia con Bologna nelle fermate: {len(via_bologna)}")
    for r in via_bologna:
        print(f"  {r['train_number']:6s}  {r['origin']:22s} -> {r['destination']:22s}  Bol arr={r['arrival'] or '':5s} dep={r['departure'] or '':5s}")

    conn.close()


if __name__ == "__main__":
    main()
