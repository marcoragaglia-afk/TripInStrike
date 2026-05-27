"""
Pulizia dei nomi stazione nella tabella train_stops.
Pattern di contaminazione PDF:
  'Foggia62 a I •'                       -> 'Foggia'
  'Caserta a 09.57 09.57E'               -> 'Caserta'
  'Bari Centrale63 a 13.57 •'            -> 'Bari Centrale'
  'sabato. Caserta a 09.57 09.57E'       -> 'Caserta'
  'Vicenza215-216 ·'                     -> 'Vicenza'
  '-Padovaq.M35,Treviglio-Milanoq.M10.'  -> 'Padova' (primo nome riconoscibile)

Strategia:
1. Strip leading non-alphabetic (.,-, lowercase prefixes)
2. Trunca su pattern di "junk" che inizia con: numero, 'a HH.MM', 'a •', '·', '|', ' a '
3. Strip trailing punctuation/spaces
4. Match alla tabella stations: se match fuzzy, usa quel nome canonico
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Junk patterns da rimuovere alla fine del nome
JUNK_END = re.compile(
    r"(\s*\d+[\s\-\d]*[a-zA-Z]?\s*[a-z]?\s*[\d:.]+.*$"  # "62 a 09.57..."
    r"|\s+a\s+[\d:.]+.*$"                                 # " a 09.57..."
    r"|\s*[•·|].*$"                                       # bullet/pipe noise
    r"|\s+a\s+[•·]\s*[•·]?.*$"                            # " a • •..."
    r"|\d+\s*[a-z]+\s*[•·].*$"                            # "62 a •..."
    r")"
)

# Junk all'inizio
JUNK_START = re.compile(
    r"^\s*([\.\,\-]+\s*"
    r"|sabato\.\s+"
    r"|domenica\.\s+"
    r"|lunedi\.\s+"
    r"|festivo\.\s+"
    r")"
)


def clean_station(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    # Strip junk start ripetutamente
    prev = None
    while prev != s:
        prev = s
        s = JUNK_START.sub("", s).strip()
    # Strip junk end
    s = JUNK_END.sub("", s).strip()
    # Pulisci doppi spazi e punteggiatura residua
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,;:•·|*\"'")
    # Rimuovi numeri puri attaccati (es. "Foggia62" -> "Foggia")
    s = re.sub(r"(\b[A-Za-z][A-Za-z]+)\d+\b", r"\1", s)
    return s.strip()


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Trova tutti i nomi delle fermate
    stops = conn.execute(
        "SELECT id, station FROM train_stops"
    ).fetchall()

    print(f"Fermate da pulire: {len(stops)}")

    fixed = 0
    deleted = 0
    for s in stops:
        cleaned = clean_station(s["station"])
        if not cleaned or len(cleaned) < 3:
            # Elimina fermate con nome troppo corto/vuoto dopo cleanup
            conn.execute("DELETE FROM train_stops WHERE id=?", (s["id"],))
            deleted += 1
        elif cleaned != s["station"]:
            conn.execute("UPDATE train_stops SET station=? WHERE id=?", (cleaned, s["id"]))
            fixed += 1

    conn.commit()
    print(f"Fermate normalizzate: {fixed}")
    print(f"Fermate eliminate (nome invalido): {deleted}")

    # Aggiorna stations
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from build_db import normalize_station_name
    seen = {r[0] for r in conn.execute("SELECT name FROM stations").fetchall()}
    added = 0
    for (st,) in conn.execute("SELECT DISTINCT station FROM train_stops").fetchall():
        if st and st not in seen:
            conn.execute(
                "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                (st, normalize_station_name(st))
            )
            seen.add(st)
            added += 1
    conn.commit()
    print(f"Stazioni aggiunte: {added}")

    # Mostra esempi del treno 8315
    print("\n=== Treno 8315 (Roma->Lecce) dopo pulizia ===")
    for r in conn.execute(
        "SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number='8315' ORDER BY sequence"
    ):
        print(f"  seq={r['sequence']:2d}  {r['station']:30s}  arr={r['arrival'] or '':5s}  dep={r['departure'] or '':5s}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
