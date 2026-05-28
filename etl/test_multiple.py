"""Test multiple route combinations rapido."""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

GENERIC_PREFIXES = {'SAN','SANTA','SANTO','SS','PORTO','TORRE','VILLA','CAPO',
    'REGGIO','MONTE','MONTI','CASTEL','CASTELLO','CAMPO','COLLE','BORGO','CAVA','PIEVE','ROCCA'}

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
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    wa = [w for w in na.split() if w]
    wb = [w for w in nb.split() if w]
    if not wa or not wb: return False
    shorter, longer = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if all(w == longer[i] for i, w in enumerate(shorter)): return True
    if wa[0] not in GENERIC_PREFIXES and wa[0] == wb[0]: return True
    return False

def find_stop_leg(stops, board_st, alight_st):
    if not stops: return None
    board_idx = next((i for i, s in enumerate(stops) if station_match(s["station"], board_st)), -1)
    alight_idx = next((i for i, s in enumerate(stops) if station_match(s["station"], alight_st)), -1)
    if board_idx == -1 or alight_idx == -1 or board_idx >= alight_idx: return None
    bt = stops[board_idx]["departure"] or stops[board_idx]["arrival"]
    at = stops[alight_idx]["arrival"] or stops[alight_idx]["departure"]
    return {"boardTime": bt, "alightTime": at, "boardStation": stops[board_idx]["station"], "alightStation": stops[alight_idx]["station"]}

def find_direct(from_, to_, day):
    trains = conn.execute("""
        SELECT * FROM guaranteed_trains WHERE day_type=? OR day_type='entrambi'
    """, (day,)).fetchall()
    results = []
    for t in trains:
        if not t["dep_time"]: continue
        stops = conn.execute("SELECT * FROM train_stops WHERE train_number=? ORDER BY sequence", (t["train_number"],)).fetchall()
        primary = station_match(t["origin"], from_) and station_match(t["destination"], to_)
        if primary:
            arr = t["arr_time"] or ""
            results.append((t["train_number"], t["origin"], from_, t["dep_time"], to_, arr or "???"))
        elif stops:
            has_origin = any(station_match(s["station"], t["origin"]) for s in stops)
            has_dest = any(station_match(s["station"], t["destination"]) for s in stops)
            full = []
            if not has_origin:
                full.append({"station": t["origin"], "arrival": None, "departure": t["dep_time"]})
            full.extend(stops)
            if not has_dest:
                full.append({"station": t["destination"], "arrival": t["arr_time"], "departure": None})
            leg = find_stop_leg(full, from_, to_)
            if leg:
                results.append((t["train_number"], t["origin"]+"->"+t["destination"], leg["boardStation"], leg["boardTime"], leg["alightStation"], leg["alightTime"] or "???"))
    return results

routes = [
    ('Ancona', 'Bari Centrale'),
    ('Ancona', 'Foggia'),
    ('Ancona', 'Lecce'),
    ('Ancona', 'Pescara Centrale'),
    ('Ancona', 'Milano Centrale'),
    ('Ancona', 'Bologna Centrale'),
    ('Ancona', 'Roma Termini'),
    ('Ancona', 'Reggio Emilia'),
    ('Ancona', 'Venezia Santa Lucia'),
    ('Pesaro', 'Bari Centrale'),
    ('Bologna Centrale', 'Bari Centrale'),
]
for f, t in routes:
    d = find_direct(f, t, 'feriale')
    print(f"\n{f} -> {t} (DIRETTI feriale): {len(d)}")
    for r in d[:5]:
        print(f"  {r[0]:6s}  [{r[1][:22]:22s}]  {r[2][:18]:18s}@{r[3]} -> {r[4][:18]:18s}@{r[5]}")

conn.close()
