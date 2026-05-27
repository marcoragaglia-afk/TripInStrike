"""
Parser del PDF A4_A_Ancona.pdf: estrae i treni in ARRIVO ad Ancona
con tutte le fermate intermedie.

Formato:
  HH.MM[*]TI<num> <ORIGINE> <HH>.<MM> <code>
  Stazione H.MM - Stazione H.MM - ...  (in ordine temporale)
  * NON CIRCOLA <condizioni>
"""
import pdfplumber
import re
import sqlite3
import sys
from pathlib import Path
from dataclasses import dataclass, field

PDF = Path(r"C:\Users\El_Bl\Downloads\A4_A_Ancona.pdf")
DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Header treno (arrivi): "HH.MM*TI<num> <ORIGINE> <HH>.<MM> <code>"
HEADER_RE = re.compile(
    r"^(\d{1,2}\.\d{2})\s*\*?\s*"
    r"T\s*I\s*((?:\d\s?){2,6})\s+"
    r"(.+?)\s+"
    r"(\d{1,2}\s?\.\s?\d{2})\s+"
    r"[A-Z]\s*$",
    re.MULTILINE,
)

# Pattern per stop
STOP_RE = re.compile(
    r"([A-ZÀÈÉÌÒÙ][\w\s\.\-'`]+?)\s+"
    r"(\d{1,2}\.\d\s?\d?)"
    r"(?:\*+)?"
    r"\s*-\s*"
)


@dataclass
class TrainArrival:
    train_number: str
    arr_time_ancona: str        # arrivo ad Ancona
    origin: str                 # stazione di origine
    origin_dep_time: str        # partenza dall'origine
    stops: list = field(default_factory=list)  # intermediate stops


def fix_time_spaces(t: str) -> str:
    return re.sub(r"(\d)\s+(\d)", r"\1\2", t)


def fix_station_spaces(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # Fix encoding: Forl� -> Forli
    s = s.replace("�", "i").replace("Forl�", "Forli")
    # Strip leading code prefix tipo "K Foo", "L Bar"
    s = re.sub(r"^[KLEABFGT]\s+", "", s)
    s = re.sub(r"^([A-Za-z]{1,2}\s+){2,6}", "", s)
    # Unisci frammenti UPPERCASE: "PIACEN ZA" -> "PIACENZA" (suffisso 2-3 char)
    s = re.sub(r"\b([A-Z]{3,})\s+([A-Z]{2,3})\b", r"\1\2", s)
    s = re.sub(r"\b([A-Z]{1,3})\s+([A-Z][A-Z]+)\b", r"\1\2", s)
    # Caso "P ORTA" -> "PORTA"
    s = re.sub(r"\b([A-Z])\s+([A-Z]{3,})", r"\1\2", s)
    # Caso "A sti" -> "Asti", "F orli" -> "Forli"
    s = re.sub(r"\b([A-Z])\s+([a-zàèéìòù]{2,})", r"\1\2", s)
    # Casi noti di città spezzate da PDF (pattern specifici)
    KNOWN_FIXES = {
        r"\bImo\s+la\b": "Imola",
        r"\bFidenz\s+a\b": "Fidenza",
        r"\bForl\s+i\b": "Forli",
        r"\bS\.\s*Benedettodel\s+T\.?": "S. Benedetto d.T",
        r"\bS\.Benedettodel\s+T\.?": "S. Benedetto d.T",
        r"\bScernedi\s+Pineto\b": "Scerne di Pineto",
        r"\bRosetodegli\s+Abruzzi\b": "Roseto degli Abruzzi",
        r"\bPortod'Ascoli\b": "Porto d'Ascoli",
        r"\bCupramarittima\b": "Cupra Marittima",
        r"\bChiet\s+i\b": "Chieti",
        r"\bChietii?\b": "Chieti",
        r"\bMonte\s+silvano\b": "Montesilvano",
        r"\bScafa-S\.Valentino\b": "Scafa-San Valentino",
        r"\bTerm\s+oli\b": "Termoli",
        r"\bPesc\s+ara\b": "Pescara",
        r"\bP iacen za\b|\bPiacen\s+za\b": "Piacenza",
        r"\bMolfetta\b": "Molfetta",
    }
    for pat, repl in KNOWN_FIXES.items():
        s = re.sub(pat, repl, s)
    fixed = []
    parts = s.split(" ")
    PREPS = {"di", "del", "della", "dei", "delle", "da", "a", "in", "degli",
             "dell'", "d'", "su", "sul", "sull'", "sulla", "alla", "al", "ai",
             "agli", "alle", "il", "lo", "la"}
    # Parole intere note (parte di nomi compound: "Scerne di Pineto" -> "Pineto" intero)
    REAL_LOWER_WORDS = {
        "abruzzi", "ascoli", "pineto", "tronto", "elpidio", "giorgio", "vittore",
        "quirico", "lucia", "centrale", "porta", "nuova", "marittima", "marche",
        "tadino", "novella", "alpe", "lido", "stadio", "aspio", "centrale",
        "festivi", "feriale", "tronto", "tibu", "torrette",
    }
    i = 0
    while i < len(parts):
        cur = parts[i]
        while i + 1 < len(parts):
            nxt = parts[i + 1]
            nxt_lower = nxt.lower().rstrip(".,;:'")
            # Stop se la prossima è una preposizione
            if nxt_lower in PREPS:
                break
            # Stop se la prossima è parola completa nota
            if nxt_lower in REAL_LOWER_WORDS:
                break
            # Stop se la prossima inizia con maiuscola (nome proprio separato)
            if re.match(r"^[A-Z]", nxt):
                break
            # Stop se ha apostrofo subito dopo prima lettera ("d'Ascoli")
            if "'" in nxt[:2]:
                break
            # Solo se la corrente non finisce con punto e ha almeno 2 lettere
            if not cur.endswith(".") and len(cur) >= 2:
                cur = cur + nxt
                i += 1
            else:
                break
        fixed.append(cur)
        i += 1
    return " ".join(fixed)


def parse_pdf() -> list[TrainArrival]:
    entries: list[TrainArrival] = []
    with pdfplumber.open(str(PDF)) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    matches = list(HEADER_RE.finditer(full_text))
    print(f"Trovati {len(matches)} header treni in arrivo")

    for idx, m in enumerate(matches):
        arr_anc = m.group(1).replace(".", ":")
        train_num = re.sub(r"\s+", "", m.group(2))
        origin = m.group(3).strip()
        orig_dep = re.sub(r"\s+", "", m.group(4)).replace(".", ":")

        for t_var in (arr_anc, orig_dep):
            pass
        arr_anc = fix_time_spaces(arr_anc.replace(":", "."))
        arr_anc = arr_anc.replace(".", ":")
        if re.match(r"^\d:\d{2}$", arr_anc):
            arr_anc = "0" + arr_anc
        if re.match(r"^\d:\d{2}$", orig_dep):
            orig_dep = "0" + orig_dep

        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        body = full_text[m.end():end]

        cleaned_lines = []
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            if re.match(r"^[A-Z]$", line):
                continue
            if len(line) <= 15 and re.match(r"^[\dILKEABFGTRabftcv\s]+$", line):
                words = line.split()
                if all(len(w) <= 2 for w in words):
                    continue
            if line.startswith("pag.") or line.startswith("PAGINA") or line.startswith("="):
                continue
            if re.match(r"^4\s*DA\s+\[", line):
                continue
            if line in ("Ovest", "G", "T", "F", "Est"):
                continue
            cleaned_lines.append(line)

        body_text = " ".join(cleaned_lines)
        body_text = re.sub(r"\s+", " ", body_text)
        body_text = re.sub(r"(\d)\s+\.\s*(\d)", r"\1.\2", body_text)
        body_text = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", body_text)
        body_text = re.sub(r"(\d\.\d)\s+(\d)(?=\s)", r"\1\2", body_text)

        stops = []
        for sm in STOP_RE.finditer(body_text + " - "):
            station = fix_station_spaces(sm.group(1))
            time = fix_time_spaces(sm.group(2)).replace(".", ":")
            if re.match(r"^\d:\d{2}$", time):
                time = "0" + time
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

        # Tronca quando il tempo diventa "scoerente" (next dovrebbe essere arr_anc)
        # I treni in arrivo ad Ancona: stops sono in ordine cronologico, finiscono prima di arr_anc.
        # Possiamo permettere wrap mezzanotte 1 sola volta.
        def to_min(t):
            h, mm = t.split(":")
            return int(h) * 60 + int(mm)

        if stops:
            arr_anc_min = to_min(arr_anc)
            orig_dep_min = to_min(orig_dep)
            clean_stops = []
            prev = orig_dep_min
            wraps_allowed = 0 if orig_dep_min <= arr_anc_min else 1  # treno notturno?
            wraps = 0
            for station, t in stops:
                tm = to_min(t)
                if tm < prev:
                    if tm + 1440 - prev < 60 and wraps < wraps_allowed:
                        wraps += 1
                        tm += 1440
                    elif tm < prev - 60:
                        # grande regressione, fine sequenza
                        break
                    else:
                        continue
                clean_stops.append((station, t))
                prev = tm
            stops = clean_stops

        entries.append(TrainArrival(
            train_number=train_num,
            arr_time_ancona=arr_anc,
            origin=fix_station_spaces(origin),
            origin_dep_time=orig_dep,
            stops=stops,
        ))
    return entries


def main():
    print("Parsing PDF arrivi a Ancona...")
    entries = parse_pdf()
    print(f"Totale entries: {len(entries)}")

    # Mostra alcuni esempi (treni regionali in arrivo)
    for tn in ("4202", "4222", "4224", "3905", "3929", "3931", "23752", "23839"):
        for e in entries:
            if e.train_number == tn:
                print(f"\n=== Treno {tn}: {e.origin} {e.origin_dep_time} -> Ancona {e.arr_time_ancona} ===")
                for st, t in e.stops:
                    print(f"  {st:30s}  {t}")
                break

    # Inserisci nel DB: solo treni esistenti con destinazione Ancona
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    sys.path.insert(0, str(Path(__file__).parent))
    from build_db import normalize_station_name

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
        "TERMOLI": "Termoli",
        "TERAMO": "Teramo",
        "S.BENEDETTO DEL T.": "S. Benedetto d.T",
        "S.Benedetto del T.": "S. Benedetto d.T",
        "Castelplanio-C.": "Castelplanio-Cupra m.",
        "Civitanova Marche": "Civitanova-M.Montegr.",
        "Pescara": "Pescara Centrale",
        "Bologna Centrale": "Bologna Centrale",
    }
    def apply_alias(name):
        return STATION_ALIASES.get(name, name)

    # Dedup: prendi prima occorrenza
    by_tn: dict[str, TrainArrival] = {}
    for e in entries:
        if e.train_number not in by_tn:
            by_tn[e.train_number] = e

    inserted = 0
    not_found = 0
    no_marche = 0

    # Stazioni Marche / arrivi che ci interessano
    MARCHE_DESTS = re.compile(r"ancona|fabriano|jesi|ascoli|civitanova|macerata|pesaro|rimini", re.I)

    for tn, e in by_tn.items():
        # Cerca il treno nel DB - DEVE esistere come guaranteed
        train = conn.execute(
            "SELECT id, origin, destination, dep_time, arr_time, table_type FROM guaranteed_trains WHERE train_number=?",
            (tn,)
        ).fetchone()
        if not train:
            not_found += 1
            continue

        # Solo se l'origine in DB combacia (approssimativamente) con quella del PDF
        # E destinazione è in zona Marche/Ancona (così sappiamo che è un treno utile)
        db_dest = (train["destination"] or "").lower()
        db_origin = (train["origin"] or "").lower()

        # Per regionali: prendiamo solo quelli con destinazione in Marche
        if train["table_type"] == "regionale" and not MARCHE_DESTS.search(db_dest):
            no_marche += 1
            continue

        # Costruisci la sequenza completa: origin -> intermediate -> Ancona
        # Se il treno DB ha già delle fermate (dalla parse_ancona_pdf precedente),
        # le manteniamo solo se sono per treni passanti per Ancona; altrimenti sostituiamo.
        # Per i treni in arrivo (es. 4202 Pescara->Ancona), sostituiamo tutto.

        # Sostituisci solo se il treno DB termina a/passa per Ancona o stazione marchigiana
        # come destinazione (non se è un AV che passa via)
        if "ancona" not in db_dest:
            no_marche += 1
            continue

        # Cancella fermate esistenti
        conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,))

        # Aggiungi fermate: origine + intermediate + Ancona
        full = [(apply_alias(e.origin), e.origin_dep_time, "boarding")]
        for st, t in e.stops:
            full.append((apply_alias(st), t, "intermediate"))
        full.append(("Ancona", e.arr_time_ancona, "destination"))

        seq = 0
        seen = set()
        for station, time, kind in full:
            # Skip origine se è già origin del treno
            if kind == "boarding" and station.lower() == db_origin:
                continue
            # Skip Ancona se non è la destinazione del treno
            if kind == "destination" and "ancona" not in db_dest:
                continue
            if station in seen:
                continue
            seen.add(station)
            arr = time if kind != "boarding" else None
            dep_t = time if kind != "destination" else None
            try:
                conn.execute(
                    "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tn, station, seq, arr, dep_t)
                )
                seq += 1
            except sqlite3.IntegrityError:
                pass
            conn.execute(
                "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                (station, normalize_station_name(station))
            )

        # Aggiorna dep_time / arr_time del treno se mancanti
        if not train["dep_time"]:
            conn.execute("UPDATE guaranteed_trains SET dep_time=? WHERE id=?",
                         (e.origin_dep_time, train["id"]))
        if not train["arr_time"]:
            conn.execute("UPDATE guaranteed_trains SET arr_time=? WHERE id=?",
                         (e.arr_time_ancona, train["id"]))

        inserted += 1

    conn.commit()
    print(f"\nFermate aggiunte ai treni in arrivo ad Ancona: {inserted}")
    print(f"Treni non in DB: {not_found}")
    print(f"Treni non Marche/non-Ancona: {no_marche}")

    # Verifica esempi
    print("\n=== Verifica esempi DB ===")
    for tn in ("4202", "3905", "3929"):
        t = conn.execute("SELECT origin, destination, dep_time, arr_time FROM guaranteed_trains WHERE train_number=?", (tn,)).fetchone()
        if t:
            print(f"\nTreno {tn}: {t['origin']} {t['dep_time']} -> {t['destination']} {t['arr_time']}")
            for r in conn.execute("SELECT sequence, station, arrival, departure FROM train_stops WHERE train_number=? ORDER BY sequence", (tn,)):
                print(f"  seq={r['sequence']:2d}  {r['station']:30s}  arr={r['arrival'] or '':5s}  dep={r['departure'] or '':5s}")

    conn.close()


if __name__ == "__main__":
    main()
