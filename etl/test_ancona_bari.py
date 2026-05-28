"""
Replica COMPLETA del router TypeScript per testare Ancona -> Bari Centrale.
Mostra tutti gli itinerari come l'app li restituirebbe.
"""
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

def to_min(t):
    if not t: return None
    m = re.match(r'^(\d{1,2}):(\d{2})$', t.strip())
    if not m: return None
    return int(m.group(1)) * 60 + int(m.group(2))

def time_diff(a, b):
    d = to_min(b) - to_min(a)
    if d < 0: d += 24*60
    return d

def find_stop_leg(stops, board_st, alight_st):
    if not stops: return None
    board_idx = -1
    alight_idx = -1
    for i, s in enumerate(stops):
        if board_idx == -1 and station_match(s["station"], board_st):
            board_idx = i
        if alight_idx == -1 and station_match(s["station"], alight_st):
            alight_idx = i
    if board_idx == -1 or alight_idx == -1 or board_idx >= alight_idx:
        return None
    bt = stops[board_idx]["departure"] or stops[board_idx]["arrival"]
    at = stops[alight_idx]["arrival"] or stops[alight_idx]["departure"]
    return {"boardTime": bt, "alightTime": at, "boardStation": stops[board_idx]["station"], "alightStation": stops[alight_idx]["station"]}

def lookup_arr_time(stops, alight_at):
    for s in stops:
        if station_match(s["station"], alight_at):
            return s["arrival"] or s["departure"] or ""
    return ""

FROM = "Ancona"
TO = "Bari Centrale"
DAY = "feriale"

trains = conn.execute("""
    SELECT * FROM guaranteed_trains WHERE day_type=? OR day_type='entrambi'
""", (DAY,)).fetchall()
stops_cache = {}
for t in trains:
    stops_cache[t["train_number"]] = conn.execute(
        "SELECT * FROM train_stops WHERE train_number=? ORDER BY sequence",
        (t["train_number"],)
    ).fetchall()

# ── FASE 1: diretti ──────────────────────────────────────────────
direct = []
for t in trains:
    if not t["dep_time"]: continue
    stops = stops_cache[t["train_number"]]
    primary = station_match(t["origin"], FROM) and station_match(t["destination"], TO)
    if primary:
        arr = t["arr_time"] or lookup_arr_time(stops, TO)
        direct.append({
            "train": t["train_number"], "kind": "primary",
            "board": t["dep_time"], "alight": arr or "???",
            "boardSt": t["origin"], "alightSt": t["destination"],
        })
    elif stops:
        # Estende SEMPRE con origin/destination virtuali (anche per tabella_a)
        # se non già presenti nelle stops
        has_origin = any(station_match(s["station"], t["origin"]) for s in stops)
        has_dest = any(station_match(s["station"], t["destination"]) for s in stops)
        full = []
        if not has_origin:
            full.append({"station": t["origin"], "arrival": None, "departure": t["dep_time"]})
        full.extend(stops)
        if not has_dest:
            full.append({"station": t["destination"], "arrival": t["arr_time"], "departure": None})
        leg = find_stop_leg(full, FROM, TO)
        if leg:
            direct.append({
                "train": t["train_number"], "kind": "stop-match",
                "board": leg["boardTime"], "alight": leg["alightTime"] or "???",
                "boardSt": leg["boardStation"], "alightSt": leg["alightStation"],
                "origin": t["origin"], "destination": t["destination"],
            })

print(f"=== {FROM} -> {TO} (giornata {DAY}) ===\n")
print(f"DIRETTI: {len(direct)}")
for it in direct:
    print(f"  {it['train']:6s}  board={it['boardSt']:18s}@{it['board']:5s}  alight={it['alightSt']:18s}@{it['alight']:5s}")
    if 'origin' in it:
        print(f"           (treno {it['origin']} -> {it['destination']})")

# ── FASE 2: con cambio ────────────────────────────────────────────
print(f"\nCON CAMBIO (Phase 2):")

# trainsFromOrigin: origin=Ancona O Ancona in stops
# NEW: escludi treni che ARRIVANO a Ancona (dest = from)
trains_from = []
for t in trains:
    if not t["dep_time"]: continue
    if station_match(t["destination"], FROM): continue  # treno che ARRIVA a from
    if station_match(t["origin"], FROM):
        trains_from.append((t, t["dep_time"], t["origin"]))
    else:
        stops = stops_cache[t["train_number"]]
        from_idx = -1
        for i, s in enumerate(stops):
            if station_match(s["station"], FROM):
                from_idx = i
                break
        if from_idx == -1: continue
        if from_idx == len(stops) - 1: continue  # last stop, no forward stops
        bt = stops[from_idx]["departure"] or stops[from_idx]["arrival"]
        if bt:
            trains_from.append((t, bt, stops[from_idx]["station"]))

trains_to = []
for t in trains:
    if not t["dep_time"]: continue
    if station_match(t["origin"], TO): continue  # treno che PARTE da TO
    if station_match(t["destination"], TO):
        trains_to.append(t)
    else:
        stops = stops_cache[t["train_number"]]
        if any(station_match(s["station"], TO) for s in stops):
            trains_to.append(t)

print(f"  Candidati trainA (con Ancona): {len(trains_from)}")
print(f"  Candidati trainB (verso Bari): {len(trains_to)}")

results = []
for trainA, board_a_time, board_a_st in trains_from:
    stops_a = stops_cache[trainA["train_number"]]
    # changePoints: tutte le fermate dopo board_a_st cronologicamente, poi destinazione
    board_idx_a = -1
    for i, s in enumerate(stops_a):
        if station_match(s["station"], board_a_st):
            board_idx_a = i
            break
    change_points = []
    for i in range(board_idx_a + 1, len(stops_a)):
        s = stops_a[i]
        at = s["arrival"] or s["departure"]
        if at and not station_match(s["station"], board_a_st) and not station_match(s["station"], FROM):
            change_points.append((s["station"], at))
    final_arr = trainA["arr_time"] or lookup_arr_time(stops_a, trainA["destination"])
    if final_arr and not any(station_match(c[0], trainA["destination"]) for c in change_points):
        change_points.append((trainA["destination"], final_arr))

    # Filtra: se 'TO' è una fermata di trainA, scarta cp DOPO TO
    to_idx_a = -1
    for i, s in enumerate(stops_a):
        if station_match(s["station"], TO):
            to_idx_a = i
            break
    to_is_dest_a = station_match(trainA["destination"], TO)

    for cp_station, cp_arr in change_points:
        if to_idx_a != -1 or to_is_dest_a:
            cp_idx = -1
            for i, s in enumerate(stops_a):
                if station_match(s["station"], cp_station):
                    cp_idx = i
                    break
            to_pos = to_idx_a if to_idx_a != -1 else len(stops_a)
            cp_pos = cp_idx if cp_idx != -1 else len(stops_a)
            if to_pos <= cp_pos: continue

        for trainB in trains_to:
            if trainB["train_number"] == trainA["train_number"]: continue
            stops_b = stops_cache[trainB["train_number"]]
            # Salita su B
            board_b_st = None
            board_b_time = None
            if station_match(cp_station, trainB["origin"]):
                board_b_st = trainB["origin"]
                board_b_time = trainB["dep_time"]
            else:
                for s in stops_b:
                    if station_match(s["station"], cp_station):
                        board_b_st = s["station"]
                        board_b_time = s["departure"] or s["arrival"]
                        break
            if not board_b_st or not board_b_time: continue
            # Discesa
            alight_b_st = None
            alight_b_time = None
            if station_match(trainB["destination"], TO):
                alight_b_st = trainB["destination"]
                alight_b_time = trainB["arr_time"] or lookup_arr_time(stops_b, TO)
            else:
                # board_idx_b < alight_idx_b
                bib = next((i for i, s in enumerate(stops_b) if station_match(s["station"], board_b_st)), -1)
                aib = next((i for i, s in enumerate(stops_b) if station_match(s["station"], TO)), -1)
                if bib == -1 or aib == -1 or aib <= bib: continue
                alight_b_st = stops_b[aib]["station"]
                alight_b_time = stops_b[aib]["arrival"] or stops_b[aib]["departure"]
            if not alight_b_time: continue

            # Transfer
            transfer = time_diff(cp_arr, board_b_time)
            if transfer < 5 or transfer > 360: continue
            total = time_diff(board_a_time, alight_b_time)

            results.append({
                "tA": trainA["train_number"], "tB": trainB["train_number"],
                "boardA": board_a_time, "cp": cp_station, "cpArr": cp_arr,
                "boardB": board_b_time, "alightB": alight_b_time,
                "transfer": transfer, "total": total,
            })

# Ordina e mostra primi
results.sort(key=lambda r: (to_min(r["boardA"]), r["total"]))
print(f"  Itinerari con cambio trovati: {len(results)}")
for r in results[:15]:
    print(f"  {r['tA']:5s} (Ancona {r['boardA']}) -> {r['cp']:22s} {r['cpArr']:5s} "
          f"| cambio {r['transfer']:3d}min | {r['tB']:5s} dep {r['boardB']} -> Bari {r['alightB']}  "
          f"(tot {r['total']//60}h{r['total']%60:02d})")

conn.close()
