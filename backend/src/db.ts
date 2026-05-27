import initSqlJs, { type Database, type QueryExecResult } from 'sql.js';
import path from 'path';
import fs from 'fs';

const DB_PATH = path.join(__dirname, '..', '..', 'db', 'sciopero.db');

let _db: Database | null = null;

export async function initDb(): Promise<void> {
  if (_db) return;
  if (!fs.existsSync(DB_PATH)) {
    throw new Error(
      `Database non trovato: ${DB_PATH}\n` +
      `Eseguire prima: cd etl && python build_db.py`
    );
  }
  const SQL = await initSqlJs();
  const fileBuffer = fs.readFileSync(DB_PATH);
  _db = new SQL.Database(fileBuffer);
}

function getDb(): Database {
  if (!_db) throw new Error('DB non inizializzato - chiamare initDb()');
  return _db;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function rows<T>(res: QueryExecResult[]): T[] {
  if (!res || res.length === 0) return [];
  const { columns, values } = res[0];
  return values.map(row => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, i) => { obj[col] = row[i]; });
    return obj as T;
  });
}

function query<T>(sql: string, params: (string | number | null)[] = []): T[] {
  const db = getDb();
  const stmt = db.prepare(sql);
  stmt.bind(params);
  const result: T[] = [];
  while (stmt.step()) {
    result.push(stmt.getAsObject() as T);
  }
  stmt.free();
  return result;
}

// ── Types ─────────────────────────────────────────────────────────────────────

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

// ── Queries ───────────────────────────────────────────────────────────────────

export function searchStations(q: string, limit = 20): Station[] {
  const upper = q.toUpperCase().trim();
  const raw = query<Station>(
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

  // Deduplicazione per normalized_name: preferisce nome misto ("Roma Termini")
  // rispetto al tutto maiuscolo ("ROMA TERMINI")
  const seen = new Map<string, Station>();
  for (const s of raw) {
    const existing = seen.get(s.normalized_name);
    if (!existing) {
      seen.set(s.normalized_name, s);
    } else if (existing.name === existing.name.toUpperCase() &&
               s.name !== s.name.toUpperCase()) {
      seen.set(s.normalized_name, s);
    }
  }

  return Array.from(seen.values()).slice(0, limit);
}

export function getGuaranteedTrains(
  dayType: 'feriale' | 'festivo',
  tableType: 'tabella_a' | 'tabella_b' | null,
): GuaranteedTrain[] {
  if (tableType === 'tabella_b') {
    return query<GuaranteedTrain>(
      `SELECT * FROM guaranteed_trains
       WHERE day_type = ? OR day_type = 'entrambi' OR table_type = 'tabella_b'
       ORDER BY dep_time`,
      [dayType]
    );
  }
  return query<GuaranteedTrain>(
    `SELECT * FROM guaranteed_trains
     WHERE day_type = ? OR day_type = 'entrambi'
     ORDER BY dep_time`,
    [dayType]
  );
}

export function getTrainStops(trainNumber: string): TrainStop[] {
  return query<TrainStop>(
    `SELECT train_number, station, sequence, arrival, departure
     FROM train_stops
     WHERE train_number = ?
     ORDER BY sequence`,
    [trainNumber]
  );
}
