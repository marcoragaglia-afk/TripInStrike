"""
Aggiunge Bologna Centrale come fermata "virtuale" per gli AV che la attraversano
logicamente ma non l'hanno nelle fermate per dati PDF incompleti.

Regola: un treno passa per Bologna se collega:
  - Stazione sud (Napoli/Salerno/Roma/Firenze/Bari/Lecce/Reggio) <-> Stazione nord-est (Venezia/Padova/Verona/Trieste/Udine)
  - Stazione sud <-> Stazione nord-ovest (Milano/Torino/Genova) andando via dorsale tirreno-adriatica

Aggiungiamo solo per i treni che hanno arr_time noto (così abbiamo tempi affidabili).
"""
import sqlite3
import re
from pathlib import Path

DB = Path(__file__).parent.parent / "db" / "sciopero.db"

# Stazioni a sud di Bologna lungo la dorsale tirreno-adriatica
SOUTH_OF_BOLOGNA = re.compile(r"NAPOLI|SALERNO|ROMA|FIRENZE|BARI|LECCE|TARANTO|REGGIO|FOGGIA|PESCARA|ANCONA|SIRACUSA|BRINDISI", re.I)
# Stazioni a nord di Bologna sulla linea Bologna-Padova-Venezia
NORTH_EAST_OF_BOLOGNA = re.compile(r"VENEZIA|PADOVA|TREVISO|UDINE|TRIESTE|PORTOGRUARO|MESTRE|FERRARA|ROVIGO", re.I)
# A nord-ovest (Milano via Modena)
NORTH_WEST_OF_BOLOGNA = re.compile(r"MILANO|TORINO|GENOVA|BRESCIA|VERONA|VICENZA", re.I)


def passes_through_bologna(origin: str, dest: str) -> bool:
    """True se il treno passa logicamente per Bologna."""
    o, d = origin.upper(), dest.upper()
    south_o = bool(SOUTH_OF_BOLOGNA.search(o))
    south_d = bool(SOUTH_OF_BOLOGNA.search(d))
    ne_o = bool(NORTH_EAST_OF_BOLOGNA.search(o))
    ne_d = bool(NORTH_EAST_OF_BOLOGNA.search(d))
    nw_o = bool(NORTH_WEST_OF_BOLOGNA.search(o))
    nw_d = bool(NORTH_WEST_OF_BOLOGNA.search(d))

    # sud <-> nord-est passa per Bologna
    if (south_o and ne_d) or (ne_o and south_d):
        return True
    # sud <-> nord-ovest passa per Bologna (NB: anche Milano-Roma)
    if (south_o and nw_d) or (nw_o and south_d):
        return True
    # nord-est <-> nord-ovest NON passa per Bologna (va via Verona-Brescia)
    return False


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Per ogni AV passante per Bologna che NON ha Bologna nelle stops:
    avs = conn.execute("""
        SELECT id, train_number, origin, destination, dep_time, arr_time, table_type
        FROM guaranteed_trains
        WHERE table_type IN ('tabella_a','tabella_b')
    """).fetchall()

    # Determina arrivi/partenze noti di Bologna su questa tratta dai treni che CE l'hanno
    print("Analisi AV che dovrebbero passare per Bologna...")
    candidates = []
    for av in avs:
        if not passes_through_bologna(av["origin"], av["destination"]):
            continue
        # Verifica se ha già Bologna nelle stops
        has_bologna = conn.execute(
            "SELECT COUNT(*) FROM train_stops WHERE train_number=? AND (station LIKE '%Bologna%' OR station LIKE '%BOLOGNA%')",
            (av["train_number"],)
        ).fetchone()[0]
        if has_bologna > 0:
            continue
        # Verifica: ha origine e destinazione, almeno una fermata
        n_stops = conn.execute(
            "SELECT COUNT(*) FROM train_stops WHERE train_number=?",
            (av["train_number"],)
        ).fetchone()[0]
        candidates.append((av, n_stops))

    print(f"Candidati per aggiunta Bologna: {len(candidates)}")
    for av, n_stops in candidates[:30]:
        print(f"  {av['train_number']:6s}  {av['origin']:25s} -> {av['destination']:25s}  dep={av['dep_time']} arr={av['arr_time']}  stops={n_stops}")

    # Per ogni candidato: stimiamo il tempo di Bologna dal dep_time e arr_time
    # NB: usiamo una stima conservativa basata sul tempo di viaggio tipico
    # Roma -> Bologna: ~2h30 in AV
    # Milano -> Bologna: ~1h
    # Napoli -> Bologna: ~3h45
    # Firenze -> Bologna: ~37 min
    # Venezia -> Bologna: ~1h30
    # Bari -> Bologna: ~5h30 (notte) o ~4h (AV)

    def estimate_bologna_time(av):
        """Stima orario a Bologna basato su origine e dep_time."""
        from datetime import datetime, timedelta
        if not av["dep_time"]:
            return None
        try:
            dep = datetime.strptime(av["dep_time"], "%H:%M")
        except ValueError:
            return None

        o = av["origin"].upper()
        # Tempo approssimativo di viaggio dall'origine a Bologna
        TRAVEL_TO_BOLOGNA = {
            "ROMA": 150, "FIRENZE": 40, "NAPOLI": 230, "SALERNO": 270,
            "BARI": 240, "LECCE": 360, "TARANTO": 330, "REGGIO": 480,
            "FOGGIA": 180, "ANCONA": 90, "PESCARA": 180,
            "MILANO": 70, "TORINO": 130, "GENOVA": 130,
            "VENEZIA": 90, "PADOVA": 60, "TRIESTE": 180, "UDINE": 150,
            "VERONA": 50, "BRESCIA": 80, "BRINDISI": 330, "FERRARA": 30,
            "MESTRE": 90, "PORTOGRUARO": 110, "ROVIGO": 50, "VICENZA": 65,
        }
        delta = None
        for kw, mins in TRAVEL_TO_BOLOGNA.items():
            if kw in o:
                delta = mins
                break
        if delta is None:
            return None
        return (dep + timedelta(minutes=delta)).strftime("%H:%M")

    # Inserisci Bologna come fermata virtuale: trova max sequence + 1 per evitare conflitti
    added = 0
    for av, n_stops in candidates:
        est = estimate_bologna_time(av)
        if est is None:
            continue
        max_seq = conn.execute(
            "SELECT COALESCE(MAX(sequence), -1) FROM train_stops WHERE train_number=?",
            (av["train_number"],)
        ).fetchone()[0]
        new_seq = max_seq + 1
        try:
            conn.execute(
                "INSERT INTO train_stops(train_number, station, sequence, arrival, departure) VALUES (?, ?, ?, ?, ?)",
                (av["train_number"], "Bologna Centrale", new_seq, est, est)
            )
            added += 1
        except sqlite3.IntegrityError:
            pass  # già esiste

    conn.commit()
    print(f"\nFermate Bologna aggiunte: {added}")

    # Ri-ordina sequence dei treni modificati per tempo (così findStopLeg funziona correttamente)
    # 2-step per evitare collisioni di unique constraint:
    # 1) Setto tutte le sequence a -id (uniche negative)
    # 2) Setto sequence finali 0, 1, 2...
    print("Riordino sequence per tempo crescente...")
    train_nums_to_reorder = list({av["train_number"] for av, _ in candidates})
    for tn in train_nums_to_reorder:
        stops = conn.execute(
            "SELECT id, station, arrival, departure FROM train_stops WHERE train_number=? ORDER BY COALESCE(arrival, departure)",
            (tn,)
        ).fetchall()
        # Step 1: sequence temporanee uniche
        for s in stops:
            conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (-s["id"], s["id"]))
        # Step 2: sequence finali
        for i, s in enumerate(stops):
            conn.execute("UPDATE train_stops SET sequence=? WHERE id=?", (i, s["id"]))
    conn.commit()
    print(f"Riordinati {len(train_nums_to_reorder)} treni")

    conn.close()
    print("\nFatto.")


if __name__ == "__main__":
    main()
