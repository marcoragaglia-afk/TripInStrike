"""
AUDIT COMPLETO TripInStrike - verifica integrità dati prima della demo nazionale.
"""
import sqlite3
import re
from pathlib import Path
from collections import defaultdict

DB = Path(__file__).parent.parent / "db" / "sciopero.db"
DB_PROD = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"

# Usa il DB di produzione (quello in public/)
conn = sqlite3.connect(str(DB_PROD))
conn.row_factory = sqlite3.Row

print("=" * 72)
print("AUDIT COMPLETO TRIPINSTRIKE")
print("=" * 72)

# ── 1. CONTEGGI GENERALI ──────────────────────────────────────────────
print("\n[1] CONTEGGI GENERALI")
print("-" * 72)
for r in conn.execute("""
    SELECT table_type, day_type, COUNT(*) c
    FROM guaranteed_trains
    GROUP BY table_type, day_type
    ORDER BY table_type, day_type
"""):
    print(f"  {r['table_type']:12s} {r['day_type']:10s}  {r['c']:4d} treni")
print(f"  Stazioni:                    {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]:4d}")
print(f"  Fermate intermedie:          {conn.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]:4d}")
print(f"  Treni con fermate:           {conn.execute('SELECT COUNT(DISTINCT train_number) FROM train_stops').fetchone()[0]:4d}")

# ── 2. NOMI STAZIONE: junk residui ──────────────────────────────────
print("\n[2] STAZIONI SOSPETTE (eventuali junk residui)")
print("-" * 72)
JUNK_PATTERNS = [
    (r"^\d", "inizia con cifra"),
    (r"[a-z]\s+[a-z]+$", "frammento minuscolo finale"),
    (r"\s\d{1,2}\.\d{2}", "contiene orario"),
    (r"^[KLE]\s+", "prefix codice non rimosso"),
    (r"^Ovest\s|^Est\s", "prefix Ovest/Est"),
    (r"\s+[a-z]{3,}\s*$", "termina con parola minuscola"),
    (r"^[A-Za-z]\s[A-Z]", "frammento iniziale 1 lettera + maiuscola"),
    (r"q\.M$|\bq\.M\b", "PDF q.M"),
    (r"a YS?$", "PDF a Y/YS"),
    (r"�|\?\?", "encoding rotto"),
    (r"^\.|^,|^-", "punteggiatura iniziale"),
]
junk_found = 0
for r in conn.execute("SELECT name FROM stations"):
    name = r["name"]
    for pat, label in JUNK_PATTERNS:
        if re.search(pat, name):
            print(f"  [{label}]  {name!r}")
            junk_found += 1
            break
if junk_found == 0:
    print("  OK Nessuna stazione junk trovata")
else:
    print(f"\n  [!] Totale junk rilevati: {junk_found}")

# ── 3. STAZIONI DUPLICATE (per matching canonico) ───────────────────
print("\n[3] STAZIONI POTENZIALMENTE DUPLICATE")
print("-" * 72)
def canon(s):
    n = s.lower()
    n = re.sub(r"[\s\.\-'`]+", "", n)
    return n

groups = defaultdict(list)
for r in conn.execute("SELECT name FROM stations"):
    groups[canon(r["name"])].append(r["name"])
dups = [(k, v) for k, v in groups.items() if len(v) > 1]
if not dups:
    print("  OK Nessuna duplicata")
else:
    for k, v in dups:
        print(f"  [!] {v}")

# ── 4. ORARI INVALIDI ────────────────────────────────────────────────
print("\n[4] ORARI INVALIDI")
print("-" * 72)
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
bad = 0
for r in conn.execute("SELECT train_number, dep_time, arr_time FROM guaranteed_trains"):
    for col, v in (("dep", r["dep_time"]), ("arr", r["arr_time"])):
        if v and not TIME_RE.match(v):
            print(f"  {r['train_number']:6s}  {col}={v!r}")
            bad += 1
            if bad > 20:
                break
    if bad > 20:
        break
if bad == 0:
    print("  OK Tutti gli orari sono in formato HH:MM")

# ── 5. FERMATE: monotonia temporale ──────────────────────────────────
print("\n[5] FERMATE: violazioni di monotonia temporale (regressioni di orario)")
print("-" * 72)
def to_min(t):
    if not t or not TIME_RE.match(t): return None
    h, m = t.split(":")
    return int(h) * 60 + int(m)

violations = 0
for r in conn.execute("SELECT DISTINCT train_number FROM train_stops"):
    tn = r["train_number"]
    stops = conn.execute(
        "SELECT sequence, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    prev = None
    for s in stops:
        t = to_min(s["arrival"]) or to_min(s["departure"])
        if t is None: continue
        if prev is not None and t < prev - 60:  # >1h regressione = errore
            print(f"  Treno {tn} regressione: seq {s['sequence']} {s['station']} {prev//60:02d}:{prev%60:02d} -> {t//60:02d}:{t%60:02d}")
            violations += 1
            if violations > 10: break
        prev = t
    if violations > 10: break
if violations == 0:
    print("  OK Nessuna violazione di monotonia (escluso wrap mezzanotte)")

# ── 6. FERMATE OLTRE LA DESTINAZIONE ─────────────────────────────────
print("\n[6] FERMATE FANTASMA OLTRE LA DESTINAZIONE GARANTITA")
print("-" * 72)
def stn_canon(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())

ghost_trains = []
for t in conn.execute("""
    SELECT train_number, destination, arr_time FROM guaranteed_trains
    WHERE destination IS NOT NULL
"""):
    tn = t["train_number"]
    dest_c = stn_canon(t["destination"])
    stops = conn.execute(
        "SELECT station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    if len(stops) < 2: continue
    # Trova indice della destinazione
    dest_idx = -1
    for i, s in enumerate(stops):
        sc = stn_canon(s["station"])
        if sc == dest_c or (len(dest_c) >= 5 and dest_c in sc):
            dest_idx = i
            break
    if dest_idx >= 0 and dest_idx < len(stops) - 1:
        ghost_trains.append((tn, t["destination"], dest_idx, len(stops), stops[dest_idx+1]["station"]))
if ghost_trains:
    for tn, dest, di, total, first_ghost in ghost_trains[:15]:
        print(f"  [!] {tn:6s}  dest={dest:25s}  ferma a seq {di} ma ha {total-1-di} fermate oltre (es. {first_ghost})")
    if len(ghost_trains) > 15:
        print(f"  ... + altri {len(ghost_trains) - 15}")
else:
    print("  OK Nessun treno ha fermate oltre la destinazione garantita")

# ── 7. TRENI CHIAVE: 752, 754, 794, 795, 758, 8814, 3904, 540 ────────
print("\n[7] VERIFICA TRENI CHIAVE")
print("-" * 72)
for tn in ("752", "754", "758", "8814", "3904", "540", "1959", "794", "795"):
    rows = conn.execute(
        "SELECT origin, destination, dep_time, arr_time, table_type, day_type "
        "FROM guaranteed_trains WHERE train_number=?", (tn,)
    ).fetchall()
    if not rows:
        print(f"  [X] {tn}: NON TROVATO")
        continue
    for r in rows:
        n_stops = conn.execute(
            "SELECT COUNT(*) FROM train_stops WHERE train_number=?", (tn,)
        ).fetchone()[0]
        print(f"  {tn:5s} [{r['table_type']:10s}] {r['origin']:22s} {r['dep_time']} -> "
              f"{r['destination']:22s} {r['arr_time'] or '???':5s}  ({n_stops} fermate, {r['day_type']})")

# ── 8. DUPLICATI ESATTI ──────────────────────────────────────────────
print("\n[8] DUPLICATI ESATTI")
print("-" * 72)
dups_t = conn.execute("""
    SELECT train_number, origin, destination, dep_time, day_type, table_type, COUNT(*) c
    FROM guaranteed_trains
    GROUP BY train_number, origin, destination, dep_time, day_type, table_type
    HAVING c > 1
""").fetchall()
if dups_t:
    for r in dups_t:
        print(f"  {r['train_number']} x{r['c']}: {r['origin']} -> {r['destination']}")
else:
    print("  OK Nessun duplicato esatto")

conn.close()
print("\n" + "=" * 72)
print("FINE AUDIT")
print("=" * 72)
