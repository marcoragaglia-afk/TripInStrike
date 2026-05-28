/**
 * Motore di routing per itinerari garantiti in giornata di sciopero.
 *
 * Strategia di matching:
 * - Solo origine/destinazione di ogni treno garantito per il routing.
 *   Le fermate intermedie (train_stops) sono usate SOLO per la visualizzazione,
 *   mai per decidere se un treno copre una stazione (dati troppo inaffidabili).
 * - Connessione diretta: train.origin ≈ from AND train.destination ≈ to
 * - Un cambio: trainA.origin ≈ from, trainA.destination ≈ trainB.origin,
 *              trainB.destination ≈ to
 */

import type { Database } from 'sql.js';
import type { GuaranteedTrain, TrainStop } from './db';
import { getTrainStopsSync } from './db';

export type DayType = 'feriale' | 'festivo';
export type TableType = 'tabella_a' | 'tabella_b';

export interface SearchParams {
  from: string;
  to: string;
  depTime?: string;
  dayType: DayType;
  tableType?: TableType;
  maxChanges?: number;
}

export interface Leg {
  trainNumber: string;
  category: string;
  tableType: string;
  origin: string;
  destination: string;
  boardAt: string;
  alightAt: string;
  depTime: string;
  arrTime: string;
  stops: TrainStop[];
  notes: string;
  reliability: 'high' | 'medium' | 'low';
}

export interface Itinerary {
  legs: Leg[];
  totalTime: number;
  changes: number;
  reliability: 'high' | 'medium' | 'low';
  warnings: string[];
}

// ── Utilità temporali ─────────────────────────────────────────────────────────

function parseTime(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

/** Minuti tra due orari, gestisce il passaggio a mezzanotte. */
function timeDiff(from: string, to: string): number {
  let d = parseTime(to) - parseTime(from);
  if (d < 0) d += 24 * 60;
  return d;
}

const MIN_TRANSFER_MINS = 5;
const MAX_TRANSFER_MINS = 6 * 60; // 6 ore: in sciopero le attese al cambio possono essere lunghe
const LONG_TRANSFER_WARN = 90;    // sopra questa soglia mostra avviso attesa lunga
const MAX_JOURNEY_MINS = 20 * 60; // filtra dati palesemente errati

// ── Normalizzazione e matching stazioni ──────────────────────────────────────

function normalizeStation(s: string): string {
  return s
    .toUpperCase()
    .replace(/\bS\.?\s*M\.?\s*N(?:OVELLA)?\.?/g, 'SANTA MARIA NOVELLA')
    .replace(/\bC\.LE\b|\bCLE\b|\bCENTR\b/g, 'CENTRALE')
    .replace(/\bP\.NUOVA\b|\bP\.N\.\b/g, 'PORTA NUOVA')
    .replace(/\bP\.GARIBALDI\b/g, 'PORTA GARIBALDI')
    .replace(/\bS\.\s*/g, 'SAN ')
    .replace(/\bD\.T\.?\b/g, 'DEL TRONTO')
    .replace(/[-']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Prefissi troppo generici per il fallback città (evita falsi positivi).
// REGGIO è ambiguo (Emilia vs Calabria). MONTE / CASTEL / CAMPO / COLLE iniziano
// molti toponimi italiani diversi tra loro.
const GENERIC_CITY_PREFIXES = new Set([
  'SAN', 'SANTA', 'SANTO', 'SS',
  'PORTO', 'TORRE', 'VILLA', 'CAPO',
  'REGGIO',
  'MONTE', 'MONTI',
  'CASTEL', 'CASTELLO',
  'CAMPO',
  'COLLE',
  'BORGO',
  'CAVA',
  'PIEVE',
  'ROCCA',
]);

/**
 * Matching per prefisso di parola (word-prefix).
 * "BOLOGNA" corrisponde a "BOLOGNA CENTRALE".
 * "ROMA TERMINI" NON corrisponde a "TERMINI IMERESE".
 * Fallback città: "FIRENZE SANTA MARIA NOVELLA" corrisponde a "FIRENZE C. MARTE"
 * perché durante lo sciopero qualsiasi stazione della stessa città è accettabile.
 */
function stationMatch(a: string, b: string): boolean {
  const na = normalizeStation(a);
  const nb = normalizeStation(b);
  if (na === nb) return true;

  const wa = na.split(' ').filter(Boolean);
  const wb = nb.split(' ').filter(Boolean);
  if (wa.length === 0 || wb.length === 0) return false;

  // Prefisso esatto: "BOLOGNA" corrisponde a "BOLOGNA CENTRALE"
  const [shorter, longer] = wa.length <= wb.length ? [wa, wb] : [wb, wa];
  if (shorter.every((w, i) => w === longer[i])) return true;

  // Fallback città: stesso primo token = stessa città
  // (non per prefissi generici come SAN/SANTA che non indicano una città specifica)
  if (!GENERIC_CITY_PREFIXES.has(wa[0]) && wa[0] === wb[0]) return true;

  return false;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function reliabilityScore(train: GuaranteedTrain): 'high' | 'medium' | 'low' {
  if (train.table_type === 'tabella_a' || train.table_type === 'tabella_b') return 'high';
  if (train.notes?.toLowerCase().includes('potrebbe')) return 'medium';
  return 'high';
}

function minReliability(
  a: 'high' | 'medium' | 'low',
  b: 'high' | 'medium' | 'low',
): 'high' | 'medium' | 'low' {
  const rank = { high: 2, medium: 1, low: 0 };
  return rank[a] < rank[b] ? a : b;
}

/** Ricava l'orario di arrivo dalle fermate quando arr_time è NULL nel DB. */
function lookupArrTime(stops: TrainStop[], alightAt: string): string {
  if (!stops.length) return '';
  const found = stops.find(s => stationMatch(s.station, alightAt));
  if (found) return found.arrival || found.departure || '';
  // Non usiamo il fallback sull'ultima fermata: i dati delle fermate intermedie
  // possono essere contaminati da treni adiacenti nel PDF, dando tempi falsi.
  return '';
}

/**
 * Per i treni AV (tabella_a) cerca le fermate di salita e discesa all'interno
 * delle stops, verificando che la sequenza sia corretta (salita < discesa).
 * Restituisce null se non trovate o in sequenza errata.
 */
function findStopLeg(
  stops: TrainStop[],
  boardStation: string,
  alightStation: string,
): { boardTime: string; alightTime: string } | null {
  if (!stops.length) return null;
  const boardIdx = stops.findIndex(s => stationMatch(s.station, boardStation));
  const alightIdx = stops.findIndex(s => stationMatch(s.station, alightStation));
  if (boardIdx === -1 || alightIdx === -1 || boardIdx >= alightIdx) return null;
  const boardStop = stops[boardIdx];
  const alightStop = stops[alightIdx];
  const boardTime = boardStop.departure || boardStop.arrival || '';
  const alightTime = alightStop.arrival || alightStop.departure || '';
  if (!boardTime) return null;
  return { boardTime, alightTime };
}

function makeLeg(
  train: GuaranteedTrain,
  boardAt: string,
  alightAt: string,
  depTime: string,
  arrTime: string,
  stops: TrainStop[],
): Leg {
  return {
    trainNumber: train.train_number,
    category: train.category || '',
    tableType: train.table_type,
    origin: train.origin,
    destination: train.destination,
    boardAt,
    alightAt,
    depTime,
    arrTime,
    stops,
    notes: train.notes || '',
    reliability: reliabilityScore(train),
  };
}

// ── Motore di routing principale ──────────────────────────────────────────────

export function findItineraries(
  db: Database,
  trains: GuaranteedTrain[],
  params: SearchParams,
): Itinerary[] {
  const { from, to, depTime = '00:00', maxChanges = 1 } = params;
  const minDep = parseTime(depTime);
  const results: Itinerary[] = [];

  if (stationMatch(from, to)) return [];

  // Pre-carica fermate per il routing e la visualizzazione
  const stopsCache = new Map<string, TrainStop[]>();
  for (const t of trains) {
    stopsCache.set(t.train_number, getTrainStopsSync(db, t.train_number));
  }

  // ── Fase 1: Connessioni dirette ───────────────────────────────────────────
  // Criteri primari: origin ≈ from  E  destination ≈ to.
  // Esteso per treni tabella_a: se i criteri primari non matchano, cerca fermate
  // intermedie nel percorso (es. salire a Bologna su un Napoli→Torino).
  for (const train of trains) {
    if (!train.dep_time) continue;

    const stops = stopsCache.get(train.train_number) || [];

    const primaryMatch =
      stationMatch(train.origin, from) && stationMatch(train.destination, to);

    if (primaryMatch) {
      const depMins = parseTime(train.dep_time);
      if (depMins < minDep) continue;

      const arrTime = train.arr_time || lookupArrTime(stops, to);
      const totalTime = arrTime ? timeDiff(train.dep_time, arrTime) : 0;
      if (totalTime > MAX_JOURNEY_MINS) continue;

      const warnings: string[] = [];
      if (train.notes) warnings.push(train.notes);
      if (!arrTime) warnings.push("Orario arrivo non disponibile: verificare sul treno");
      if (arrTime && parseTime(arrTime) < parseTime(train.dep_time)) warnings.push("Arrivo il giorno successivo");

      results.push({
        legs: [makeLeg(train, from, to, train.dep_time, arrTime, stops)],
        totalTime,
        changes: 0,
        reliability: reliabilityScore(train),
        warnings,
      });
    } else if (stops.length > 0) {
      // Treno AV o regionale con fermate validate: cerca salita/discesa nel percorso.
      // Per i regionali costruisce lista estesa includendo origine e destinazione
      // come fermate virtuali (così funziona Rimini→Bologna su un treno Ancona→Bologna).
      const fullStops: TrainStop[] = train.table_type === 'tabella_a' ? stops : [
        { train_number: train.train_number, station: train.origin,      sequence: -1,   arrival: '',                departure: train.dep_time! },
        ...stops,
        { train_number: train.train_number, station: train.destination, sequence: 9999, arrival: train.arr_time || '', departure: '' },
      ];
      const leg = findStopLeg(fullStops, from, to);
      if (!leg) continue;
      if (parseTime(leg.boardTime) < minDep) continue;

      const totalTime = leg.alightTime ? timeDiff(leg.boardTime, leg.alightTime) : 0;
      if (totalTime > MAX_JOURNEY_MINS) continue;

      const warnings: string[] = [];
      if (train.notes) warnings.push(train.notes);
      if (!leg.alightTime) warnings.push("Orario arrivo non disponibile: verificare sul treno");
      if (leg.alightTime && parseTime(leg.alightTime) < parseTime(leg.boardTime)) warnings.push("Arrivo il giorno successivo");

      results.push({
        legs: [makeLeg(train, from, to, leg.boardTime, leg.alightTime, stops)],
        totalTime,
        changes: 0,
        reliability: reliabilityScore(train),
        warnings,
      });
    }
  }

  // ── Fase 2: Connessioni con un cambio ─────────────────────────────────────
  // TrainA: origin ≈ from O passa per 'from' (fermata intermedia), arriva alla stazione di cambio.
  // TrainB: parte dalla stazione di cambio, destination ≈ to (o fermata intermedia).
  if (maxChanges >= 1) {
    // trainA candidates: origine = from OPPURE 'from' è una fermata intermedia
    const trainsFromOrigin = trains.filter(t => {
      if (!t.dep_time) return false;
      if (stationMatch(t.origin, from)) {
        return parseTime(t.dep_time) >= minDep;
      }
      // Cerca 'from' come fermata intermedia
      const stops = stopsCache.get(t.train_number) || [];
      const fromStop = stops.find(s => stationMatch(s.station, from));
      if (!fromStop) return false;
      const boardT = fromStop.departure || fromStop.arrival;
      return !!boardT && parseTime(boardT) >= minDep;
    });

    // trainB: destinazione ≈ to  OPPURE  treno con fermata 'to' nel percorso
    const trainsToDestination = trains.filter(t =>
      t.dep_time && (
        stationMatch(t.destination, to) ||
        (stopsCache.get(t.train_number) || []).some(s => stationMatch(s.station, to))
      ),
    );

    for (const trainA of trainsFromOrigin) {
      const stopsA = stopsCache.get(trainA.train_number) || [];
      // Determina punto di salita su trainA (può essere origine o fermata intermedia)
      let boardATime: string;
      let boardAStation: string;
      if (stationMatch(trainA.origin, from)) {
        boardATime = trainA.dep_time!;
        boardAStation = trainA.origin;
      } else {
        const stop = stopsA.find(s => stationMatch(s.station, from));
        if (!stop) continue;
        boardATime = stop.departure || stop.arrival || '';
        if (!boardATime) continue;
        boardAStation = stop.station;
      }

      // Per ogni possibile stazione di cambio: una fermata intermedia di trainA
      // (in ordine cronologico) OPPURE la destinazione finale.
      // NB: mettiamo PRIMA le intermedie e POI la destinazione perché i cambi
      // più vicini all'origine sono preferibili (meno tempo "sprecato" sul treno A).
      type ChangePoint = { station: string; arrTime: string };
      const changePoints: ChangePoint[] = [];
      const boardIdxA = stopsA.findIndex(s => stationMatch(s.station, boardAStation));
      // Fermate intermedie DOPO il punto di salita (ordinate per sequenza = cronologiche)
      for (let i = boardIdxA + 1; i < stopsA.length; i++) {
        const s = stopsA[i];
        const arrT = s.arrival || s.departure;
        if (arrT && !stationMatch(s.station, boardAStation) && !stationMatch(s.station, from)) {
          changePoints.push({ station: s.station, arrTime: arrT });
        }
      }
      // Destinazione finale come ULTIMO punto di cambio possibile
      const finalArr = trainA.arr_time || lookupArrTime(stopsA, trainA.destination);
      if (finalArr && !changePoints.some(c => stationMatch(c.station, trainA.destination))) {
        changePoints.push({ station: trainA.destination, arrTime: finalArr });
      }

      // Se trainA passa attraverso la destinazione 'to', individua dove.
      // Tutti i changePoint DOPO 'to' vanno scartati: sarebbe assurdo
      // andare oltre la destinazione e poi tornare indietro con un altro treno.
      const toStopIdxA = stopsA.findIndex(s => stationMatch(s.station, to));
      const toIsDestA = stationMatch(trainA.destination, to);

      for (const cp of changePoints) {
        const arrForCalc = cp.arrTime;
        const changeStation = cp.station;

        // Skip se trainA passa per 'to' PRIMA del cambio (combinazione redundante)
        if (toStopIdxA !== -1 || toIsDestA) {
          const cpStopIdxA = stopsA.findIndex(s => stationMatch(s.station, cp.station));
          // Effective "to" position: indice della fermata 'to' oppure fine (=destination)
          const toPosA = toStopIdxA !== -1 ? toStopIdxA : stopsA.length;
          // Posizione effettiva di cp: la sua sequence o stopsA.length se è destination
          const cpPosA = cpStopIdxA !== -1 ? cpStopIdxA : stopsA.length;
          // Se 'to' precede cp sul percorso di trainA, salta
          if (toPosA < cpPosA) continue;
          // Anche se to e cp coincidono: il viaggio è "diretto" gestito in Fase 1
          if (toPosA === cpPosA) continue;
        }

        const travelA = timeDiff(boardATime, arrForCalc);
        if (travelA > MAX_JOURNEY_MINS) continue;

      for (const trainB of trainsToDestination) {
        if (trainB.train_number === trainA.train_number) continue;

        const stopsB = stopsCache.get(trainB.train_number) || [];

        // Determina punto di salita su trainB: origine o fermata intermedia
        let boardBTime: string;
        let boardBStation: string;

        if (stationMatch(changeStation, trainB.origin)) {
          boardBTime = trainB.dep_time!;
          boardBStation = trainB.origin;
        } else {
          const stop = stopsB.find(s => stationMatch(s.station, changeStation));
          if (!stop) continue;
          boardBTime = stop.departure || stop.arrival || '';
          if (!boardBTime) continue;
          boardBStation = stop.station;
        }

        // Determina punto di discesa su trainB
        let alightBTime: string;

        if (stationMatch(trainB.destination, to)) {
          alightBTime = trainB.arr_time || lookupArrTime(stopsB, to);
        } else {
          // Discesa a fermata intermedia
          const stop = stopsB.find(s => stationMatch(s.station, to));
          if (!stop) continue;
          // Verifica che la discesa venga dopo la salita
          const boardIdx = stopsB.findIndex(s => stationMatch(s.station, boardBStation));
          const alightIdx = stopsB.indexOf(stop);
          if (boardIdx === -1 || alightIdx <= boardIdx) continue;
          alightBTime = stop.arrival || stop.departure || '';
        }

        const travelB = alightBTime ? timeDiff(boardBTime, alightBTime) : 0;
        if (travelB > MAX_JOURNEY_MINS) continue;

        const transfer = timeDiff(arrForCalc, boardBTime);
        if (transfer < MIN_TRANSFER_MINS || transfer > MAX_TRANSFER_MINS) continue;

        const totalTime = alightBTime ? timeDiff(boardATime, alightBTime) : 0;
        if (totalTime > MAX_JOURNEY_MINS) continue;

        const warnings: string[] = [];
        if (trainA.notes) warnings.push(trainA.notes);
        if (trainB.notes) warnings.push(trainB.notes);
        if (!alightBTime) warnings.push("Orario arrivo finale non disponibile: verificare sul treno");
        if (transfer > LONG_TRANSFER_WARN) warnings.push(`Attesa lunga al cambio: ${Math.floor(transfer / 60)}h${String(transfer % 60).padStart(2, '0')}min a ${changeStation}`);
        if (alightBTime && parseTime(alightBTime) < parseTime(boardATime)) warnings.push("Arrivo il giorno successivo");

        results.push({
          legs: [
            makeLeg(
              trainA, from, changeStation,
              boardATime, arrForCalc,
              stopsA,
            ),
            makeLeg(
              trainB, boardBStation, to,
              boardBTime, alightBTime,
              stopsB,
            ),
          ],
          totalTime,
          changes: 1,
          reliability: minReliability(
            reliabilityScore(trainA),
            reliabilityScore(trainB),
          ),
          warnings,
        });
      }
      }
    }
  }

  // ── Deduplication e ordinamento ───────────────────────────────────────────
  // 1) Dedup esatto: stesso treno A + treno B + stesso punto di cambio
  const seenExact = new Set<string>();
  let unique = results.filter(r => {
    const key = r.legs.map(l => `${l.trainNumber}|${l.depTime}|${l.boardAt}`).join('>');
    if (seenExact.has(key)) return false;
    seenExact.add(key);
    return true;
  });

  // 2) Dedup "intelligente" per cambi: se abbiamo lo STESSO treno A con stesso
  //    orario di partenza E lo STESSO treno B (con orari diversi al cambio),
  //    teniamo solo quello con il cambio CRONOLOGICAMENTE PIÙ ANTICIPATO sul
  //    percorso di trainA — è il cambio più vicino all'origine, quindi più logico.
  //    NB: tieni conto che lo stesso (A,B) può apparire con cambio a Bologna E a Milano:
  //    Bologna arriva prima -> meno tempo sprecato su A -> preferito.
  const bestPerPair = new Map<string, Itinerary>();
  for (const it of unique) {
    if (it.changes !== 1) {
      // Diretti o multi-cambio: non dedupare
      const k = `${it.legs[0].trainNumber}|${it.legs[0].depTime}|direct|${it.legs.length}`;
      if (!bestPerPair.has(k)) bestPerPair.set(k, it);
      continue;
    }
    const a = it.legs[0];
    const b = it.legs[1];
    // Chiave per la coppia (treno A + dep A) + (treno B + alight B)
    const pairKey = `${a.trainNumber}|${a.depTime}>${b.trainNumber}|${b.alightAt}`;
    const existing = bestPerPair.get(pairKey);
    if (!existing) {
      bestPerPair.set(pairKey, it);
    } else {
      // Tieni quello con cambio PRIMA (boardBTime minore = boardiamo trainB prima)
      const existingChangeTime = parseTime(existing.legs[1].depTime);
      const newChangeTime = parseTime(it.legs[1].depTime);
      if (newChangeTime < existingChangeTime) {
        bestPerPair.set(pairKey, it);
      }
    }
  }
  unique = Array.from(bestPerPair.values());

  // 3) Ordinamento finale: prima per numero di cambi, poi per orario partenza,
  //    poi per durata totale (a parità, percorso più corto vince).
  unique.sort((a, b) => {
    if (a.changes !== b.changes) return a.changes - b.changes;
    const depDiff = parseTime(a.legs[0].depTime) - parseTime(b.legs[0].depTime);
    if (depDiff !== 0) return depDiff;
    return a.totalTime - b.totalTime;
  });

  return unique.slice(0, 20);
}
