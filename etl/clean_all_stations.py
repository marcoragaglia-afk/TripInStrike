"""
Pulizia aggressiva di tutti i nomi stazione in stations + train_stops + guaranteed_trains.

Rimuove pattern di junk PDF:
  - Caratteri di controllo, (cid:NN)
  - Sequenze "62 a I", "a HH.MM", numeri appiccicati
  - Bullet/pipe/asterischi
  - Stazioni che cominciano con %%, "*Gli, (asterisco, ecc.
  - Suffissi come ".50 ·", "P.N.50 · ·"

Normalizza:
  - "Verona P.N", "Verona P.N.", "Verona P.N. · ·" -> "Verona P.N."
  - "Foggia62 a I" -> "Foggia"
"""
import sqlite3
import re
import sys
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"
sys.path.insert(0, str(Path(__file__).parent))
from build_db import normalize_station_name


# Pattern di junk da rimuovere a destra
TRAILING_JUNK = re.compile(
    r"(\s*\d+\s*[a-zA-Z]?\s*[•·]?.*"      # "62 a I •"
    r"|\s+a\s+[\d:.]+.*"                   # " a 09.57"
    r"|\s*[•·|*].*"                        # bullet/pipe/asterisco
    r"|\s+a\s+[•·].*"                      # " a •"
    r"|\.\s*\d+\s*[•·].*"                  # ".50 •"
    r"|\s*\(cid:\d+\).*"                   # (cid:57)
    r")$"
)
# Pattern di junk a sinistra
LEADING_JUNK = re.compile(
    r"^(\s*[\.\-,]+\s*"
    r"|sabato\.\s+|domenica\.\s+|lunedi\.\s+|festivo\.\s+|feriale\.\s+"
    r"|%+\s*"
    r"|\"+\s*\*\s*"          # "*Gli...
    r"|\(\s*"                # (asterisco
    r")"
)
# Pattern che identifica una stazione che è quasi tutta junk e va eliminata
PURE_JUNK = re.compile(
    r"^[^a-zA-Z]"            # non inizia con lettera
    r"|^\d+"                 # inizia con numero
    r"|effettua|orario|sieffettu|gliautoservizi|sostitutivi|valido|circola|servizio"
    r"|^(con|al|il|del|le|da|per)\s"
    r"|^[A-Z]\s+[A-Z]\s+[A-Z]"  # spazi tra lettere
    , re.I
)


def clean_station_name(name: str) -> str | None:
    """Pulisce nome stazione. Ritorna None se è junk da eliminare."""
    if not name:
        return None
    s = name.strip()

    # Rimuovi (cid:N) ovunque
    s = re.sub(r"\(cid:\d+\)", "", s)

    # Strip junk start ripetutamente
    prev = None
    while prev != s:
        prev = s
        s = LEADING_JUNK.sub("", s).strip()

    # Strip junk end
    s = TRAILING_JUNK.sub("", s).strip()

    # Numeri appiccicati alla fine di parole: "Foggia62" -> "Foggia"
    s = re.sub(r"(\b[A-Za-z][A-Za-zàèéìòù]+)\d+\b", r"\1", s)

    # Doppi spazi, punteggiatura residua
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,;:•·|*\"'-")

    # Check finale: se è troppo corto o è puro junk, scarta
    if not s or len(s) < 3:
        return None
    if PURE_JUNK.search(s):
        return None
    if not re.search(r"[a-zA-ZàèéìòùÀÈÉÌÒÙ]", s):
        return None

    # Normalizza "Verona P.N", "Verona P.N." -> "Verona P.N." (con punto finale)
    s = re.sub(r"\bP\.N(?!\.)", "P.N.", s)
    s = re.sub(r"\bP\.N\.+", "P.N.", s)

    return s


def canonical_name(name: str) -> str:
    """Forma canonica per matching tra varianti."""
    n = name.upper()
    n = re.sub(r"[^\w]+", "", n)
    return n


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("PULIZIA AGGRESSIVA STAZIONI")
    print("=" * 70)

    # ── 1. Pulisci tutti i nomi nelle 3 tabelle ─────────────────────────────
    print("\n--- Step 1: pulizia nomi in stations ---")
    stations = conn.execute("SELECT name FROM stations").fetchall()
    delete_st = []
    rename_map: dict[str, str] = {}
    for r in stations:
        old = r["name"]
        new = clean_station_name(old)
        if new is None:
            delete_st.append(old)
        elif new != old:
            rename_map[old] = new

    print(f"  Da eliminare (junk): {len(delete_st)}")
    print(f"  Da rinominare: {len(rename_map)}")

    # Pulisci anche train_stops e guaranteed_trains
    print("\n--- Step 2: pulizia in train_stops ---")
    ts = conn.execute("SELECT id, station FROM train_stops").fetchall()
    ts_fixed = 0
    ts_deleted = 0
    for r in ts:
        new = clean_station_name(r["station"])
        if new is None:
            conn.execute("DELETE FROM train_stops WHERE id=?", (r["id"],))
            ts_deleted += 1
        elif new != r["station"]:
            conn.execute("UPDATE train_stops SET station=? WHERE id=?", (new, r["id"]))
            ts_fixed += 1
    print(f"  fermate rinominate: {ts_fixed}, eliminate: {ts_deleted}")

    print("\n--- Step 3: pulizia origin/destination in guaranteed_trains ---")
    gt = conn.execute("SELECT id, origin, destination FROM guaranteed_trains").fetchall()
    gt_fixed = 0
    gt_deleted = 0
    for r in gt:
        no = clean_station_name(r["origin"])
        nd = clean_station_name(r["destination"])
        if no is None or nd is None:
            conn.execute("DELETE FROM guaranteed_trains WHERE id=?", (r["id"],))
            gt_deleted += 1
        else:
            if no != r["origin"]:
                conn.execute("UPDATE guaranteed_trains SET origin=? WHERE id=?", (no, r["id"]))
                gt_fixed += 1
            if nd != r["destination"]:
                conn.execute("UPDATE guaranteed_trains SET destination=? WHERE id=?", (nd, r["id"]))
                gt_fixed += 1
    print(f"  origin/destination rinominati: {gt_fixed}, treni eliminati: {gt_deleted}")

    # ── 4. Ricostruisci stations dalla unione di origin/destination + train_stops ──
    print("\n--- Step 4: ricostruisci stations table ---")
    conn.execute("DELETE FROM stations")
    used_names: set[str] = set()
    for (n,) in conn.execute(
        "SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains "
        "UNION SELECT station FROM train_stops"
    ):
        if n and n.strip():
            used_names.add(n.strip())

    # Fonde varianti dello stesso nome canonico, preferisce versione con punto/spazi corretti
    canon_groups: dict[str, list[str]] = {}
    for n in used_names:
        canon_groups.setdefault(canonical_name(n), []).append(n)

    name_canonical_map: dict[str, str] = {}
    for canon, variants in canon_groups.items():
        # Scegli la versione canonica: preferisce minuscolo/misto, con punti, più lunga
        best = sorted(variants, key=lambda s: (
            s == s.upper(),                  # evita TUTTE MAIUSCOLE
            -s.count("."),                   # preferisce con punti
            -len(s),                          # preferisce versione più lunga
            s
        ))[0]
        for v in variants:
            if v != best:
                name_canonical_map[v] = best

    print(f"  Varianti da fondere: {len(name_canonical_map)}")

    # Applica fusione
    for old, new in name_canonical_map.items():
        conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old))
        conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old))
        conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old))

    # Reinserisci stazioni finali
    final_names: set[str] = set()
    for (n,) in conn.execute(
        "SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains "
        "UNION SELECT station FROM train_stops"
    ):
        if n and n.strip():
            final_names.add(n.strip())

    for name in sorted(final_names):
        conn.execute(
            "INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
            (name, normalize_station_name(name))
        )

    conn.commit()
    n_st = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"  Stazioni finali: {n_st}")

    # ── 5. Mostra stato Verona e Foggia ─────────────────────────────────────
    print("\n--- Verifica Verona ---")
    for r in conn.execute("SELECT name FROM stations WHERE lower(name) LIKE '%verona%' ORDER BY name"):
        print(f"  {r[0]!r}")
    print("\n--- Verifica Foggia ---")
    for r in conn.execute("SELECT name FROM stations WHERE lower(name) LIKE '%foggia%' ORDER BY name"):
        print(f"  {r[0]!r}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
