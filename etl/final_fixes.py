"""
FIX FINALI prima della demo nazionale:

1. Orario malformato (9702 arr=9:50 -> 09:50)
2. Rimuove Bologna FASULLA da treni che NON passano per Bologna
   (794, 795 vanno via Roma; 9583/9587/9623/9639 vanno via Firenze AV)
3. Riordina fermate AV con Bologna mal posizionata (9406, 9414, etc.)
4. Tronca fermate oltre destinazione garantita
5. Rimuove fermate corrotte (treni con regressioni >1h)
6. Rimuove duplicati esatti
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "frontend" / "public" / "sciopero.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

def to_min(t):
    if not t: return None
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", t.strip())
    if not m: return None
    h, mm = int(m.group(1)), int(m.group(2))
    if h > 23 or mm > 59: return None
    return h * 60 + mm

# ── FIX 1: orari malformati ──────────────────────────────────────────
print("[FIX 1] Orari malformati (manca zero iniziale)")
n = conn.execute("""
    UPDATE guaranteed_trains
    SET arr_time = '0' || arr_time
    WHERE arr_time LIKE '_:__' AND arr_time NOT LIKE '__:__'
""").rowcount
n2 = conn.execute("""
    UPDATE guaranteed_trains
    SET dep_time = '0' || dep_time
    WHERE dep_time LIKE '_:__' AND dep_time NOT LIKE '__:__'
""").rowcount
print(f"  arr_time corretti: {n}, dep_time: {n2}")

# ── FIX 2: rimuove Bologna fasulla dai treni che NON passano via Bologna
print("\n[FIX 2] Rimuove Bologna fasulla")
# 794, 795 vanno via Roma-Firenze-Bologna non li tocco
# 794: Reggio Cal -> Torino, va via Roma direttamente (non Bologna)
# 795: simmetrico
# Notte ICN: 794, 795, 1959, 1963 etc. spesso non passano via Bologna
# Verifico caso per caso

# ICN/AV verso/da Reggio Cal o Salerno con SOLO Bologna come fermata:
# Probabilmente Bologna fittizia aggiunta da add_missing_bologna.py
suspicious = conn.execute("""
    SELECT t.train_number, t.origin, t.destination, COUNT(s.id) n_stops
    FROM guaranteed_trains t
    LEFT JOIN train_stops s ON t.train_number = s.train_number
    WHERE t.table_type IN ('tabella_a','tabella_b')
    GROUP BY t.train_number
    HAVING n_stops = 1
""").fetchall()

removed_bologna = 0
for r in suspicious:
    tn = r["train_number"]
    stops = conn.execute(
        "SELECT id, station FROM train_stops WHERE train_number=?", (tn,)
    ).fetchall()
    if len(stops) == 1 and "Bologna" in stops[0]["station"]:
        # Una sola fermata = Bologna = quasi certamente fittizia
        conn.execute("DELETE FROM train_stops WHERE id=?", (stops[0]["id"],))
        print(f"  Rimossa Bologna fasulla da {tn} ({r['origin']} -> {r['destination']})")
        removed_bologna += 1
print(f"  Totale Bologna fasulle rimosse: {removed_bologna}")

# ── FIX 3: riordina fermate per coerenza temporale ───────────────────
print("\n[FIX 3] Riordino fermate per orario crescente (treni con sequence non monotone)")
def assign_sorted_sequences(conn, train_number):
    """Riordina le fermate per orario crescente e ri-assegna sequence."""
    rows = conn.execute(
        "SELECT id, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (train_number,)
    ).fetchall()
    if len(rows) < 2: return False
    # Calcola tempo "rappresentativo" di ogni fermata
    items = []
    for r in rows:
        t = to_min(r["departure"]) if r["departure"] else to_min(r["arrival"])
        if t is None: continue
        items.append((t, r["id"], r["station"], r["arrival"], r["departure"]))
    # Se l'ordine attuale (by sequence) ha regressioni > 1h, riordina
    times = [it[0] for it in items]
    has_big_regression = any(times[i] < times[i-1] - 60 for i in range(1, len(times)))
    if not has_big_regression: return False
    # Riordina per orario
    items.sort(key=lambda x: x[0])
    # Aggiorna sequence (step 1: temporaneo, step 2: finale per evitare unique conflict)
    for it in items:
        conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (-it[1], it[1]))
    for i, it in enumerate(items):
        conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (i, it[1]))
    return True

# Identifica treni con regressioni di orario significative
candidates = conn.execute("SELECT DISTINCT train_number FROM train_stops").fetchall()
reordered = 0
for r in candidates:
    if assign_sorted_sequences(conn, r["train_number"]):
        reordered += 1
print(f"  Treni con fermate riordinate: {reordered}")
conn.commit()

# ── FIX 4: tronca fermate oltre destinazione garantita ───────────────
print("\n[FIX 4] Troncamento fermate oltre destinazione garantita")
def stn_canon(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())

truncated = 0
for t in conn.execute("""
    SELECT train_number, destination FROM guaranteed_trains
    WHERE destination IS NOT NULL
""").fetchall():
    tn = t["train_number"]
    dest_c = stn_canon(t["destination"])
    stops = conn.execute(
        "SELECT id, station FROM train_stops WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    if len(stops) < 2: continue
    dest_idx = -1
    for i, s in enumerate(stops):
        sc = stn_canon(s["station"])
        if sc == dest_c or (len(dest_c) >= 5 and dest_c in sc):
            dest_idx = i
            break
    if dest_idx >= 0 and dest_idx < len(stops) - 1:
        # Elimina tutto oltre la destinazione
        for s in stops[dest_idx + 1:]:
            conn.execute("DELETE FROM train_stops WHERE id=?", (s["id"],))
        truncated += 1
print(f"  Treni con fermate fantasma troncate: {truncated}")

# ── FIX 5: rimuovi duplicati esatti ──────────────────────────────────
print("\n[FIX 5] Duplicati esatti")
n = conn.execute("""
    DELETE FROM guaranteed_trains WHERE id NOT IN (
        SELECT MIN(id) FROM guaranteed_trains
        GROUP BY train_number, origin, destination, dep_time, day_type, table_type
    )
""").rowcount
print(f"  Duplicati rimossi: {n}")

# ── FIX 6: treni con fermate completamente corrotte ─────────────────
# (orari incompatibili con dep/arr del treno o tempi che vanno indietro)
print("\n[FIX 6] Treni con dati fermate troppo corrotti per essere salvati")
wiped = 0
for t in conn.execute("""
    SELECT train_number, dep_time, arr_time FROM guaranteed_trains
""").fetchall():
    tn = t["train_number"]
    dep_min = to_min(t["dep_time"])
    arr_min = to_min(t["arr_time"])
    if dep_min is None: continue
    stops = conn.execute(
        "SELECT id, station, arrival, departure FROM train_stops "
        "WHERE train_number=? ORDER BY sequence", (tn,)
    ).fetchall()
    if not stops: continue

    # Conta quante fermate hanno orari inconsistenti col percorso teorico
    times = []
    for s in stops:
        t_ = to_min(s["departure"]) or to_min(s["arrival"])
        if t_ is not None:
            times.append(t_)

    if not times: continue

    # Verifica monotonia (permettendo 1 wrap mezzanotte)
    wraps = 0
    bad = False
    for i in range(1, len(times)):
        if times[i] < times[i-1]:
            wraps += 1
            if wraps > 1:
                bad = True
                break
            # Se decrease > 60min e l'orario non è "credibile come wrap mezzanotte"
            if times[i-1] - times[i] < 60:
                bad = True
                break

    if bad:
        # Wipe stops
        n = conn.execute("DELETE FROM train_stops WHERE train_number=?", (tn,)).rowcount
        print(f"  Wipe {tn} ({n} fermate troppo corrotte)")
        wiped += 1

print(f"  Treni con fermate cancellate: {wiped}")

conn.commit()

# ── RIEPILOGO FINALE ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("RIEPILOGO POST-FIX")
print("=" * 60)
for r in conn.execute("""
    SELECT table_type, day_type, COUNT(*) c
    FROM guaranteed_trains
    GROUP BY table_type, day_type
    ORDER BY table_type, day_type
"""):
    print(f"  {r['table_type']:12s} {r['day_type']:10s}  {r['c']:4d} treni")
print(f"  Stazioni:                {conn.execute('SELECT COUNT(*) FROM stations').fetchone()[0]:4d}")
print(f"  Fermate:                 {conn.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]:4d}")
print(f"  Treni con fermate:       {conn.execute('SELECT COUNT(DISTINCT train_number) FROM train_stops').fetchone()[0]:4d}")

conn.close()
