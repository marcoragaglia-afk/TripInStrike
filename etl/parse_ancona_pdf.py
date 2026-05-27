"""
Parser del PDF A4_P_Ancona.pdf: estrae i treni in partenza da Ancona
con tutte le fermate intermedie.

Formato tipico di un treno:
    HH.MM[*]TI<num> <DESTINAZIONE> <HH>.<MM> <code>
    [Cat] Stazione H.MM - Stazione H.MM - Stazione H.MM -
    ... continua su più righe ...
    * NON CIRCOLA <condizioni>
    ** ALTRE NOTE
"""
import pdfplumber
import re
import sqlite3
import sys
from pathlib import Path
from dataclasses import dataclass, field

PDF = Path(r"C:\Users\El_Bl\Downloads\A4_P_Ancona.pdf")
DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Header treno: "HH.MM*TI<num> <DEST> <HH>.<MM> <code>"
# Il numero treno può avere spazi interni: "TI7 54"
HEADER_RE = re.compile(
    r"^(\d{1,2}\.\d{2})\s*\*?\s*"              # dep_time
    r"T\s*I\s*((?:\d\s?){2,6})\s+"             # train number (con eventuali spazi interni)
    r"(.+?)\s+"                                # destination
    r"(\d{1,2}\s?\.\s?\d{2})\s+"               # arrival time (con eventuali spazi)
    r"[A-Z]\s*$",                              # code letter
    re.MULTILINE,
)

# Pattern per stop: "Nome stazione HH.MM" — il tempo può avere spazi interni
STOP_RE = re.compile(
    r"([A-ZÀÈÉÌÒÙ][\w\s\.\-'`]+?)\s+"
    r"(\d{1,2}\.\d\s?\d?)"                     # tempo: "5.39" o "5.3 9"
    r"(?:\*+)?"                                # opzionale asterisco
    r"\s*-\s*"
)


@dataclass
class TrainEntry:
    train_number: str
    dep_time: str               # da Ancona
    destination: str
    dest_arr_time: str
    stops: list = field(default_factory=list)  # [(station, time), ...]


def fix_time_spaces(t: str) -> str:
    """'5.3 9' -> '5.39', '20.4 6' -> '20.46'"""
    return re.sub(r"(\d)\s+(\d)", r"\1\2", t)


def fix_station_spaces(s: str) -> str:
    """Normalizza spazi nei nomi stazione tipo 'Pesc ara' -> 'Pescara', 'TO RINO' -> 'TORINO'."""
    # Rimuovi spazi multipli
    s = re.sub(r"\s+", " ", s).strip()
    # Strip prefisso codici tipo "R A B b ", "L R a f T ", "I R a f T "
    # Sequenza all'inizio di 1-2 char + spazi + 1-2 char + ... (max 5 elementi)
    s = re.sub(r"^([A-Za-z]{1,2}\s+){2,6}", "", s)
    # Caso TUTTO MAIUSCOLO: unisce parole spezzate "TO RINO" -> "TORINO", "C ENTRALE" -> "CENTRALE"
    s = re.sub(r"\b([A-Z]{1,3})\s+([A-Z][A-Z]+)\b", r"\1\2", s)
    # Caso misto "P ORTA" -> "PORTA" (1 lettera + spazio + parola maiuscola)
    s = re.sub(r"\b([A-Z])\s+([A-Z]{3,})", r"\1\2", s)
    # Caso "A sti" -> "Asti", "F orli" -> "Forli" (1 maiuscola + spazio + parola minuscola)
    s = re.sub(r"\b([A-Z])\s+([a-zàèéìòù]{2,})", r"\1\2", s)
    # Risolve spaziature errate dentro le parole (a-z spazio a-z)
    # Pattern: lettera seguita da spazio e lettera minuscola = continua la parola
    # Es: "Pesc ara" -> "Pescara"
    fixed = []
    parts = s.split(" ")
    i = 0
    while i < len(parts):
        cur = parts[i]
        # Se la parola termina senza punteggiatura e la prossima inizia con minuscola
        # e la corrente non termina con un classificatore (di, del, ecc.)
        while i + 1 < len(parts):
            nxt = parts[i + 1]
            # Unisci se: corrente non è preposizione/articolo, prossima inizia con minuscola
            if (re.match(r"^[a-zàèéìòù]", nxt) and
                cur not in ("di", "del", "della", "dei", "delle", "da", "a", "in") and
                not cur.endswith(".") and
                len(cur) >= 2):
                # Sembra una parola spezzata
                cur = cur + nxt
                i += 1
            else:
                break
        fixed.append(cur)
        i += 1
    return " ".join(fixed)


def parse_pdf() -> list[TrainEntry]:
    """Parse l'intero PDF di Ancona."""
    entries: list[TrainEntry] = []

    with pdfplumber.open(str(PDF)) as pdf:
        full_text = ""
        for page in pdf.pages:
            txt = page.extract_text() or ""
            full_text += txt + "\n"

    # Trova tutti gli header
    matches = list(HEADER_RE.finditer(full_text))
    print(f"Trovati {len(matches)} header treni")

    for idx, m in enumerate(matches):
        dep_t = m.group(1).replace(".", ":")
        # Rimuovi spazi interni dal numero treno: "7 54" -> "754"
        train_num = re.sub(r"\s+", "", m.group(2))
        dest = m.group(3).strip()
        # Rimuovi spazi interni dall'orario di arrivo: "9 .25" -> "9.25"
        dest_arr = re.sub(r"\s+", "", m.group(4)).replace(".", ":")
        # Normalizza tempo "5:3 9" -> "5:39"
        dep_t = fix_time_spaces(dep_t)
        dest_arr = fix_time_spaces(dest_arr)
        # Aggiungi zero iniziale "5:39" -> "05:39"
        if re.match(r"^\d:\d{2}$", dep_t):
            dep_t = "0" + dep_t
        if re.match(r"^\d:\d{2}$", dest_arr):
            dest_arr = "0" + dest_arr

        # Estrai testo tra questo header e il prossimo
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        body = full_text[m.end():end]

        # Rimuovi righe di codice (1 lettera+spazi+lettere singole) e note (*/**)
        cleaned_lines = []
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):  # note
                continue
            if re.match(r"^[A-Z]$", line):  # codice "K", "L", "E"
                continue
            # codici tipo "2 R a F", "L R a f T", "I R a f T", "3 R a F T"
            if re.match(r"^[\dIL]\s+[A-Z]?\s*[a-z]?\s*[A-Z]?\s*[a-z]?\s*[A-Z]?\s*$", line):
                continue
            if re.match(r"^[KLEAEIBFGT]+\s*$", line):
                continue
            if line.startswith("pag.") or line.startswith("PAGINA") or line.startswith("="):
                continue
            if re.match(r"^4\s*DA\s+\[", line):  # "4 DA [lunedi] A [...]"
                continue
            if line in ("Ovest", "G", "T", "F", "Est"):
                continue
            cleaned_lines.append(line)

        # Unisci tutto in una stringa e trova le fermate
        body_text = " ".join(cleaned_lines)
        # Normalizza spazi multipli
        body_text = re.sub(r"\s+", " ", body_text)
        # Pre-fix: spazi interni nei tempi "5.3 9" -> "5.39", "5 .30" -> "5.30", "7. 55" -> "7.55"
        body_text = re.sub(r"(\d)\s+\.\s*(\d)", r"\1.\2", body_text)   # "5 .30" -> "5.30"
        body_text = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", body_text)       # "7. 55" -> "7.55"
        body_text = re.sub(r"(\d\.\d)\s+(\d)(?=\s)", r"\1\2", body_text)  # "5.3 9" -> "5.39"

        # DEBUG: stampa body per 752
        if train_num in ("752", "754"):
            print(f"\n--- DEBUG body per {train_num} (idx={idx}): ---")
            print(repr(body_text[:500]))
            test_stops = list(STOP_RE.finditer(body_text + " - "))
            print(f"  STOP_RE matches: {len(test_stops)}")
            for sm in test_stops[:6]:
                print(f"    {sm.group(1)!r}  {sm.group(2)!r}")
        # Trova tutte le fermate: "<station> <HH.MM>"
        stops = []
        for sm in STOP_RE.finditer(body_text + " - "):  # aggiunto separator finale
            station_raw = sm.group(1)
            time_raw = sm.group(2)
            station = fix_station_spaces(station_raw)
            time = fix_time_spaces(time_raw).replace(".", ":")  # 4.07 -> 4:07
            if re.match(r"^\d:\d{2}$", time):
                time = "0" + time
            # Validazione tempo
            tm = re.match(r"^(\d{1,2}):(\d{1,2})$", time)
            if not tm:
                continue
            h, mm = int(tm.group(1)), int(tm.group(2))
            if h > 23 or mm > 59:
                continue
            time = f"{h:02d}:{int(mm):02d}"
            if len(station) < 3 or len(station) > 35:
                continue
            stops.append((station, time))

        # Tronca la lista appena un tempo è < di quello precedente
        # (indica fine del treno corrente / inizio variante successiva)
        def parse_minutes(t):
            h, mm = t.split(":")
            return int(h) * 60 + int(mm)
        clean_stops = []
        last_t = parse_minutes(dep_t)
        for station, t in stops:
            tm = parse_minutes(t)
            # Permettiamo wrap mezzanotte (1 volta)
            if tm < last_t - 60:  # decreasing by more than 1h = junk
                break
            if tm < last_t:
                # piccola regressione, salta questa fermata
                continue
            clean_stops.append((station, t))
            last_t = tm
        stops = clean_stops

        entry = TrainEntry(
            train_number=train_num,
            dep_time=dep_t,
            destination=fix_station_spaces(dest),
            dest_arr_time=dest_arr,
            stops=stops,
        )
        entries.append(entry)

    return entries


def main():
    print("Parsing PDF Ancona...")
    entries = parse_pdf()
    print(f"\nTotale train entries estratti: {len(entries)}")

    # Mostra esempio: 752 e 754
    for tn_target in ("752", "754", "758", "3904", "4205", "8806"):
        for e in entries:
            if e.train_number == tn_target:
                print(f"\n=== Treno {tn_target}: Ancona {e.dep_time} -> {e.destination} {e.dest_arr_time} ===")
                for station, time in e.stops:
                    print(f"  {station:30s}  {time}")
                break

    # Salva su DB: solo per treni che esistono già in guaranteed_trains
    print("\n" + "=" * 60)
    print("Inserimento fermate nel DB...")
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    inserted = 0
    skipped = 0
    no_train = 0
    sys.path.insert(0, str(Path(__file__).parent))
    from build_db import normalize_station_name

    # Alias stazioni per matching con il DB esistente
    STATION_ALIASES = {
        "MILANO CENTRALE": "Milano Centrale",
        "TORINO PORTA NUOVA": "Torino Porta Nuova",
        "ROMA TERMINI": "Roma Termini",
        "BOLOGNA CENTRALE": "Bologna Centrale",
        "NAPOLI CENTRALE": "Napoli Centrale",
        "LECCE": "Lecce",
        "BARI CENTRALE": "Bari Centrale",
        "PIACENZA": "Piacenza",
        "PESCARA": "Pescara Centrale",
        "VENEZIA SANTA LUCIA": "Venezia Santa Lucia",
        "ASCOLI PICENO": "Ascoli Piceno",
        "PESARO": "Pesaro",
        "RIMINI": "Rimini",
        "FABRIANO": "Fabriano",
        "JESI": "Jesi",
        "SULMONA": "Sulmona",
        "FOLIGNO": "Foligno",
        "S.BENEDETTO DEL T.": "S. Benedetto d.T",
        "CASTELPLANIO-C.": "Castelplanio-Cupra m.",
        "FOSSATO DI VICO-G.": "Fossato di Vico-G.",
        "Reggio E. AV Medio P": "Reggio Emilia AV",
        "Cattolica-S.G.-G.": "Cattolica S.Giovanni Gabicce",
        "S.Benedetto del T.": "S. Benedetto d.T",
        "Castelplanio-C.": "Castelplanio-Cupra m.",
        "Civitanova Marche": "Civitanova-M.Montegr.",
        "Marotta-Mondolfo": "Marotta-Mondolfo",
        "Pescara": "Pescara Centrale",
    }
    def apply_alias(name):
        return STATION_ALIASES.get(name, name)

    # Dedup entries per (train_number, dep_time): l'ultima vince
    by_key: dict[tuple[str, str], TrainEntry] = {}
    for e in entries:
        by_key[(e.train_number, e.dep_time)] = e

    for (tn, dep), entry in by_key.items():
        # Verifica esistenza del treno in DB
        train = conn.execute(
            "SELECT id, origin, destination, dep_time FROM guaranteed_trains WHERE train_number=?",
            (tn,)
        ).fetchone()
        if not train:
            no_train += 1
            continue

        # Cancella fermate precedenti
        conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))

        # Inserisci tutte le fermate (origine Ancona è inclusa come prima)
        # Costruisci sequence completa: Ancona@dep_time, poi le fermate del PDF, poi destinazione
        full_stops = [("Ancona", entry.dep_time, "boarding")]
        for station, t in entry.stops:
            full_stops.append((station, t, "intermediate"))
        # Aggiungi destinazione finale
        full_stops.append((entry.destination, entry.dest_arr_time, "destination"))

        seq = 0
        seen_stations = set()
        for station, time, kind in full_stops:
            station = apply_alias(station)
            # Skip Ancona se è già origine del treno (per non duplicare)
            if kind == "boarding" and (train["origin"] or "").lower().startswith("ancona"):
                continue
            if station in seen_stations:
                continue
            seen_stations.add(station)

            # Tempi: per fermata intermedia, usiamo come arrival
            arr = time
            dep_t = time
            if kind == "destination":
                dep_t = None
            elif kind == "boarding":
                arr = None
            try:
                conn.execute(
                    "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tn, station, seq, arr, dep_t)
                )
                seq += 1
            except sqlite3.IntegrityError:
                pass
            # Aggiungi a stations se manca
            conn.execute(
                "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                (station, normalize_station_name(station))
            )

        # Aggiorna arr_time del treno se manca
        if not conn.execute("SELECT arr_time FROM guaranteed_trains WHERE id=?", (train["id"],)).fetchone()[0]:
            conn.execute("UPDATE guaranteed_trains SET arr_time=? WHERE id=?",
                         (entry.dest_arr_time, train["id"]))

        inserted += 1

    conn.commit()
    print(f"  Treni con fermate aggiornate: {inserted}")
    print(f"  Treni non in DB (saltati):    {no_train}")
    print(f"  Stazioni: {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]}")
    print(f"  Fermate:  {conn.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]}")

    # Verifica 752 e 754
    for tn in ("752", "754"):
        print(f"\n=== Verifica DB treno {tn} ===")
        t = conn.execute(
            "SELECT origin, destination, dep_time, arr_time FROM guaranteed_trains WHERE train_number=?",
            (tn,)
        ).fetchone()
        if t:
            print(f"  guaranteed: {t['origin']} -> {t['destination']}  dep={t['dep_time']} arr={t['arr_time']}")
        for r in conn.execute(
            "SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number=? ORDER BY sequence",
            (tn,)
        ):
            print(f"  seq={r['sequence']:2d}  {r['station']:25s}  arr={r['arrival'] or '':5s}  dep={r['departure'] or '':5s}")

    conn.close()


if __name__ == "__main__":
    main()
