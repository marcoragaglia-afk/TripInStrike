"""
Parser per i PDF dei treni garantiti in caso di sciopero.

merged1 (ilovepdf_merged (1).pdf):
  - Pagine 1-141:  treni regionali garantiti nei giorni FERIALI
  - Pagine 142-148: Tabella A (lunga percorrenza, feriali E festivi)

merged2 (ilovepdf_merged (2).pdf):
  - Pagine 1-40:  treni regionali garantiti nei giorni FESTIVI
  - Pagine 41+:   Tabella B (lunga percorrenza, festivi – condizioni speciali)
"""

import re
import pdfplumber
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

PDF_MERGED1 = Path(r"C:\Users\El_Bl\Downloads\ilovepdf_merged (1).pdf")
PDF_MERGED2 = Path(r"C:\Users\El_Bl\Downloads\ilovepdf_merged (2).pdf")

# Pagina (1-based) da cui inizia Tabella A in merged1
TABLE_A_START_PAGE = 142
# Pagina (1-based) da cui inizia Tabella B in merged2
TABLE_B_START_PAGE = 41


@dataclass
class GuaranteedTrain:
    train_number: str
    category: str = ""
    origin: str = ""
    destination: str = ""
    dep_time: str = ""
    arr_time: str = ""
    day_type: str = ""   # feriale | festivo | entrambi
    table_type: str = "" # regionale | tabella_a | tabella_b
    region: str = ""
    line: str = ""
    notes: str = ""
    validity: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

TIME_RE = re.compile(r"\b(\d{1,2}[:.]\d{2})\b")
TRAIN_NUM_RE = re.compile(r"^\d{2,6}$")

def norm_time(t: str) -> str:
    """Normalizza 07.10 -> 07:10"""
    return t.replace(".", ":") if t else ""


def clean(s: str) -> str:
    return " ".join(s.split()) if s else ""


# Inserisce spazio tra CamelCase: "RomaTiburtina" -> "Roma Tiburtina"
_CAMEL_RE = re.compile(r"([a-z])([A-Z])")

def fix_station_name(s: str) -> str:
    """Post-processa nome stazione: rimuove spazi extra e separa CamelCase."""
    s = clean(s)
    # Inserisce spazio prima di maiuscola preceduta da minuscola
    s = _CAMEL_RE.sub(r"\1 \2", s)
    # Normalizza spazi multipli
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_region_from_text(txt: str) -> str:
    """Estrae il nome della regione dall'intestazione pagina."""
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    region_keywords = {
        "abruzzo", "basilicata", "bolzano", "trento", "calabria", "campania",
        "emilia", "friuli", "lazio", "liguria", "lombardia", "marche",
        "molise", "piemonte", "puglia", "sardegna", "sicilia", "toscana",
        "umbria", "valle", "veneto"
    }
    for l in lines[:5]:
        low = l.lower()
        if any(k in low for k in region_keywords):
            return l
    return ""


def is_region_header(line: str) -> bool:
    region_keywords = [
        "abruzzo", "basilicata", "bolzano", "trento", "calabria", "campania",
        "emilia", "friuli", "lazio", "liguria", "lombardia", "marche",
        "molise", "piemonte", "puglia", "sardegna", "sicilia", "toscana",
        "umbria", "valle d'aosta", "veneto", "bozen"
    ]
    l = line.lower().strip()
    return any(k in l for k in region_keywords) and len(l) < 80


def is_line_header(line: str) -> bool:
    return line.strip().lower().startswith("linea ")


# ──────────────────────────────────────────────────────────────────────────────
# Parser treni regionali feriali (merged1, pagine 1-141)
# Layout testuale (x_tolerance=5, y_tolerance=5):
#   - Blocco "N.treno" seguito da numeri treno
#   - Blocco "Stazionedipartenza" seguito da nomi stazioni
#   - Blocco "Orapart. Stazionediarrivo" + righe "HH:MM Destinazione"
#   - Sub-header "Linea ..." che indica la linea
# La tecnica più affidabile: usa word positions per ricostruire le colonne.
# ──────────────────────────────────────────────────────────────────────────────

def parse_regional_feriali_page(page) -> list[GuaranteedTrain]:
    """Parsa una singola pagina di treni regionali feriali."""
    trains: list[GuaranteedTrain] = []

    # Estrai tutte le parole con coordinate
    words = page.extract_words(x_tolerance=5, y_tolerance=5)
    if not words:
        return trains

    # Raggruppa parole per riga (y-coordinate simile)
    rows: dict[int, list] = {}
    for w in words:
        y_key = round(w["top"] / 3) * 3  # quantizza a 3pt
        rows.setdefault(y_key, []).append(w)

    sorted_rows = sorted(rows.items())

    # Determina i range X delle colonne guardando l'intestazione
    # Colonna 1: N.treno  (x ~ 0-90)
    # Colonna 2: Stazionedipartenza (x ~ 90-230)
    # Colonna 3: Orapart. (x ~ 230-280)
    # Colonna 4: Stazionediarrivo (x ~ 280-600)
    COL1_MAX = 90
    COL2_MAX = 230
    COL3_MAX = 285

    current_region = ""
    current_line = ""

    # Dizionario: numero_treno -> GuaranteedTrain (parziale)
    train_map: dict[str, GuaranteedTrain] = {}
    # Lista numeri treno in ordine (col1)
    train_numbers_col: list[str] = []
    # Stazioni di partenza (col2)
    origins_col: list[str] = []
    # Coppie (ora, dest) (col3+4)
    timed_dests: list[tuple[str, str]] = []  # (time, dest)

    collecting_numbers = False
    collecting_origins = False

    row_text_cache: list[tuple[int, str, float]] = []  # (y_key, full_text, x_min)

    for y_key, row_words in sorted_rows:
        row_words_sorted = sorted(row_words, key=lambda w: w["x0"])
        full_text = " ".join(w["text"] for w in row_words_sorted).strip()
        x_min = row_words_sorted[0]["x0"]
        row_text_cache.append((y_key, full_text, x_min))

    # Parsing per blocchi
    i = 0
    n = len(row_text_cache)

    while i < n:
        y_key, text, x_min = row_text_cache[i]

        # Intestazione regione
        if is_region_header(text):
            current_region = text.strip()
            i += 1
            continue

        # Sub-header linea
        if is_line_header(text):
            current_line = text.strip()
            i += 1
            continue

        # Header colonne (salta)
        lower = text.lower()
        if "n.treno" in lower or "stazionedipartenza" in lower or "orapart" in lower:
            i += 1
            continue
        if "servizi minimi" in lower or "caso di sciopero" in lower:
            i += 1
            continue

        # Numero treno (colonna 1, x piccolo, solo cifre)
        if x_min < COL1_MAX and re.match(r"^\d{2,6}$", text.replace(" ", "")):
            num = text.replace(" ", "")
            if num not in train_map:
                t = GuaranteedTrain(
                    train_number=num,
                    day_type="feriale",
                    table_type="regionale",
                    region=current_region,
                    line=current_line,
                )
                train_map[num] = t
                train_numbers_col.append(num)
            i += 1
            continue

        # Riga con orario (colonna 3+4): HH:MM Destinazione
        m = TIME_RE.match(text.strip())
        if m:
            time_str = norm_time(m.group(1))
            dest = text[m.end():].strip()
            timed_dests.append((time_str, dest))
            i += 1
            continue

        i += 1

    # Matching numeri_treno <-> stazioni origine <-> (time, dest)
    # Le stazioni di partenza sono al centro (x ~ 90-230)
    # Le ridestiniamo alle righe dei treni basandoci sulla posizione Y
    # Approccio alternativo: rileggi la pagina come testo strutturato a colonne

    return trains  # vedi parse_regional_feriali_page_v2 più robusta


def parse_regional_feriali_page_v2(page, current_region: str, current_line: str) -> tuple[list[GuaranteedTrain], str]:
    """
    Parser basato su word positions.

    Layout della pagina (da analisi empirica):
      Col 1 - N.treno:           x0 ~19,  x1 ~42   (sinistra)
      Col 2 - Staz.partenza:     x0 ~70,  x1 ~145  (centro-sinistra)
      Col 3 - Orapart.:          x0 ~211, x1 ~232  (centro-destra)
      Col 4 - Staz.arrivo:       x0 ~249, x1 ~...  (destra)

    Tutte le colonne condividono lo stesso range Y per ogni riga treno.
    """
    trains: list[GuaranteedTrain] = []

    # x_tolerance=5 mantiene parole separate; fix_station_name gestisce CamelCase
    words = page.extract_words(x_tolerance=5, y_tolerance=5)
    if not words:
        return trains, current_line

    # Raggruppa per riga Y (quantizzata a 4pt per robustezza)
    rows: dict[int, list] = {}
    for w in words:
        y_key = round(float(w["top"]) / 4) * 4
        rows.setdefault(y_key, []).append(w)

    # Soglie X colonne (da analisi empirica del PDF ilovepdf_merged_1):
    #   N.treno:         x0 ~19-42
    #   Staz.partenza:   x0 ~70-145  (con x_tolerance=10 fino a ~155)
    #   Orapart.:        x0 ~211-231
    #   Staz.arrivo:     x0 ~249-370
    #   Note:            x0 ~370+
    X_NUM_MAX = 60       # fine colonna numero treno
    X_ORIG_MIN = 60      # inizio colonna origine
    X_ORIG_MAX = 200     # fine colonna origine
    X_TIME_MIN = 195     # inizio colonna orario
    X_TIME_MAX = 245     # fine colonna orario (NON includere x0=249)
    X_DEST_MIN = 245     # inizio colonna destinazione
    X_DEST_MAX = 370     # fine colonna destinazione (Note iniziano ~370)

    SKIP_TEXTS = {
        "n.treno", "stazionedipartenza", "orapart.", "stazionediarrivo",
        "servizi", "minimi", "garantiti", "incaso", "caso", "di", "sciopero",
        "nei", "giorni", "feriali", "note", "categoria", "treno", "origine",
        "destinazione", "oradipartenza"
    }

    for y_key in sorted(rows):
        row_words = sorted(rows[y_key], key=lambda w: float(w["x0"]))
        row_text = " ".join(w["text"] for w in row_words).lower()

        # Skip header rows
        if any(k in row_text for k in ["n.treno", "stazionedipartenza", "orapart",
                                        "servizi minimi", "sciopero nei giorni"]):
            continue

        # Region header
        if is_region_header(" ".join(w["text"] for w in row_words)):
            current_region = " ".join(w["text"] for w in row_words).strip()
            continue

        # Line sub-header (al centro/destra, testo che inizia con "Linea")
        row_full = " ".join(w["text"] for w in row_words).strip()
        if is_line_header(row_full):
            current_line = row_full
            continue

        # Estrai celle per colonna X
        num_words = [w for w in row_words if float(w["x0"]) < X_NUM_MAX
                     and w["text"].lower() not in SKIP_TEXTS]
        orig_words = [w for w in row_words if X_ORIG_MIN <= float(w["x0"]) < X_ORIG_MAX
                      and w["text"].lower() not in SKIP_TEXTS]
        time_words = [w for w in row_words if X_TIME_MIN <= float(w["x0"]) < X_TIME_MAX]
        dest_words = [w for w in row_words if X_DEST_MIN <= float(w["x0"]) < X_DEST_MAX
                      and w["text"].lower() not in SKIP_TEXTS]
        note_words = [w for w in row_words if float(w["x0"]) >= X_DEST_MAX]

        # Numero treno: solo cifre
        num_text = "".join(w["text"] for w in num_words).strip()
        if not re.match(r"^\d{4,6}$", num_text):
            continue

        orig_text = fix_station_name(" ".join(w["text"] for w in orig_words))
        time_text = norm_time("".join(w["text"] for w in time_words).strip())
        dest_text = fix_station_name(" ".join(w["text"] for w in dest_words))
        notes = clean(" ".join(w["text"] for w in note_words))

        if not orig_text or not dest_text:
            continue

        trains.append(GuaranteedTrain(
            train_number=num_text,
            origin=orig_text,
            destination=dest_text,
            dep_time=time_text,
            day_type="feriale",
            table_type="regionale",
            region=current_region,
            line=current_line,
            notes=notes,
        ))

    return trains, current_line


# ──────────────────────────────────────────────────────────────────────────────
# Parser treni regionali festivi (merged2, pagine 1-40)
# Formato pulito: Categoria Treno Origine Ora Destinazione Note
# ──────────────────────────────────────────────────────────────────────────────

# Pattern note che terminano la parte "destinazione"
NOTE_STARTERS = re.compile(
    r"(\s+L'orario|\s+Si effettua|\s+Nota:|\s+NB:)",
    re.IGNORECASE
)

CATEGORY_RE = re.compile(
    r"^(REG|RV|IC|FA|FR|FB|EC|MET|BUS|AV|EXP|INT|EXB|EXC|EXD)\s+"
    r"(\d{2,6})\s+"
    r"(.+?)\s+"
    r"(\d{1,2}[:.]\d{2})\s+"
    r"(.+?)(?:\s+(L'orario.*))?$",
    re.IGNORECASE
)


def split_dest_note(dest_raw: str) -> tuple[str, str]:
    """Separa destinazione dalle note appendite."""
    m = NOTE_STARTERS.search(dest_raw)
    if m:
        return clean(dest_raw[:m.start()]), clean(dest_raw[m.start():])
    return clean(dest_raw), ""


def parse_regional_festivi_page(page, current_region: str) -> tuple[list[GuaranteedTrain], str]:
    trains: list[GuaranteedTrain] = []
    txt = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    lines = txt.splitlines()

    current_line = ""
    pending_note = ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Regione
        if is_region_header(line):
            current_region = line
            continue

        # Skip header
        lower = line.lower()
        if any(k in lower for k in [
            "servizi minimi", "caso di sciopero", "categoria", "treno",
            "origine", "destinazione", "ora di", "partenza", "note",
            "kategorie", "abfahrtszeit", "anmerkungen", "zugnummer",
            "tabella", "treni validi"
        ]):
            continue

        # Linea
        if is_line_header(line):
            current_line = line
            continue

        # Note continuation (multiline)
        if line.lower().startswith("l'orario") or line.lower().startswith("si effettua"):
            pending_note = line
            continue

        # Prova match categoria + treno
        m = CATEGORY_RE.match(line)
        if m:
            cat = m.group(1).upper()
            num = m.group(2)
            orig_raw = clean(m.group(3))
            time_str = norm_time(m.group(4))
            dest_raw = m.group(5) or ""
            explicit_note = m.group(6) or ""
            # Separa note appendite alla destinazione
            dest, inline_note = split_dest_note(dest_raw)
            # Separa note appendite all'origine
            orig, orig_note = split_dest_note(orig_raw)
            note = clean(explicit_note or inline_note or pending_note)
            pending_note = ""
            trains.append(GuaranteedTrain(
                train_number=num,
                category=cat,
                origin=orig,
                destination=dest,
                dep_time=time_str,
                day_type="festivo",
                table_type="regionale",
                region=current_region,
                line=current_line,
                notes=note,
            ))
            continue

        # Fallback: linea con numero treno anche senza categoria esplicita
        parts = line.split()
        if len(parts) >= 3 and re.match(r"^\d{4,6}$", parts[0] if not parts[0].isalpha() else ""):
            pass  # handled above or skip

    return trains, current_region


# ──────────────────────────────────────────────────────────────────────────────
# Parser Tabella A/B (lunga percorrenza)
# Formato: Treno n° | Categoria | Provenienza | Ora part. | Destinazione | Ora arr.
# ──────────────────────────────────────────────────────────────────────────────

LONG_DIST_RE = re.compile(
    r"^(\d{2,6})"              # numero treno (eventualmente con note come "(2)")
    r"(?:\s*\(\d+\))?\s+"
    r"([A-Z✈☆★◆▲•·\-]+)\s+"   # categoria (simboli inclusi)
    r"(.+?)\s+"                 # provenienza
    r"(\d{1,2}[:.]\d{2})\s+"   # orario partenza
    r"(.+?)\s+"                 # destinazione
    r"(\d{1,2}[:.]\d{2})"      # orario arrivo
    r"\s*$"
)

# Codici categoria testuale
CAT_MAP = {
    "A": "Freccia (AV - notte)",
    "B": "EuroCity/EuroNight",
    "C": "Intercity/Intercity Notte",
    "D": "EuroCity",
}


def parse_tabella_long_dist(
    pdf_path: Path, start_page: int, end_page: int,
    day_type: str, table_type: str,
    # Limiti X delle colonne (diversi per Tabella A e Tabella B)
    x_num: tuple[float, float] = (74, 118),
    x_cat: tuple[float, float] = (143, 188),
    x_orig: tuple[float, float] = (193, 313),
    x_dep: tuple[float, float] = (311, 350),
    x_dest: tuple[float, float] = (347, 480),
    x_arr: tuple[float, float] = (477, 512),
) -> list[GuaranteedTrain]:
    """
    Parsa Tabella A o Tabella B dal PDF usando word positions.

    Alcuni nomi di stazione (es. "REGGIO CALABRIA CENTRALE") sono spezzati su
    più righe Y intorno alla riga del numero treno. Ogni parola viene assegnata
    al treno Y più vicino (Voronoi assignment).
    """
    trains: list[GuaranteedTrain] = []

    X_NUM_MIN, X_NUM_MAX = x_num
    X_CAT_MIN, X_CAT_MAX = x_cat
    X_ORIG_MIN, X_ORIG_MAX = x_orig
    X_DEP_MIN, X_DEP_MAX = x_dep
    X_DEST_MIN, X_DEST_MAX = x_dest
    X_ARR_MIN, X_ARR_MAX = x_arr
    Y_MAX_DIST = 25  # distanza Y massima per assegnazione Voronoi

    SKIP_TEXTS_LOWER = {
        "treno", "n°", "categoria", "provenienza", "orario", "partenza",
        "destinazione", "arrivo", "tabella",
        "note", "continua", "treni", "validi", "elenco",
        "aggiornato", "sono", "da", "intendersi", "in", "i",
    }

    with pdfplumber.open(str(pdf_path)) as pdf:
        for pg_idx in range(start_page - 1, min(end_page, len(pdf.pages))):
            page = pdf.pages[pg_idx]
            words = page.extract_words(x_tolerance=5, y_tolerance=3)
            if not words:
                continue

            # Trova tutte le righe con numero treno (gestisce anche "8814(27)")
            train_rows: list[tuple[float, str]] = []  # (y, train_num)
            for w in words:
                x0 = float(w["x0"])
                y = float(w["top"])
                if X_NUM_MIN <= x0 <= X_NUM_MAX:
                    m = re.match(r"^(\d{3,6})", w["text"])
                    if m:
                        train_rows.append((y, m.group(1)))

            if not train_rows:
                continue

            train_ys = [y for y, _ in train_rows]

            # Assegnazione Voronoi: ogni parola va al treno Y più vicino
            word_by_train: dict[int, list] = {i: [] for i in range(len(train_rows))}
            for w in words:
                if w["text"].lower() in SKIP_TEXTS_LOWER:
                    continue
                wy = float(w["top"])
                wx0 = float(w["x0"])
                # Trova l'indice del treno più vicino
                dists = [abs(wy - ty) for ty in train_ys]
                nearest = dists.index(min(dists))
                if dists[nearest] <= Y_MAX_DIST:
                    word_by_train[nearest].append(w)

            for i, (y_train, num) in enumerate(train_rows):
                row_words = word_by_train[i]

                def col_words(x_min: float, x_max: float) -> list[str]:
                    ws = [w for w in row_words if x_min <= float(w["x0"]) <= x_max]
                    ws.sort(key=lambda w: (round((float(w["top"]) - y_train) / 3), float(w["x0"])))
                    return [w["text"] for w in ws]

                cat_parts = col_words(X_CAT_MIN, X_CAT_MAX)
                orig_parts = col_words(X_ORIG_MIN, X_ORIG_MAX)
                dep_parts = col_words(X_DEP_MIN, X_DEP_MAX)
                dest_parts = col_words(X_DEST_MIN, X_DEST_MAX)
                arr_parts = col_words(X_ARR_MIN, X_ARR_MAX)

                cat = cat_parts[0] if cat_parts else ""
                origin = fix_station_name(" ".join(orig_parts))
                destination = fix_station_name(" ".join(dest_parts))

                dep_t = norm_time(dep_parts[0]) if dep_parts else ""
                arr_t = norm_time(arr_parts[0]) if arr_parts else ""

                if not re.match(r"^\d{1,2}:\d{2}$", dep_t):
                    continue
                if arr_t and not re.match(r"^\d{1,2}:\d{2}$", arr_t):
                    arr_t = ""
                if not origin or not destination:
                    continue

                trains.append(GuaranteedTrain(
                    train_number=num,
                    category=cat,
                    origin=origin,
                    destination=destination,
                    dep_time=dep_t,
                    arr_time=arr_t,
                    day_type=day_type,
                    table_type=table_type,
                ))

    return trains




# ──────────────────────────────────────────────────────────────────────────────
# Funzione principale di parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_all() -> list[GuaranteedTrain]:
    all_trains: list[GuaranteedTrain] = []

    # 1. Treni regionali feriali (merged1, pagine 1-141)
    print("Parsing treni regionali FERIALI (merged1 pp.1-141)...")
    regional_feriali: list[GuaranteedTrain] = []
    current_region = ""
    current_line = ""
    with pdfplumber.open(str(PDF_MERGED1)) as pdf:
        for pg_idx in range(0, TABLE_A_START_PAGE - 1):
            page = pdf.pages[pg_idx]
            txt_full = page.extract_text(x_tolerance=5, y_tolerance=5) or ""
            # aggiorna regione
            r = extract_region_from_text(txt_full)
            if r:
                current_region = r

            trains_page, current_line = parse_regional_feriali_page_v2(
                page, current_region, current_line
            )
            regional_feriali.extend(trains_page)

    print(f"  >> {len(regional_feriali)} treni regionali feriali")
    all_trains.extend(regional_feriali)

    # 2. Tabella A (merged1, pagine 142-148)
    print("Parsing Tabella A (merged1 pp.142-148)...")
    tab_a = parse_tabella_long_dist(
        PDF_MERGED1,
        start_page=TABLE_A_START_PAGE,
        end_page=148,
        day_type="entrambi",
        table_type="tabella_a",
    )
    print(f"  >> {len(tab_a)} treni Tabella A")
    all_trains.extend(tab_a)

    # 3. Treni regionali festivi (merged2, pagine 1-40)
    print("Parsing treni regionali FESTIVI (merged2 pp.1-40)...")
    regional_festivi: list[GuaranteedTrain] = []
    current_region = ""
    with pdfplumber.open(str(PDF_MERGED2)) as pdf:
        for pg_idx in range(0, TABLE_B_START_PAGE - 1):
            page = pdf.pages[pg_idx]
            trains_page, current_region = parse_regional_festivi_page(page, current_region)
            regional_festivi.extend(trains_page)

    print(f"  >> {len(regional_festivi)} treni regionali festivi")
    all_trains.extend(regional_festivi)

    # 4. Tabella B (merged2, pagine 41+) — layout colonne diverso da Tabella A
    print("Parsing Tabella B (merged2 pp.41+)...")
    tab_b = parse_tabella_long_dist(
        PDF_MERGED2,
        start_page=TABLE_B_START_PAGE,
        end_page=999,
        day_type="festivo",
        table_type="tabella_b",
        x_num=(62, 95),
        x_cat=(112, 130),
        x_orig=(175, 296),
        x_dep=(294, 315),
        x_dest=(350, 472),
        x_arr=(471, 495),
    )
    print(f"  >> {len(tab_b)} treni Tabella B")
    all_trains.extend(tab_b)

    print(f"\nTotale treni garantiti estratti: {len(all_trains)}")
    return all_trains


if __name__ == "__main__":
    trains = parse_all()
    # Stampa campione
    print("\n--- Campione (primi 10 treni) ---")
    for t in trains[:10]:
        print(f"  [{t.day_type}/{t.table_type}] #{t.train_number} "
              f"{t.category} {t.origin} {t.dep_time} -> {t.destination} {t.arr_time}")
