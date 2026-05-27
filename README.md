# Sciopero Treni 🚆

Applicazione per trovare gli **itinerari ferroviari garantiti** in caso di sciopero in Italia.

Basata sui dati ufficiali Trenitalia (orario dicembre 2025 – giugno 2026).

---

## Funzionalità

- **Ricerca itinerari** da stazione a stazione durante uno sciopero
- **Filtro giornata**: feriale o festiva
- **Tabella A / B**: selezione manuale del tipo di garanzia per i treni a lunga percorrenza
- **Treni regionali** garantiti per tutte le regioni italiane
- **AV, Intercity, EuroCity** da Tabella A e B
- Funziona **offline** dopo l'installazione (PWA)

---

## Installazione (Windows)

### Requisiti
- Python 3.10+ (`winget install Python.Python.3.12`)
- Node.js 18+ (`winget install OpenJS.NodeJS.LTS`)

### Passo 1 – Installazione automatica
Doppio click su **`installa.bat`** (prima installazione, ~5 minuti)

### Passo 2 – Avvio
Doppio click su **`avvia.bat`**

L'app si aprirà automaticamente su http://localhost:3000

---

## Installazione manuale

```bash
# 1. Dipendenze Python
cd etl
pip install -r requirements.txt

# 2. Costruisci il database
python build_db.py --skip-timetable
# (oppure build_db.py per includere le fermate intermedie dall'orario completo - richiede ~30 min)

# 3. Backend
cd ../backend
npm install
npm run build
node dist/server.js &   # avvia in background su porta 3001

# 4. Frontend
cd ../frontend
npm install
npm run build
npm start               # avvia su porta 3000
```

---

## API Backend

```
GET /api/stations?q=Roma
GET /api/journey?from=Roma+Termini&to=Milano+Centrale&day_type=feriale&table_type=tabella_a
GET /api/trains?day_type=feriale
GET /api/health
```

Parametri `/api/journey`:
| Parametro | Valori | Obbligatorio |
|-----------|--------|:---:|
| `from` | nome stazione | ✓ |
| `to` | nome stazione | ✓ |
| `day_type` | `feriale` \| `festivo` | ✓ |
| `table_type` | `tabella_a` \| `tabella_b` | |
| `dep_time` | `HH:MM` | |

---

## Struttura del progetto

```
sciopero-treni/
├── etl/                    # ETL Python – parsing PDF e build database
│   ├── parse_guaranteed.py # Parser treni garantiti (merged1, merged2)
│   ├── parse_timetable.py  # Parser orario completo (fermate intermedie)
│   ├── build_db.py         # Script principale build database
│   └── requirements.txt
├── db/
│   ├── schema.sql          # Schema SQLite
│   └── sciopero.db         # Database generato (gitignore)
├── backend/                # API Node.js/TypeScript/Fastify
│   └── src/
│       ├── server.ts
│       ├── db.ts
│       ├── engine/router.ts
│       └── routes/journey.ts
├── frontend/               # Next.js/React/TypeScript PWA
│   └── src/
│       ├── app/page.tsx
│       ├── components/
│       └── lib/api.ts
├── avvia.bat               # Avvia l'applicazione (Windows)
├── installa.bat            # Prima installazione (Windows)
├── Dockerfile
└── README.md
```

---

## Logica business

### Tabella A
Treni a lunga percorrenza (AV, Intercity, EuroCity) garantiti **in ogni giornata di sciopero**, sia feriale che festiva.

### Tabella B
Treni aggiuntivi garantiti solo con queste condizioni **tutte** soddisfatte:
- Sciopero generale nazionale
- Giornata festiva
- Motivazione: rinnovo CCNL
- Durata ≤ 24 ore
- Inizio ore 21:00 del giorno prefestivo

### Treni regionali
Servizi minimi garantiti per ogni regione, con liste distinte per giorni feriali e festivi.

---

## Disclaimer

App non ufficiale. Verificare sempre le informazioni su [trenitalia.com](https://www.trenitalia.com) in caso di sciopero.
I dati fanno riferimento all'orario Trenitalia 14 dicembre 2025 – 13 giugno 2026.

---

## Licenza

MIT – uso libero con attribuzione.
