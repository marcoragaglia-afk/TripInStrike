"""
Parser dell'orario completo (In_Treno_Orario_TuttItalia.pdf, 2581 pagine).

Il PDF usa il formato "orario tabellare" classico di Trenitalia:
- Ogni "quadro" copre una relazione ferroviaria
- Colonne = treni, righe = stazioni
- Formato complesso con CID chars, simboli, footnotes

Strategia:
1. Per ogni pagina dati, identificare la struttura a colonne
2. Estrarre numero treno per ogni colonna
3. Estrarre stazioni (righe) con orari
4. Produrre lista di (numero_treno, stazione, sequenza, arrival, departure)

Nota: il parsing è best-effort per via della complessità del formato.
I treni non matchati usano solo origin/dest dalle liste garantite.
"""

import re
import pdfplumber
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PDF_TIMETABLE = Path(r"C:\Users\El_Bl\Pictures\In_Treno_Orario_TuttItalia.pdf")

# Pagine dati effettive (dopo le prime pagine di indice)
DATA_START_PAGE = 40
DATA_END_PAGE = 2581


@dataclass
class TrainStop:
    train_number: str
    station: str
    sequence: int
    arrival: Optional[str]
    departure: Optional[str]


TIME_PAT = re.compile(r"\b(\d{1,2}[.:]\d{2})\b")
TRAIN_NUM_PAT = re.compile(r"\b(\d{4,5})\b")


def norm_time(t: str) -> str:
    return t.replace(".", ":") if t else ""


def clean(s: str) -> str:
    return " ".join(s.split()) if s else ""


def clean_station_name(raw: str) -> str:
    """
    Pulisce il nome stazione estratto dal PDF dell'orario.
    Gestisce:
    - Artefatti (cid:N) da font non mappati Unicode
    - Nomi CamelCase fusi senza spazio ("NapoliCentrale" -> "Napoli Centrale")
    - Marcatori footnote singoli ("a", "R", "O", "S") appesi alla fine
    - Numeri di binario/marciapiede ("80-85", "47", "1/2") con o senza spazio prima
    """
    s = raw.strip()
    if not s:
        return ''
    # Rimuovi artefatti (cid:N)
    s = re.sub(r'\s*\(cid:\d+\)\s*', ' ', s).strip()
    # Fix CamelCase prima: "NapoliCentrale" -> "Napoli Centrale"
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    s = ' '.join(s.split())
    # Rimuovi iterativamente suffissi footnote/binario/orario finché stabile
    for _ in range(10):
        prev = s
        s = re.sub(r'\s+[A-Za-z]\s*$', '', s).strip()             # " a", " R", " O"
        s = re.sub(r'(\s+\d{1,2}[.:]\d{0,2})+\s*$', '', s).strip()  # " 12.38 13.34 11." (orari multipli)
        s = re.sub(r'\s*\d+[-/.]?\d*\s*$', '', s).strip()           # "80-85", "47", "11." (spazio opzionale)
        if s == prev:
            break
    # Fix abbreviazioni standard coerenti con fix_stations.py
    s = re.sub(r'\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?', 'S.M.N.', s, flags=re.IGNORECASE)
    return ' '.join(s.split()).strip()


def is_arrival_row(raw_station: str) -> bool:
    """
    True se la riga del PDF è una riga di arrivo.
    Il marcatore ' a' può essere seguito da artefatti CID, numeri di binario,
    ulteriori footnote — cerca quindi ' a' ovunque nel suffisso.
    """
    return bool(re.search(r'\s+a(?:\s|$|\s*\(cid:|\s*\d)', raw_station))


def is_data_page(txt: str) -> bool:
    """Verifica se una pagina contiene dati orari."""
    if not txt or len(txt) < 50:
        return False
    # Le pagine dati hanno orari nel formato HH.MM
    times = TIME_PAT.findall(txt)
    return len(times) >= 3


def extract_train_numbers_from_header(header_text: str) -> list[str]:
    """Estrae numeri treno dall'intestazione colonne."""
    nums = TRAIN_NUM_PAT.findall(header_text)
    # Filtra duplicati mantenendo l'ordine
    seen = set()
    result = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def parse_timetable_page_columnar(page) -> dict[str, list[TrainStop]]:
    """
    Parsa una pagina dell'orario tabellare.
    Restituisce {numero_treno: [TrainStop, ...]}
    """
    result: dict[str, list[TrainStop]] = {}
    width = float(page.width)
    height = float(page.height)

    # Estrai testo completo per vedere struttura
    txt = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    if not is_data_page(txt):
        return result

    # Estrai parole con posizioni
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return result

    # Raggruppa per riga Y
    row_groups: dict[int, list] = {}
    for w in words:
        y_key = round(float(w["top"]) / 4) * 4
        row_groups.setdefault(y_key, []).append(w)

    sorted_rows = [(y, sorted(ws, key=lambda w: w["x0"]))
                   for y, ws in sorted(row_groups.items())]

    if len(sorted_rows) < 3:
        return result

    # Le prime righe contengono i numeri treno (intestazione)
    # Le righe successive: stazione + orari per colonna
    # Identifica colonne X dai numeri treno nella prima riga utile

    # Cerca riga con numeri treno (4-5 cifre)
    header_row_idx = -1
    train_cols: list[tuple[float, str]] = []  # (x_center, train_num)

    for row_idx, (y, row_words) in enumerate(sorted_rows[:15]):
        nums_in_row = [(w, w["text"]) for w in row_words
                       if re.match(r"^\d{4,5}$", w["text"])]
        if len(nums_in_row) >= 2:
            header_row_idx = row_idx
            for w, num in nums_in_row:
                x_center = (float(w["x0"]) + float(w["x1"])) / 2
                train_cols.append((x_center, num))
            break

    if not train_cols:
        return result

    # Assegna parole alle colonne basandosi sulla distanza X
    col_xs = [x for x, _ in train_cols]
    col_nums = [n for _, n in train_cols]

    def assign_to_col(x_pos: float) -> int:
        """Restituisce indice colonna più vicina."""
        dists = [abs(x_pos - cx) for cx in col_xs]
        return dists.index(min(dists))

    # Larghezza della colonna (approssimata)
    if len(col_xs) >= 2:
        col_width = (col_xs[-1] - col_xs[0]) / (len(col_xs) - 1) * 0.8
    else:
        col_width = width / 8

    # Analizza righe dati (dopo l'intestazione)
    for row_idx, (y, row_words) in enumerate(sorted_rows[header_row_idx + 2:]):
        row_text = " ".join(w["text"] for w in row_words)
        row_times = TIME_PAT.findall(row_text)

        if not row_times:
            continue

        # Primo "token" lontano sinistra = nome stazione
        station_words = [w for w in row_words if float(w["x0"]) < col_xs[0] - col_width * 0.3]
        if not station_words:
            continue
        raw_station = clean(" ".join(w["text"] for w in station_words))
        arr_row = is_arrival_row(raw_station)
        station = clean_station_name(raw_station)

        if len(station) < 2 or station[0].isdigit():
            continue

        # Parole di orario: assegna alla colonna più vicina
        time_words = [w for w in row_words if TIME_PAT.match(w["text"].replace(" ", ""))]

        for tw in time_words:
            t_x = (float(tw["x0"]) + float(tw["x1"])) / 2
            # Solo se non troppo distante dalla colonna
            col_idx = assign_to_col(t_x)
            if abs(t_x - col_xs[col_idx]) > col_width:
                continue
            train_num = col_nums[col_idx]
            t_str = norm_time(tw["text"])

            if train_num not in result:
                result[train_num] = []

            # Cerca entry esistente per questo nome stazione (già pulito)
            existing = next((s for s in result[train_num] if s.station == station), None)

            if arr_row:
                # Riga di arrivo: il tempo è l'orario di arrivo
                if existing:
                    existing.arrival = existing.arrival or t_str
                else:
                    result[train_num].append(TrainStop(
                        train_number=train_num, station=station,
                        sequence=len(result[train_num]),
                        arrival=t_str, departure=None,
                    ))
            else:
                # Riga di partenza (o unica riga): il tempo è l'orario di partenza
                if existing:
                    existing.departure = existing.departure or t_str
                else:
                    result[train_num].append(TrainStop(
                        train_number=train_num, station=station,
                        sequence=len(result[train_num]),
                        arrival=None, departure=t_str,
                    ))

    return result


def parse_timetable(target_trains: set[str], max_pages: int = 2581) -> dict[str, list[TrainStop]]:
    """
    Parsa l'orario completo cercando i treni in target_trains.
    Restituisce {numero_treno: [TrainStop, ...]} per i treni trovati.
    """
    all_stops: dict[str, list[TrainStop]] = {}
    found_trains: set[str] = set()

    print(f"Parsing orario completo ({max_pages} pagine)...")
    print(f"Cercando {len(target_trains)} treni garantiti...")

    with pdfplumber.open(str(PDF_TIMETABLE)) as pdf:
        total = min(max_pages, len(pdf.pages))
        for pg_idx in range(DATA_START_PAGE - 1, total):
            if pg_idx % 100 == 0:
                print(f"  Pagina {pg_idx + 1}/{total} - trovati {len(found_trains)} treni...")

            page = pdf.pages[pg_idx]

            # Controllo veloce: la pagina contiene numeri di treni cercati?
            txt_quick = page.extract_text(x_tolerance=5, y_tolerance=5) or ""
            page_nums = set(TRAIN_NUM_PAT.findall(txt_quick))
            relevant = page_nums & target_trains
            if not relevant:
                continue

            try:
                page_stops = parse_timetable_page_columnar(page)
            except Exception:
                continue

            for train_num, stops in page_stops.items():
                if train_num in target_trains and stops:
                    if train_num not in all_stops or len(stops) > len(all_stops[train_num]):
                        all_stops[train_num] = stops
                        found_trains.add(train_num)

    print(f"Trovate fermate per {len(found_trains)}/{len(target_trains)} treni garantiti")
    return all_stops


if __name__ == "__main__":
    # Test su un sottoinsieme di treni
    test_trains = {"9512", "9520", "9527", "4205", "23751"}
    results = parse_timetable(test_trains, max_pages=300)
    for num, stops in results.items():
        print(f"\nTreno {num}:")
        for s in stops:
            print(f"  {s.sequence:2d}. {s.station:30s}  arr={s.arrival}  dep={s.departure}")
