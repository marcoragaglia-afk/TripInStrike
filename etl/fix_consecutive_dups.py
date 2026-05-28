"""
Fix avanzato:
1. Rimuove fermate duplicate consecutive (stessa stazione due volte di fila)
2. Tronca aggressivamente le fermate dopo la destinazione del treno
   (anche se la destinazione appare con nome leggermente diverso nelle stops)
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

GENERIC_PREFIXES = {
    'SAN', 'SANTA', 'SANTO', 'SS', 'PORTO', 'TORRE', 'VILLA', 'CAPO',
    'REGGIO', 'MONTE', 'MONTI', 'CASTEL', 'CASTELLO',
    'CAMPO', 'COLLE', 'BORGO', 'CAVA', 'PIEVE', 'ROCCA',
}

def normalize(s):
    s = s.upper()
    s = re.sub(r'\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?', 'SANTA MARIA NOVELLA', s)
    s = re.sub(r'\bC\.LE\b|\bCLE\b|\bCENTR\b', 'CENTRALE', s)
    s = re.sub(r'\bP\.NUOVA\b|\bP\.N\.\b', 'PORTA NUOVA', s)
    s = re.sub(r'\bS\.\s*', 'SAN ', s)
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

# ── FIX 1: rimuovi fermate duplicate consecutive ──────────────────
print("[FIX A] Rimuovi fermate duplicate consecutive (stessa stazione 2x di fila)")
duped = 0
for r in conn.execute("SELECT DISTINCT train_number FROM train_stops").fetchall():
    tn = r["train_number"]
    stops = conn.execute(
        "SELECT id, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence",
        (tn,)
    ).fetchall()
    if len(stops) < 2: continue
    to_delete = []
    for i in range(1, len(stops)):
        if station_match(stops[i-1]["station"], stops[i]["station"]):
            # Tieni quello con più info; elimina l'altro
            prev_info = (stops[i-1]["arrival"] or "") + (stops[i-1]["departure"] or "")
            curr_info = (stops[i]["arrival"] or "") + (stops[i]["departure"] or "")
            if len(curr_info) >= len(prev_info):
                to_delete.append(stops[i-1]["id"])
            else:
                to_delete.append(stops[i]["id"])
    for sid in to_delete:
        conn.execute("DELETE FROM train_stops WHERE id=?", (sid,))
        duped += 1
print(f"  Fermate duplicate consecutive eliminate: {duped}")

# ── FIX 2: troncamento aggressivo oltre destinazione ──────────────
print("\n[FIX B] Truncamento aggressivo oltre destinazione (uso station_match)")
truncated = 0
for t in conn.execute("""
    SELECT train_number, destination FROM guaranteed_trains
    WHERE destination IS NOT NULL
""").fetchall():
    tn = t["train_number"]
    stops = conn.execute(
        "SELECT id, station FROM train_stops WHERE train_number=? ORDER BY sequence",
        (tn,)
    ).fetchall()
    if len(stops) < 2: continue
    dest_idx = -1
    for i, s in enumerate(stops):
        if station_match(s["station"], t["destination"]):
            dest_idx = i
            break
    if dest_idx >= 0 and dest_idx < len(stops) - 1:
        for s in stops[dest_idx + 1:]:
            conn.execute("DELETE FROM train_stops WHERE id=?", (s["id"],))
        truncated += 1
print(f"  Treni con fermate fantasma troncate: {truncated}")

# ── FIX 3: ri-numera sequence per pulizia ─────────────────────────
print("\n[FIX C] Ri-numerazione sequence")
for r in conn.execute("SELECT DISTINCT train_number FROM train_stops").fetchall():
    tn = r["train_number"]
    stops = conn.execute(
        "SELECT id FROM train_stops WHERE train_number=? ORDER BY sequence",
        (tn,)
    ).fetchall()
    for s in stops:
        conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (-s[0], s[0]))
    for i, s in enumerate(stops):
        conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (i, s[0]))

conn.commit()

# Riepilogo
print("\n" + "=" * 60)
print("STATO POST-FIX")
print("=" * 60)
total = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
stops = conn.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
print(f"  Treni totali:     {total}")
print(f"  Fermate totali:   {stops}")
print(f"  Treni con stops:  {conn.execute('SELECT COUNT(DISTINCT train_number) FROM train_stops').fetchone()[0]}")

conn.close()
print("\nFatto.")
