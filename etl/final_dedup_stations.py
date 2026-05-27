"""
Pulizia finale stazioni:
1. Applica WORD_FIXES (Sul mona -> Sulmona, etc.)
2. Fonde duplicati canonici (UPPERCASE vs mixed case, con/senza punto)
"""
import sqlite3
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fix_stations import WORD_FIXES, normalize as normalize_alias
from build_db import normalize_station_name

DB = Path(__file__).parent.parent / "db" / "sciopero.db"


# Forma canonica per matching dei duplicati
def canonical(name: str) -> str:
    n = name.lower()
    n = re.sub(r"[._\-'\"]", "", n)
    n = re.sub(r"\s+", "", n)
    # Abbreviazioni comuni
    n = re.sub(r"\bcle\b|\bc.le\b|centrale", "c", n)
    n = re.sub(r"\bpn\b|\bp.n\b|\bportanuova\b", "pn", n)
    n = re.sub(r"\bs\b|\bsan\b|\bsanta\b", "s", n)
    n = re.sub(r"\bsmn\b|santamarianovella", "smn", n)
    return n


def apply_word_fixes(name: str) -> str:
    """Applica WORD_FIXES e altre normalizzazioni."""
    if not name:
        return name
    s = name
    for wrong, right in WORD_FIXES.items():
        s = s.replace(wrong, right)
    # Normalizza "P.N" → "P.N." e "C.le" → "Centrale" per uniformità visiva
    s = re.sub(r"\bP\.N(?!\.)", "P.N.", s)
    # Trim
    s = re.sub(r"\s+", " ", s).strip()
    return s


def choose_canonical(variants: list[str]) -> str:
    """Sceglie la migliore tra varianti dello stesso nome."""
    # Punteggio: più alto = migliore
    def score(s: str) -> tuple:
        is_all_upper = s == s.upper()
        has_dot = "." in s
        # Preferisce: non tutto maiuscolo, con punti, abbastanza lungo, ordine alfabetico
        return (not is_all_upper, has_dot, len(s) > 5, -len(s), s)
    return max(variants, key=score)


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    print("=" * 60)
    print("PULIZIA FINALE STAZIONI")
    print("=" * 60)

    # Step 1: Applica WORD_FIXES a tutto
    print("\nStep 1: applica WORD_FIXES (Sul mona -> Sulmona, ecc.)...")
    fixed = 0
    for table, col in [("guaranteed_trains", "origin"), ("guaranteed_trains", "destination"),
                       ("train_stops", "station"), ("stations", "name")]:
        rows = conn.execute(f"SELECT rowid AS rid, {col} AS val FROM {table}").fetchall()
        for r in rows:
            old = r["val"]
            new = apply_word_fixes(old)
            if new != old and new:
                try:
                    conn.execute(f"UPDATE {table} SET {col}=? WHERE rowid=?", (new, r["rid"]))
                    fixed += 1
                except sqlite3.IntegrityError:
                    pass
    print(f"  WORD_FIXES applicati: {fixed}")

    # Step 2: Fondi duplicati canonici
    print("\nStep 2: fondi varianti dello stesso nome...")
    all_names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n: all_names.add(n.strip())

    canon_groups: dict[str, list[str]] = {}
    for n in all_names:
        c = canonical(n)
        if c:
            canon_groups.setdefault(c, []).append(n)

    rename_map = {}
    for canon, variants in canon_groups.items():
        if len(variants) <= 1:
            continue
        best = choose_canonical(variants)
        for v in variants:
            if v != best:
                rename_map[v] = best

    print(f"  Varianti da fondere: {len(rename_map)}")
    for old, new in list(rename_map.items())[:15]:
        print(f"    '{old}' -> '{new}'")

    for old, new in rename_map.items():
        conn.execute("UPDATE guaranteed_trains SET origin=? WHERE origin=?", (new, old))
        conn.execute("UPDATE guaranteed_trains SET destination=? WHERE destination=?", (new, old))
        # train_stops potrebbe collidere con (train_number, sequence) unique
        # ma siccome cambiamo solo station non c'è problema
        conn.execute("UPDATE train_stops SET station=? WHERE station=?", (new, old))

    # Step 3: Dedup esatto guaranteed_trains
    print("\nStep 3: dedup treni identici (post-fusione)...")
    n_before = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    conn.execute("""
        DELETE FROM guaranteed_trains WHERE id NOT IN (
            SELECT MIN(id) FROM guaranteed_trains
            GROUP BY train_number, origin, destination, dep_time, day_type, table_type
        )
    """)
    n_after = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    print(f"  Treni eliminati: {n_before - n_after}")

    # Step 4: Ricostruisci stations
    print("\nStep 4: ricostruisci stations...")
    conn.execute("DELETE FROM stations")
    final_names = set()
    for (n,) in conn.execute("SELECT origin FROM guaranteed_trains UNION SELECT destination FROM guaranteed_trains UNION SELECT station FROM train_stops"):
        if n and n.strip(): final_names.add(n.strip())
    for n in sorted(final_names):
        conn.execute("INSERT OR IGNORE INTO stations(name, normalized_name) VALUES (?, ?)",
                     (n, normalize_station_name(n)))

    conn.commit()

    # Stato finale
    print("\n" + "=" * 60)
    print("STATO FINALE:")
    n_st = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    n_tr = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    n_reg = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
    print(f"  Stazioni:  {n_st}")
    print(f"  Treni:     {n_tr} ({n_reg} regionali)")

    print("\n--- Stazioni Pescara/Sulmona/Termoli ---")
    for r in conn.execute("SELECT name FROM stations WHERE lower(name) LIKE '%pescara%' OR lower(name) LIKE '%sulmona%' OR lower(name) LIKE '%termoli%' OR lower(name) LIKE '%teramo%' ORDER BY name"):
        print(f"  '{r[0]}'")

    print("\n--- Stazioni Verona/Foggia/S.Benedetto ---")
    for r in conn.execute("SELECT name FROM stations WHERE lower(name) LIKE '%verona%' OR lower(name) LIKE '%foggia%' OR lower(name) LIKE '%benedetto%' ORDER BY name"):
        print(f"  '{r[0]}'")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
