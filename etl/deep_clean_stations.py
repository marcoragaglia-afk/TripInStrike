"""
Pulizia FINALE e profonda di tutte le stazioni.
Elimina:
- Stazioni con timing dentro il nome ("Rimini 19. 18 - Cesena")
- Stazioni con header treno dentro ("TI23867 MACERATA...")
- Prefissi codici ("K Foo", "L Foo", "Ovest Foo", "R A B b Foo", "E Foo")
- Frammenti spezzati ("A sti", "F orli", "G rottammare")
- Variant maiuscole ("PIACENZA", "FABRIANO", "LECCE")
- Frammenti URL/web ("nord.it", "ts/c_", "sportodialtretipologiedibicin")
- Caratteri encoding corrotti ("Forl�", "ch�il")
- Stazioni con numero finale ("Bologna Centrale 1", "Castelbolognese 1")
- Spazi interni ("PIACEN ZA" -> "PIACENZA", "Imo la" -> "Imola")
- Spazi prima del punto ("F.Aer" / "Faenza 20 .39")

Fonde varianti dello stesso nome.
"""
import sqlite3
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"


def is_pure_junk(name: str) -> bool:
    """True se la stazione è da eliminare."""
    s = name.strip()
    if not s or len(s) < 3:
        return True
    # Inizia con minuscola = frammento
    if re.match(r"^[a-zàèéìòù]", s):
        return True
    # Contiene timing pattern "HH .MM" o "HH.MM"
    if re.search(r"\b\d{1,2}\s*\.\s*\d{2}\b", s):
        return True
    # Header treno "TI<num>" oppure "TUA<num>"
    if re.match(r"^(TI|TUA|RV|REG|IC|FA|FR|AV)\d", s):
        return True
    # Stazioni con dash + spazi (timing pattern)
    if " - " in s:
        return True
    # Frammenti corti seguiti da parole intere
    parts = s.split()
    if len(parts) >= 2 and len(parts[0]) <= 1 and parts[0] not in ("L'", "S.", "S", "D'"):
        return True
    # URL/web fragments
    if re.search(r"\.(it|com|org)\b|/c_|/upload|https?", s, re.I):
        return True
    # Encoding corrotto �
    if "�" in s:
        return True
    # Termina con numero solo
    if re.search(r"\s+\d+$", s):
        return True
    # Contiene "Sospeso..."
    if re.search(r"Sospes|RELAZIONE|MOBILE|disponibilit|sportodialtre|tariffaregionale", s, re.I):
        return True
    # "Centrale" da sola (frammento)
    if s.lower() in ("centrale", "ovest", "est"):
        return True
    # Solo numeri/cifre
    if re.match(r"^[\d\s\.]+$", s):
        return True
    return False


def normalize_for_matching(s: str) -> str:
    """Forma canonica strict per identificare duplicati."""
    n = s.lower().strip()
    # Rimuovi punti, trattini, apostrofi e spazi per matching
    n = re.sub(r"[\s\.\-'`]+", "", n)
    return n


# Mappa specifica città spezzate
CITY_FIX = {
    r"\bPI?A\s*CEN\s*ZA\b|\bPIACE NZA\b|\bP IACENZA\b": "PIACENZA",
    r"\bFAB\s*RIA?\s*NO\b|\bFABRIA NO\b": "FABRIANO",
    r"\bPES\s*ARO\b|\bPES ARO\b": "PESARO",
    r"\bPESCA\s*RA\b|\bPESCA RA\b": "PESCARA",
    r"\bA\s*SCOLI?\s*P?\s*ICENO\b|\bASCOL\s*IPICENO\b": "ASCOLI PICENO",
    r"\bL\s*ECCE\b|\bLECC\s*E\b": "LECCE",
    r"\bROMA\s*T\s*ERMINI\b": "ROMA TERMINI",
    r"\bBOLOGNA\s*CENT\s*RALE\b": "BOLOGNA CENTRALE",
    r"\bMILAN\s*O?\s*CENTRALE\b": "MILANO CENTRALE",
    r"\bMILAN\s*O?\s*P\.?\s*GARIBALD\s*I\b": "MILANO PORTA GARIBALDI",
    r"\bFRANCAVIL\s*LAAL\s*MARE\b": "FRANCAVILLA AL MARE",
    r"\bTORINO\s*P\s*ORTA\s*NUOVA\b": "TORINO PORTA NUOVA",
    r"\bTorino\s*Port\b(?!\s*a)": "Torino Porta Nuova",
}


def apply_city_fixes(s: str) -> str:
    for pat, repl in CITY_FIX.items():
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    return s


def clean_name(s: str) -> str:
    """Pulisce il nome rimuovendo prefissi e fragmenti, applicando fixes."""
    s = s.strip()
    # Rimuovi prefissi codice singoli
    s = re.sub(r"^([KLEABFGT]|Ovest|Est)\s+(?=[A-Z])", "", s)
    # Rimuovi prefissi "R A B b ", "I R a f T ", ecc.
    s = re.sub(r"^([A-Za-z]\s+){2,6}(?=[A-Z])", "", s)
    # Strip leading/trailing spazi
    s = s.strip()
    # Apply city-specific fixes
    s = apply_city_fixes(s)
    # Strip trailing number
    s = re.sub(r"\s+\d+$", "", s).strip()
    # Doppi spazi
    s = re.sub(r"\s+", " ", s)
    # Spazio prima del punto: "Faenza ." -> "Faenza."
    s = re.sub(r"\s+\.", ".", s)
    return s.strip()


# Alias canonici (versione preferita)
CANONICAL_ALIASES = {
    "PIACENZA": "Piacenza",
    "FABRIANO": "Fabriano",
    "PESARO": "Pesaro",
    "PESCARA": "Pescara Centrale",
    "ASCOLI PICENO": "Ascoli Piceno",
    "LECCE": "Lecce",
    "ROMA TERMINI": "Roma Termini",
    "BOLOGNA CENTRALE": "Bologna Centrale",
    "MILANO CENTRALE": "Milano Centrale",
    "MILANO PORTA GARIBALDI": "Milano Porta Garibaldi",
    "TORINO PORTA NUOVA": "Torino Porta Nuova",
    "FRANCAVILLA AL MARE": "Francavilla al Mare",
    "PERUGIA": "Perugia",
    "RIMINI": "Rimini",
    "MACERATA": "Macerata",
    "PALERMO CENTRALE": "Palermo Centrale",
    "PALERMO C.LE": "Palermo Centrale",
    "SIBARI": "Sibari",
    "MESSINA CENTRALE": "Messina Centrale",
    "MESSINA CENT": "Messina Centrale",
    "BATTIPAGLIA": "Battipaglia",
    "VENTIMIGLIA": "Ventimiglia",
    "VIENNA Hauptbahnhof": "Vienna Hauptbahnhof",
    "Reggio Cal.C.le": "Reggio Calabria Centrale",
    "Castel S.Pietro T.": "Castel S.Pietro Terme",
    "Castelplanio-Cupra m": "Castelplanio-Cupra m.",
    "Castelplanio-Cupra m.": "Castelplanio-Cupra m.",
    "Castelbolognese": "Castelbolognese-Riolo Terme",
    "Cattolica-S.G.-G.": "Cattolica S.Giovanni Gabicce",
    "Cattolica-Gabicce": "Cattolica S.Giovanni Gabicce",
    "Falconara M.ma": "Falconara Marittima",
    "Cupramarittima": "Cupra Marittima",
    "Firenze S.M.N": "Firenze S.M.N.",
    "Marotta -Mondolfo": "Marotta-Mondolfo",
    "Marotta- Mondolfo": "Marotta-Mondolfo",
    "Rosetodegli Abruzzi": "Roseto degli Abruzzi",
    "Scernedi Pineto": "Scerne di Pineto",
    "Cerretod'Esi": "Cerreto d'Esi",
    "Portod'Ascoli": "Porto d'Ascoli",
    "Portod' Ascoli": "Porto d'Ascoli",
    "S.Benedettodel T.": "S. Benedetto d.T",
    "Maltignanod.Tronto": "Maltignano d.Tronto",
    "Maltignanod .Tronto": "Maltignano d.Tronto",
    "Marinodel Tronto": "Marino del Tronto",
    "Collidel Tronto": "Colli del Tronto",
    "Collidel T ronto": "Colli del Tronto",
    "Fossatodi Vico-G.": "Fossato di Vico-G.",
    "Fossatodi V ico-G.": "Fossato di Vico-G.",
    "Fossatodi Vico -G.": "Fossato di Vico-G.",
    "Francavillaal Mare": "Francavilla al Mare",
    "Monsampolodel T": "Monsampolo del T.",
    "Monsampolo del T": "Monsampolo del T.",
    "Monsampo lo del T": "Monsampolo del T.",
    "Pantieredi C.": "Pantiere di C.",
    "Savignanosul Ovest R.": "Savignano sul Rubicone",
    "Savignano sul Ovest R.": "Savignano sul Rubicone",
    "Torredei Passeri": "Torre dei Passeri",
    "Civitanova-M.Montegr.": "Civitanova-M.Montegr.",
    "Venezia Mestre !": "Venezia Mestre",
    "Peschierad.Garda": "Peschiera del Garda",
    "Pavia a Y": "Pavia",
    "Benevento a YS": "Benevento",
    "Padovaq.M": "Padova",
    "Orte 2": "Orte",
}


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("DEEP CLEANUP STAZIONI")
    print("=" * 70)

    # ─── Step 1: applica clean_name + alias a tutto ────────────────────────
    print("\nStep 1: pulizia nomi + alias canonici...")
    fixed_count = 0
    for table, col in [("guaranteed_trains", "origin"), ("guaranteed_trains", "destination"),
                       ("train_stops", "station"), ("stations", "name")]:
        rows = conn.execute(f"SELECT rowid AS rid, {col} AS val FROM {table}").fetchall()
        for r in rows:
            old = r["val"]
            new = clean_name(old)
            new = CANONICAL_ALIASES.get(new, new)
            if new != old:
                try:
                    conn.execute(f"UPDATE {table} SET {col}=? WHERE rowid=?", (new, r["rid"]))
                    fixed_count += 1
                except sqlite3.IntegrityError:
                    pass
    print(f"  Rinominati: {fixed_count}")

    # ─── Step 2: elimina stazioni junk ────────────────────────────────────
    print("\nStep 2: eliminazione stazioni junk...")
    junk_deleted = 0
    rows = conn.execute("SELECT name FROM stations").fetchall()
    for (name,) in rows:
        if is_pure_junk(name):
            # Elimina anche treni e fermate che usano questo nome (PURO junk)
            conn.execute("DELETE FROM train_stops WHERE station=?", (name,))
            conn.execute("DELETE FROM stations WHERE name=?", (name,))
            junk_deleted += 1
            print(f"  ELIM: {name!r}")
    print(f"  Stazioni junk eliminate: {junk_deleted}")

    # Pulisci anche fermate che hanno nomi junk anche se la stazione non c'è più
    rows = conn.execute("SELECT id, station FROM train_stops").fetchall()
    stops_deleted = 0
    for r in rows:
        if is_pure_junk(r["station"]):
            conn.execute("DELETE FROM train_stops WHERE id=?", (r["id"],))
            stops_deleted += 1
    print(f"  Fermate junk eliminate: {stops_deleted}")

    # ─── Step 3: fondi varianti tramite forma canonica ────────────────────
    print("\nStep 3: fusione varianti dello stesso nome...")
    all_names = set()
    for table, col in [("guaranteed_trains", "origin"), ("guaranteed_trains", "destination"),
                       ("train_stops", "station")]:
        for (n,) in conn.execute(f"SELECT DISTINCT {col} FROM {table}").fetchall():
            if n: all_names.add(n.strip())

    canon_groups: dict[str, list[str]] = {}
    for n in all_names:
        c = normalize_for_matching(n)
        if c:
            canon_groups.setdefault(c, []).append(n)

    rename_map = {}
    for canon, variants in canon_groups.items():
        if len(variants) <= 1:
            continue
        # Sceglie versione canonica: mixed case, con punti, più corta tra le pulite
        def score(s: str) -> tuple:
            return (
                s == s.upper(),       # evita tutto MAIUSCOLO
                -s.count("."),         # preferisce con punti
                len(s),                # preferisce più corta
                s
            )
        best = sorted(variants, key=score)[0]
        for v in variants:
            if v != best:
                rename_map[v] = best

    print(f"  Fusioni: {len(rename_map)}")
    for old, new in list(rename_map.items())[:30]:
        print(f"    '{old}' -> '{new}'")

    for old, new in rename_map.items():
        conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old))
        conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old))
        conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old))

    # ─── Step 4: ricostruisci stations table ──────────────────────────────
    print("\nStep 4: ricostruzione stations...")
    conn.execute("DELETE FROM stations")
    final_names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n and n.strip() and not is_pure_junk(n):
            final_names.add(n.strip())
    for n in sorted(final_names):
        conn.execute("INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                     (n, normalize_station_name(n)))

    conn.commit()
    n_st = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"  Stazioni finali: {n_st}")

    print("\n--- TUTTE LE STAZIONI FINALI ---")
    for r in conn.execute("SELECT name FROM stations ORDER BY name"):
        print(f"  {r[0]}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
