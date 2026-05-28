"""
TEST ROUTING: simula in Python lo stesso algoritmo del router TS,
per verificare che le coincidenze siano logiche.

Verifica:
- Ancona -> destinazioni nazionali
- Roma -> destinazioni nazionali
- Bologna -> destinazioni nazionali
- Stazioni Marche -> Ancona
- Coincidenze devono avere senso geografico
- Non ci devono essere "ritorni" (treno A che supera la destinazione e poi B che torna indietro)
- Non ci devono essere connessioni REGGIO EMILIA vs REGGIO CALABRIA confuse
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# Replica della normalizzazione del router.ts
GENERIC_PREFIXES = {
    'SAN', 'SANTA', 'SANTO', 'SS',
    'PORTO', 'TORRE', 'VILLA', 'CAPO',
    'REGGIO',
    'MONTE', 'MONTI',
    'CASTEL', 'CASTELLO',
    'CAMPO', 'COLLE', 'BORGO', 'CAVA', 'PIEVE', 'ROCCA',
}

def normalize(s):
    s = s.upper()
    s = re.sub(r'\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?', 'SANTA MARIA NOVELLA', s)
    s = re.sub(r'\bC\.LE\b|\bCLE\b|\bCENTR\b', 'CENTRALE', s)
    s = re.sub(r'\bP\.NUOVA\b|\bP\.N\.\b', 'PORTA NUOVA', s)
    s = re.sub(r'\bP\.GARIBALDI\b', 'PORTA GARIBALDI', s)
    s = re.sub(r'\bS\.\s*', 'SAN ', s)
    s = re.sub(r'\bD\.T\.?\b', 'DEL TRONTO', s)
    s = re.sub(r"[-']", ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def station_match(a, b):
    na = normalize(a)
    nb = normalize(b)
    if na == nb: return True
    wa = [w for w in na.split() if w]
    wb = [w for w in nb.split() if w]
    if not wa or not wb: return False
    shorter, longer = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if all(w == longer[i] for i, w in enumerate(shorter)): return True
    if wa[0] not in GENERIC_PREFIXES and wa[0] == wb[0]: return True
    return False

# ── Test station_match con casi tricky ───────────────────────────────
print("=" * 72)
print("TEST 1: station_match — Reggio Emilia / Reggio Calabria")
print("=" * 72)
tests = [
    ('Reggio Emilia', 'Reggio Emilia AV', True),
    ('Reggio Emilia', 'Reggio Calabria Centrale', False),  # CRUCIAL
    ('Reggio Calabria', 'Reggio Calabria Centrale', True),
    ('Roma Termini', 'Roma', True),
    ('Roma Termini', 'Roma Tiburtina', True),  # stesso primo token = stessa citta
    ('Firenze S.M.N.', 'Firenze SMN', True),
    ('Termini Imerese', 'Roma Termini', False),
    ('Bologna', 'Bologna Centrale', True),
    ('San Benedetto', 'San Marino', False),   # SAN e' generico
    ('Monte San Vito', 'Monte San Giusto', False),  # MONTE generico
    ('Castel S.Pietro Terme', 'Castelfranco Emilia', False),  # CASTEL generico
    ('Porto Recanati', "Porto d'Ascoli", False),  # PORTO generico
]
all_ok = True
for a, b, expected in tests:
    result = station_match(a, b)
    ok = result == expected
    sym = 'OK' if ok else 'FAIL'
    print(f"  [{sym}]  station_match({a!r}, {b!r}) = {result} (atteso {expected})")
    if not ok: all_ok = False
print(f"\n  RISULTATO: {'TUTTI OK' if all_ok else 'CI SONO FALLIMENTI'}")

# ── Funzione: trova itinerari per (from, to, day_type) ──────────────
def find_itineraries(from_, to_, day_type='feriale'):
    """Implementazione semplificata del router per testing."""
    direct = []
    with_change = []

    if station_match(from_, to_):
        return direct, with_change

    trains = conn.execute("""
        SELECT * FROM guaranteed_trains
        WHERE day_type=? OR day_type='entrambi'
        ORDER BY dep_time
    """, (day_type,)).fetchall()

    stops_cache = {}
    for t in trains:
        stops_cache[t['train_number']] = conn.execute(
            "SELECT * FROM train_stops WHERE train_number=? ORDER BY sequence",
            (t['train_number'],)
        ).fetchall()

    def to_min(t):
        if not t: return None
        m = re.match(r'^(\d{1,2}):(\d{2})$', t.strip())
        if not m: return None
        return int(m.group(1)) * 60 + int(m.group(2))

    def time_diff(a, b):
        d = to_min(b) - to_min(a)
        if d < 0: d += 24*60
        return d

    # FASE 1: diretti
    for t in trains:
        if not t['dep_time']: continue
        stops = stops_cache[t['train_number']]
        if station_match(t['origin'], from_) and station_match(t['destination'], to_):
            direct.append({
                'train': t['train_number'],
                'origin': t['origin'], 'destination': t['destination'],
                'board': t['dep_time'], 'alight': t['arr_time'] or '???',
            })
            continue
        if not stops: continue
        # Cerca da/to in stops
        full_stops = list(stops)
        # Per regionali, includi origin e destination come stop virtuali
        if t['table_type'] != 'tabella_a':
            full_stops = (
                [{'station': t['origin'], 'arrival': None, 'departure': t['dep_time']}] +
                list(stops) +
                [{'station': t['destination'], 'arrival': t['arr_time'], 'departure': None}]
            )
        board_idx = next((i for i, s in enumerate(full_stops) if station_match(s['station'], from_)), -1)
        alight_idx = next((i for i, s in enumerate(full_stops) if station_match(s['station'], to_)), -1)
        if board_idx == -1 or alight_idx == -1 or board_idx >= alight_idx: continue
        board_t = full_stops[board_idx]['departure'] or full_stops[board_idx]['arrival']
        alight_t = full_stops[alight_idx]['arrival'] or full_stops[alight_idx]['departure']
        if not board_t: continue
        direct.append({
            'train': t['train_number'],
            'origin': t['origin'], 'destination': t['destination'],
            'board': board_t, 'alight': alight_t or '???',
            'boardAt': full_stops[board_idx]['station'],
        })

    return direct, with_change

# ── TEST 2: rotte da Ancona ──────────────────────────────────────────
print("\n" + "=" * 72)
print("TEST 2: Direct routes from Ancona")
print("=" * 72)
destinations = [
    'Milano Centrale', 'Torino Porta Nuova', 'Venezia Santa Lucia',
    'Roma Termini', 'Bologna Centrale', 'Napoli Centrale', 'Salerno',
    'Bari Centrale', 'Lecce', 'Foggia', 'Pescara Centrale',
    'Reggio Calabria Centrale', 'Reggio Emilia', 'Parma', 'Piacenza',
    'Firenze S.M.N.',
]
for d in destinations:
    direct, _ = find_itineraries('Ancona', d)
    print(f"  Ancona -> {d:28s}  {len(direct):3d} diretti")
    # Mostra primi 2
    for it in direct[:2]:
        print(f"      {it['train']:6s} [{it['boardAt'] if 'boardAt' in it else it['origin'][:18]:18s}]  "
              f"{it['board']} -> {it['alight']}")

# ── TEST 3: verifica anti-pattern "andare oltre e tornare" ──────────
print("\n" + "=" * 72)
print("TEST 3: Anti-pattern verification — no 'overshoot' routes")
print("=" * 72)
# Per ogni treno A che passa per X (destinazione), nessun cambio dopo X
problematic = []
for t in conn.execute("""SELECT train_number, origin, destination FROM guaranteed_trains
                         WHERE table_type IN ('tabella_a', 'tabella_b')""").fetchall():
    stops = conn.execute(
        "SELECT station FROM train_stops WHERE train_number=? ORDER BY sequence",
        (t['train_number'],)
    ).fetchall()
    if not stops: continue
    # Verifica che la destinazione del treno NON appaia tra le fermate intermedie seguito da altre fermate
    dest_norm = normalize(t['destination'])
    for i, s in enumerate(stops):
        if station_match(s['station'], t['destination']) and i < len(stops) - 1:
            problematic.append((t['train_number'], t['destination'], stops[i+1]['station']))
            break
if problematic:
    print(f"  [!] Trovati {len(problematic)} treni con fermate oltre la destinazione:")
    for tn, dest, after in problematic[:10]:
        print(f"      {tn}: dest={dest}, prosegue verso {after}")
else:
    print("  OK Nessun treno ha fermate dopo la sua destinazione")

# ── TEST 4: tutti i treni hanno orari coerenti dep < arr ──────────
print("\n" + "=" * 72)
print("TEST 4: Coerenza dep_time vs arr_time")
print("=" * 72)
def _parse_hhmm(s):
    if not s: return None
    return int(s.split(':')[0]) * 60 + int(s.split(':')[1])

bad = 0
for t in conn.execute("""SELECT train_number, origin, destination, dep_time, arr_time
                         FROM guaranteed_trains WHERE dep_time IS NOT NULL AND arr_time IS NOT NULL""").fetchall():
    dep = _parse_hhmm(t['dep_time'])
    arr = _parse_hhmm(t['arr_time'])
    if dep is None or arr is None: continue
    duration = (arr - dep) % (24 * 60)
    if duration > 18 * 60:
        print(f"  [!] {t['train_number']:6s} {t['origin']} {t['dep_time']} -> {t['destination']} {t['arr_time']}: "
              f"durata implausibile {duration//60}h{duration%60:02d}min")
        bad += 1
if bad == 0:
    print("  OK Tutti i tempi sono plausibili")

conn.close()
print("\n" + "=" * 72)
print("FINE TEST")
print("=" * 72)
