/**
 * API client-side: invece di chiamare un backend, esegue tutto nel browser.
 * Il DB viene caricato la prima volta e poi cached dal Service Worker.
 */
import { initDb, searchStations as dbSearchStations, getGuaranteedTrains } from './db';
import { findItineraries, type DayType, type TableType } from './router';

export type { Station, TrainStop } from './db';
export type { Itinerary, Leg } from './router';
import type { Station } from './db';
import type { Itinerary } from './router';

export interface JourneyResponse {
  query: {
    from: string;
    to: string;
    day_type: string;
    table_type: string | null;
    dep_time?: string;
  };
  count: number;
  itineraries: Itinerary[];
  meta: {
    trains_available: number;
    note: string | null;
  };
}

export async function searchStations(q: string): Promise<Station[]> {
  if (q.trim().length < 2) return [];
  try {
    return await dbSearchStations(q, 10);
  } catch (err) {
    console.error('searchStations error', err);
    return [];
  }
}

export interface SearchParams {
  from: string;
  to: string;
  depTime?: string;
  dayType: 'feriale' | 'festivo';
  tableType?: 'tabella_a' | 'tabella_b';
}

export async function searchJourney(params: SearchParams): Promise<JourneyResponse> {
  const db = await initDb();
  const trains = await getGuaranteedTrains(params.dayType, params.tableType ?? null);

  const itineraries = findItineraries(db, trains, {
    from: params.from.trim(),
    to: params.to.trim(),
    depTime: params.depTime,
    dayType: params.dayType,
    tableType: params.tableType,
    maxChanges: 1,
  });

  return {
    query: {
      from: params.from.trim(),
      to: params.to.trim(),
      day_type: params.dayType,
      table_type: params.tableType ?? null,
      dep_time: params.depTime,
    },
    count: itineraries.length,
    itineraries,
    meta: {
      trains_available: trains.length,
      note: itineraries.length === 0
        ? 'Nessun itinerario garantito trovato. Verifica i nomi delle stazioni.'
        : null,
    },
  };
}

// ── Formattazione UI (invariato) ──────────────────────────────────────────

export function formatCategory(cat: string, tableType: string): string {
  if (tableType === 'tabella_a' || tableType === 'tabella_b') {
    const map: Record<string, string> = {
      'A': 'Intercity Notte / AV Notte',
      'B': 'EuroCity / EuroNight',
      'C': 'Intercity / Intercity Notte',
      'D': 'EuroCity',
    };
    const sym: Record<string, string> = {
      '◆': 'Frecciarossa',
      '★': 'Frecciargento',
      '•': 'Frecciabianca',
    };
    return map[cat] || sym[cat] || cat || 'Lunga percorrenza';
  }
  const regionMap: Record<string, string> = {
    'REG': 'Regionale',
    'RV': 'Regionale Veloce',
    'IC': 'Intercity',
    'MET': 'Metropolitano',
    'BUS': 'Bus sostitutivo',
    'FA': 'FrecciaArgento',
    'FR': 'Frecciarossa',
    'FB': 'Frecciabianca',
  };
  return regionMap[cat?.toUpperCase()] || cat || 'Treno';
}

export function formatTableType(t: string): string {
  if (t === 'tabella_a') return 'Tabella A';
  if (t === 'tabella_b') return 'Tabella B';
  return 'Regionale';
}

export function reliabilityLabel(r: 'high' | 'medium' | 'low'): string {
  return { high: 'Alta', medium: 'Media', low: 'Bassa' }[r];
}

export function reliabilityColor(r: 'high' | 'medium' | 'low'): string {
  return {
    high: 'text-green-400',
    medium: 'text-yellow-400',
    low: 'text-red-400',
  }[r];
}
