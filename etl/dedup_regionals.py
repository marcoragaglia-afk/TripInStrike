"""
Pulizia post-parsing per i treni regionali:
1. Pulisce dep_time da suffissi tipo "Linea" appiccicati alla fine.
2. Normalizza format orario: aggiunge zero iniziale (7:13 -> 07:13).
3. Deduplica per (train_number, day_type), mantenendo l'entry "migliore":
   - dep_time più piccolo (origine reale, non fermata intermedia)
   - destinazione che termina il percorso (preferisce l'ultima parola della "linea")
"""
import sqlite3
import re
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "db" / "sciopero.db"

TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})")

def fix_time(t: str) -> str | None:
    """Estrae HH:MM dall'inizio della stringa, normalizza con zero iniziale."""
    if not t:
        return None
    m = TIME_RE.match(t)
    if not m:
        return None
    h, mm = int(m.group(1)), m.group(2)
    if h > 23 or int(mm) > 59:
        return None
    return f"{h:02d}:{mm}"


def line_terminals(line: str) -> set[str]:
    """Estrae le città terminali da un nome linea: 'Linea Genova-Tortona-Milano' -> {'genova','milano'}."""
    if not line:
        return set()
    s = re.sub(r"^Linea\s+", "", line, flags=re.I)
    s = re.sub(r"\(.*?\)", "", s)
    parts = re.split(r"\s*[-–]\s*", s)
    parts = [p.strip().lower() for p in parts if p.strip()]
    if not parts:
        return set()
    return {parts[0], parts[-1]}


def dest_score(dest: str, line: str) -> int:
    """Punteggio: destinazione che appare nei terminali della linea ha priorità."""
    if not dest or not line:
        return 0
    terms = line_terminals(line)
    dl = dest.lower()
    for t in terms:
        if t and (t in dl or dl in t):
            return 10
    return 0


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("PULIZIA TRENI REGIONALI")
    print("=" * 70)

    # Step 1: Fix dep_time per tutti i regionali
    print("\nStep 1: Pulizia dep_time (rimuove suffissi tipo 'Linea')...")
    rows = conn.execute(
        "SELECT id, dep_time FROM guaranteed_trains WHERE table_type='regionale'"
    ).fetchall()
    fixed_time = 0
    deleted_no_time = 0
    for r in rows:
        new_t = fix_time(r["dep_time"])
        if new_t is None:
            conn.execute("DELETE FROM guaranteed_trains WHERE id=?", (r["id"],))
            deleted_no_time += 1
        elif new_t != r["dep_time"]:
            conn.execute("UPDATE guaranteed_trains SET dep_time=? WHERE id=?", (new_t, r["id"]))
            fixed_time += 1
    print(f"  dep_time normalizzati: {fixed_time}")
    print(f"  treni eliminati (orario invalido): {deleted_no_time}")

    # Step 2: Deduplica per (train_number, day_type)
    print("\nStep 2: Deduplica per (train_number, day_type)...")
    rows = conn.execute("""
        SELECT id, train_number, origin, destination, dep_time, arr_time, day_type, line, notes
        FROM guaranteed_trains
        WHERE table_type='regionale'
    """).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        groups[(r["train_number"], r["day_type"])].append(r)

    to_delete: list[int] = []
    multi = 0
    for key, entries in groups.items():
        if len(entries) <= 1:
            continue
        multi += 1
        # Ordina: priorità a (score destinazione vs linea desc, dep_time asc)
        sorted_e = sorted(
            entries,
            key=lambda e: (
                -dest_score(e["destination"], e["line"] or ""),
                e["dep_time"] or "99:99",
            ),
        )
        keep = sorted_e[0]
        for e in sorted_e[1:]:
            to_delete.append(e["id"])

    print(f"  Treni con duplicati: {multi}")
    print(f"  Righe da eliminare: {len(to_delete)}")

    if to_delete:
        # Eliminazione batch (limite 500 per IN)
        for i in range(0, len(to_delete), 500):
            batch = to_delete[i:i+500]
            placeholders = ",".join("?" * len(batch))
            conn.execute(
                f"DELETE FROM guaranteed_trains WHERE id IN ({placeholders})",
                batch,
            )

    conn.commit()

    # Statistiche finali
    total = conn.execute("SELECT COUNT(*) FROM guaranteed_trains").fetchone()[0]
    regional = conn.execute("SELECT COUNT(*) FROM guaranteed_trains WHERE table_type='regionale'").fetchone()[0]
    print(f"\nTotale treni: {total}")
    print(f"Totale regionali: {regional}")

    # Esempi: train 3018 dopo la pulizia
    print("\nVerifica treno 3018:")
    for r in conn.execute(
        "SELECT origin, destination, dep_time, day_type, line FROM guaranteed_trains WHERE train_number='3018'"
    ):
        print(f"  {r['origin']!r} -> {r['destination']!r}  dep={r['dep_time']}  day={r['day_type']}  line={r['line']!r}")

    print("\nVerifica treno 3019:")
    for r in conn.execute(
        "SELECT origin, destination, dep_time, day_type, line FROM guaranteed_trains WHERE train_number='3019'"
    ):
        print(f"  {r['origin']!r} -> {r['destination']!r}  dep={r['dep_time']}  day={r['day_type']}  line={r['line']!r}")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
