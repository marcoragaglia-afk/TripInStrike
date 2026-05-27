/**
 * Database loader client-side.
 * Carica sciopero.db come asset statico, lo apre con sql.js (WASM nel browser).
 * Il DB viene cachato dal Service Worker dopo la prima visita -> funziona offline.
 */
import initSqlJs, { type Database } from 'sql.js';

let _db: Database | null = null;
let _loading: Promise<Database> | null = null;

export async function initDb(): Promise<Database> {
  if (_db) return _db;
  if (_loading) return _loading;

  _loading = (async () => {
    // sql.js richiede di scaricare il file .wasm separato.
    // Lo serviamo localmente da /sql-wasm.wasm (cached dal SW per uso offline).
    const SQL = await initSqlJs({
      locateFile: (file: string) => `/${file}`,
    });

    // Scarica il DB precostruito (~2MB, cached dal SW dopo la prima volta)
    const res = await fetch('/sciopero.db');
    if (!res.ok) throw new Error(`DB non disponibile: HTTP ${res.status}`);
    const buf = new Uint8Array(await res.arrayBuffer());
    _db = new SQL.Database(buf);
    return _db;
  })();

  return _loading;
}

function rows<T>(db: Database, sql: string, params: (string | number | null)[] = []): T[] {
  const stmt = db.prepare(sql);
  stmt.bind(params);
  const result: T[] = [];
  while (stmt.step()) result.push(stmt.getAsObject() as T);
  stmt.free();
  return result;
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface GuaranteedTrain {
  id: number;
  train_number: string;
  category: string | null;
  origin: string;
  destination: string;
  dep_time: string | null;
  arr_time: string | null;
  day_type: string;
  table_type: string;
  region: string | null;
  line: string | null;
  notes: string | null;
  validity: string | null;
}

export interface TrainStop {
  train_number: string;
  station: string;
  sequence: number;
  arrival: string | null;
  departure: string | null;
}

export interface Station {
  id: number;
  name: string;
  normalized_name: string;
  region: string | null;
}

// ── Queries ─────────────────────────────────────────────────────────────────

export async function searchStations(q: string, limit = 20): Promise<Station[]> {
  if (q.trim().length < 2) return [];
  const db = await initDb();
  const upper = q.toUpperCase().trim();
  const raw = rows<Station>(db,
    `SELECT id, name, normalized_name, region
     FROM stations
     WHERE normalized_name LIKE ? OR name LIKE ?
     ORDER BY
       CASE WHEN normalized_name = ? THEN 0
            WHEN normalized_name LIKE ? || '%' THEN 1
            ELSE 2 END,
       length(name),
       name
     LIMIT ?`,
    [`%${upper}%`, `%${upper}%`, upper, upper, limit * 3]
  );
  // Dedup preferendo nome misto
  const seen = new Map<string, Station>();
  for (const s of raw) {
    const ex = seen.get(s.normalized_name);
    if (!ex) seen.set(s.normalized_name, s);
    else if (ex.name === ex.name.toUpperCase() && s.name !== s.name.toUpperCase()) {
      seen.set(s.normalized_name, s);
    }
  }
  return Array.from(seen.values()).slice(0, limit);
}

export async function getGuaranteedTrains(
  dayType: 'feriale' | 'festivo',
  tableType: 'tabella_a' | 'tabella_b' | null,
): Promise<GuaranteedTrain[]> {
  const db = await initDb();
  if (tableType === 'tabella_b') {
    return rows<GuaranteedTrain>(db,
      `SELECT * FROM guaranteed_trains
       WHERE day_type = ? OR day_type = 'entrambi' OR table_type = 'tabella_b'
       ORDER BY dep_time`,
      [dayType]
    );
  }
  return rows<GuaranteedTrain>(db,
    `SELECT * FROM guaranteed_trains
     WHERE day_type = ? OR day_type = 'entrambi'
     ORDER BY dep_time`,
    [dayType]
  );
}

export async function getTrainStops(trainNumber: string): Promise<TrainStop[]> {
  const db = await initDb();
  return rows<TrainStop>(db,
    `SELECT train_number, station, sequence, arrival, departure
     FROM train_stops WHERE train_number = ? ORDER BY sequence`,
    [trainNumber]
  );
}

/** Versione sincrona: presuppone DB già caricato. Usata dal router. */
export function getTrainStopsSync(db: Database, trainNumber: string): TrainStop[] {
  return rows<TrainStop>(db,
    `SELECT train_number, station, sequence, arrival, departure
     FROM train_stops WHERE train_number = ? ORDER BY sequence`,
    [trainNumber]
  );
}
