"""
Validazione delle fermate intermedie per treni garantiti.

Strategia (in ordine):
1. Normalizza nome stazioni (lower, no punt., no spazi extra).
2. Cerca la destinazione del treno tra le fermate -> tronca tutto dopo.
3. Cerca l'origine tra le fermate -> tronca tutto prima (escludendola, è già il dep_time).
4. Verifica monotonicità temporale della sequenza risultante.
5. Verifica che ogni fermata abbia un orario valido.
6. Se la destinazione NON viene trovata nelle fermate E non abbiamo arr_time,
   le fermate sono sospette: ELIMINA tutto per quel treno.

Risultato: per ogni treno o abbiamo fermate pulite (delimitate dai capolinea
del treno garantito) o nessuna fermata.
"""
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_t(t: str | None) -> int | None:
    if not t:
        return None
    m = TIME_RE.match(t.strip())
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if h > 23 or mm > 59:
        return None
    return h * 60 + mm


# Normalizzazione station name per matching robusto
_NORM_RE = re.compile(r"[^a-z0-9]+")
_ABBREV = {
    "centrale": "c", "c.le": "c", "cle": "c", "centr": "c",
    "porta": "p", "p.n.": "pn", "p.nuova": "pn", "pnuova": "pn", "pn": "pn",
    "p.garibaldi": "pg", "porta garibaldi": "pg",
    "santa": "s", "s.": "s", "s": "s",
    "marittima": "mm", "m.ma": "mm", "ma": "mm",
    "santa maria novella": "smn", "s.m.n.": "smn", "smn": "smn",
}

def normalize(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[•·|]", "", s)        # rimuovi bullet/pipe
    # rimuovi note numeriche tipo "Vicenza215-216" -> "vicenza"
    s = re.sub(r"\d+[-\d]*", "", s)
    s = _NORM_RE.sub(" ", s)
    s = " ".join(s.split())
    # applica abbreviazioni
    for k, v in _ABBREV.items():
        s = re.sub(rf"\b{re.escape(k)}\b", v, s)
    s = re.sub(r"\s+", "", s)
    return s


def station_match(a: str, b: str) -> bool:
    """Confronto fuzzy: normalizza e verifica uguaglianza o contenimento."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Se uno contiene l'altro almeno per 5+ caratteri, ok
    if len(na) >= 5 and na in nb:
        return True
    if len(nb) >= 5 and nb in na:
        return True
    return False


def find_match_index(stops: list, target: str) -> int:
    """Restituisce l'indice della prima fermata che matcha target, -1 altrimenti."""
    for i, (seq, station, arr, dep) in enumerate(stops):
        if station_match(station, target):
            return i
    return -1


def validate_and_truncate(
    train_number: str,
    origin: str,
    destination: str,
    dep_time: str | None,
    arr_time: str | None,
    stops: list[tuple[int, str, str | None, str | None]],
) -> list[tuple[int, str, str | None, str | None]] | None:
    """
    Ritorna la lista di fermate pulite (potenzialmente troncata),
    oppure None se le fermate sono troppo contaminate (vanno eliminate tutte).
    """
    if not stops:
        return []

    # 1. Cerca destinazione nelle fermate
    dest_idx = find_match_index(stops, destination)
    if dest_idx == -1:
        # Destinazione non presente nelle fermate
        # Se abbiamo arr_time, possiamo usarlo come boundary, altrimenti scartiamo
        if arr_time is None:
            return None
        # Senza match di destinazione e con arr_time, accettiamo solo se tutti
        # gli orari delle fermate sono <= arr_time
        arr_min = parse_t(arr_time)
        if arr_min is None:
            return None
        for seq, station, arr, dep in stops:
            t = parse_t(arr) or parse_t(dep)
            if t is None or t > arr_min + 5:
                return None
        # Le fermate sembrano coerenti con arr_time, le manteniamo tutte
        truncated = stops
    else:
        # Tronca tutto dopo la destinazione (inclusa)
        truncated = stops[: dest_idx + 1]

    # 2. Cerca origine: se è in mezzo alla lista, scarta le fermate prima
    orig_idx = find_match_index(truncated, origin)
    if orig_idx > 0:
        truncated = truncated[orig_idx + 1:]  # skip origin stop itself

    if not truncated:
        return []

    # 3. Verifica che ogni fermata abbia un orario valido
    times: list[int] = []
    for seq, station, arr, dep in truncated:
        t = parse_t(dep) if dep else parse_t(arr)
        if t is None:
            return None
        times.append(t)

    # 4. Monotonicità con dep_time/arr_time come boundaries
    dep_min = parse_t(dep_time)
    arr_min = parse_t(arr_time)
    full = []
    if dep_min is not None:
        full.append(dep_min)
    full.extend(times)
    if arr_min is not None:
        full.append(arr_min)

    # Permetti 1 wrap di mezzanotte
    wraps = 0
    for i in range(1, len(full)):
        if full[i] < full[i - 1]:
            wraps += 1
            if wraps > 1:
                return None
            if full[i - 1] - full[i] < 60:
                return None  # discontinuità troppo piccola per essere wrap mezzanotte

    # 5. Nessuna stazione duplicata nella sequenza
    seen = set()
    for seq, station, arr, dep in truncated:
        n = normalize(station)
        if n in seen:
            return None
        seen.add(n)

    return truncated


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("VALIDAZIONE + TRONCAMENTO FERMATE")
    print("=" * 70)

    trains = conn.execute(
        "SELECT id, train_number, origin, destination, dep_time, arr_time FROM guaranteed_trains"
    ).fetchall()
    print(f"\nTreni da processare: {len(trains)}")

    truncated_count = 0
    eliminated_count = 0
    unchanged_count = 0
    no_stops_count = 0

    # Processiamo per train_number unico (anche se ci sono duplicati nel master)
    seen_tn = set()
    for t in trains:
        tn = t["train_number"]
        if tn in seen_tn:
            continue
        seen_tn.add(tn)

        stops_rows = conn.execute(
            "SELECT sequence, station, arrival, departure FROM train_stops "
            "WHERE train_number=? ORDER BY sequence",
            (tn,),
        ).fetchall()
        stops = [(r["sequence"], r["station"], r["arrival"], r["departure"]) for r in stops_rows]

        if not stops:
            no_stops_count += 1
            continue

        cleaned = validate_and_truncate(
            tn, t["origin"], t["destination"],
            t["dep_time"], t["arr_time"], stops,
        )

        if cleaned is None:
            # Tutto contaminato -> elimina tutte le fermate
            conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))
            eliminated_count += 1
        elif len(cleaned) != len(stops):
            # Sostituisci con la versione troncata, ri-numerando le sequence
            conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))
            for i, (seq, station, arr, dep) in enumerate(cleaned):
                conn.execute(
                    "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tn, station, i, arr, dep),
                )
            truncated_count += 1
        else:
            unchanged_count += 1

    conn.commit()

    print(f"\nFermate INTOCCATE (già pulite):       {unchanged_count}")
    print(f"Fermate TRONCATE (rimosse contaminazioni): {truncated_count}")
    print(f"Fermate ELIMINATE (troppo contaminate): {eliminated_count}")
    print(f"Treni senza fermate (intoccati):        {no_stops_count}")

    total_stops = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    trains_with_stops = conn.execute(
        "SELECT COUNT(DISTINCT train_number) FROM train_stops"
    ).fetchone()[0]
    print(f"\nFermate totali rimaste: {total_stops}")
    print(f"Treni con fermate: {trains_with_stops}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
