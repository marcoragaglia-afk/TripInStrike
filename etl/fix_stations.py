"""
Pulizia del database:
1. Corregge nomi stazione con spazio errato da hyphenation PDF ("La mbrate" -> "Lambrate")
2. Rimuove suffissi di validità/servizio ("Circola nei Festivi...", "Servizio di TTPER", ecc.)
3. Corregge numeri treno preposti a origine/destinazione ("12504 Roma Termini" -> "Roma Termini")
4. Ricostruisce la tabella stations da guaranteed_trains puliti
"""

import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"

# Correzioni dirette: nome sbagliato -> nome corretto (o None per eliminare)
WORD_FIXES = {
    "La mbrate": "Lambrate",
    "Ter me": "Terme",
    "Ter mini": "Termini",
    "Ter moli": "Termoli",
    "Tera mo": "Teramo",
    "Ca mpiglia": "Campiglia",
    "Cia mpino": "Ciampino",
    "Cre mona": "Cremona",
    "Deci mo": "Decimo",
    "Do modossola": "Domodossola",
    "E mpoli": "Empoli",
    "Fiu micino": "Fiumicino",
    "For mia": "Formia",
    "Ge mona": "Gemona",
    "Ger magnano": "Germagnano",
    "I mola": "Imola",
    "I mperia": "Imperia",
    "La mezia": "Lamezia",
    "Li mone": "Limone",
    "Maco mer": "Macomer",
    "Paler mo": "Palermo",
    "Par ma": "Parma",
    "Pio mbino": "Piombino",
    "Pontre moli": "Pontremoli",
    "Porto maggiore": "Portomaggiore",
    "Pre mosello": "Premosello",
    "Reggio E milia": "Reggio Emilia",
    "Ri mini": "Rimini",
    "Ro ma": "Roma",
    "Roccapalu mba": "Roccapalumba",
    "Salso maggiore": "Salsomaggiore",
    "Ser mide": "Sermide",
    "Sul mona": "Sulmona",
    "Taor mina": "Taormina",
    "U mbertide": "Umbertide",
    "Venti miglia": "Ventimiglia",
}

# Pattern per suffissi da rimuovere (testo di validità/servizio appeso al nome)
TRASH_PATTERNS = [
    r"\s+Circola.*$",           # "... Circola nei Festivi dal..."
    r"\s+valido\b.*$",          # "... valido dal 1° gennaio..."
    r"\s+Servizio\b.*$",        # "... Servizio di TTPER"
    r"\s+Non\b.*$",             # "... Non effettua..."
    r"\s+\d+/\d+.*$",           # "... 14/2..."
]

# Stazioni da eliminare completamente (duplicati già presenti nella forma corretta)
DELETE_NAMES = {
    "Acqui Ter me",                    # -> Acqui Terme
    "Cagliari -El mas",                # -> Cagliari Elmas
    "Castelplanio-Cupra m.m.m.m.m.m.m.",
    "Napoli C.C.C.C.C.C.C.C.C. Flegrei",
    "Napoli S.S.S.S.S.S. Giovanni-Barra",
    "Reggio Cal. C.le",               # -> REGGIO DI CALABRIA CENTRALE
    "Reggio E. S.Lazzaro",
    "Ter mini I merese",              # -> TERMINI IMERESE
    "Paler mo Centrale",              # -> PALERMO C.LE / Palermo Centrale
    "vs",                             # junk
    "MILANO CENTRALE VIENNA Hauptbahnhof",
    "MILANO CENTRALE modifiche alla relazione garantita",
    "BASILEA SBB ROMA TIBURTINA",
    "LECCE MILANO CENTRALE",
    "MILANO CENTRALE LECCE",
}


def normalize(name: str) -> str:
    n = name.upper().strip()
    n = re.sub(r'\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?', 'SANTA MARIA NOVELLA', n)
    n = re.sub(r'\bC\.LE\b|\bCLE\b|\bCENTR\b', 'CENTRALE', n)
    n = re.sub(r'\bP\.NUOVA\b|\bP\.N\.\b|\bPN\b', 'PORTA NUOVA', n)
    n = re.sub(r'\bP\.GARIBALDI\b', 'PORTA GARIBALDI', n)
    n = re.sub(r'\bSTA\.\s*LUCIA\b|\bS\.LUCIA\b', 'SANTA LUCIA', n)
    n = re.sub(r'\bS\.\s*', 'SAN ', n)
    n = re.sub(r'\bD\.T\.?\b', 'DEL TRONTO', n)
    n = re.sub(r"['\\-]", ' ', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip()


def clean_name(name: str) -> str | None:
    """Pulisce un nome stazione; restituisce None se va eliminato."""
    if not name:
        return None

    # Elimina da lista nera
    if name.strip() in DELETE_NAMES:
        return None

    # Elimina nomi che sono puri orari (es. "22:03") o numeri
    if re.match(r'^\d{1,2}:\d{2}$', name.strip()):
        return None
    if re.match(r'^\d+$', name.strip()):
        return None

    # Rimuovi suffissi di validità/servizio
    for pat in TRASH_PATTERNS:
        name = re.sub(pat, "", name).strip()

    # Applica correzioni parole spezzate
    for wrong, correct in WORD_FIXES.items():
        name = name.replace(wrong, correct)

    # Elimina se troppo corto o troppo lungo dopo la pulizia
    name = name.strip()
    if len(name) < 2 or len(name) > 50:
        return None

    return name


def main():
    if not DB_PATH.exists():
        print(f"Database non trovato: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))

    # Step 1: Correggi numeri treno preposti
    conn.execute("""
        UPDATE guaranteed_trains
        SET origin = TRIM(SUBSTR(origin, INSTR(origin, ' ') + 1))
        WHERE origin GLOB '[0-9]*' AND INSTR(origin, ' ') > 0
    """)
    conn.execute("""
        UPDATE guaranteed_trains
        SET destination = TRIM(SUBSTR(destination, INSTR(destination, ' ') + 1))
        WHERE destination GLOB '[0-9]*' AND INSTR(destination, ' ') > 0
    """)

    # Step 2: Carica tutte le origini/destinazioni e puliscile
    rows = conn.execute(
        "SELECT DISTINCT origin FROM guaranteed_trains WHERE origin != '' "
        "UNION SELECT DISTINCT destination FROM guaranteed_trains WHERE destination != ''"
    ).fetchall()

    # Costruisci mapping: vecchio nome -> nuovo nome (None = da eliminare)
    rename_map: dict[str, str | None] = {}
    for (raw_name,) in rows:
        cleaned = clean_name(raw_name)
        if cleaned != raw_name:
            rename_map[raw_name] = cleaned

    print(f"Correzioni da applicare: {len(rename_map)}")
    for old, new in sorted(rename_map.items()):
        print(f"  '{old}' -> '{new}'")

    # Step 3: Applica le correzioni a guaranteed_trains
    for old, new in rename_map.items():
        if new is None:
            # Elimina i treni che hanno questa stazione (sono dati non validi)
            conn.execute(
                "DELETE FROM guaranteed_trains WHERE origin=? OR destination=?",
                (old, old)
            )
        else:
            conn.execute(
                "UPDATE guaranteed_trains SET origin=? WHERE origin=?",
                (new, old)
            )
            conn.execute(
                "UPDATE guaranteed_trains SET destination=? WHERE destination=?",
                (new, old)
            )

    # Step 4: Ricostruisce la tabella stations
    rows2 = conn.execute("""
        SELECT DISTINCT origin AS name FROM guaranteed_trains
        WHERE origin != '' AND length(origin) BETWEEN 2 AND 50
        UNION
        SELECT DISTINCT destination FROM guaranteed_trains
        WHERE destination != '' AND length(destination) BETWEEN 2 AND 50
    """).fetchall()

    stations: dict[str, str] = {}
    for (name,) in rows2:
        name = name.strip()
        if not name:
            continue
        norm = normalize(name)
        if norm not in stations:
            stations[norm] = name
        elif stations[norm] == stations[norm].upper() and name != name.upper():
            stations[norm] = name  # preferisce misto su maiuscolo

    conn.execute("DELETE FROM stations")
    conn.executemany(
        "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
        [(display, norm) for norm, display in stations.items()],
    )

    conn.commit()

    total_trains = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"\nTreni garantiti: {total_trains}")
    print(f"Stazioni pulite: {total_stations}")

    print("\nStazioni Roma:")
    for r in conn.execute(
        "SELECT name FROM stations WHERE normalized_name LIKE '%ROMA%' ORDER BY name"
    ):
        print(f"  {r[0]}")

    print("\nStazioni Milano:")
    for r in conn.execute(
        "SELECT name FROM stations WHERE normalized_name LIKE '%MILAN%' ORDER BY name"
    ):
        print(f"  {r[0]}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
