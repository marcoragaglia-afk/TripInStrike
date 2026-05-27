'use client';

import { useState } from 'react';
import type { Itinerary, Leg } from '@/lib/api';
import { formatCategory, formatTableType, reliabilityColor, reliabilityLabel } from '@/lib/api';

interface Props {
  itinerary: Itinerary;
  index: number;
}

function TableBadge({ tableType }: { tableType: string }) {
  const styles: Record<string, string> = {
    tabella_a: 'bg-blue-900/50 border-blue-500/40 text-blue-300',
    tabella_b: 'bg-purple-900/50 border-purple-500/40 text-purple-300',
    regionale: 'bg-green-900/50 border-green-500/40 text-green-300',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${styles[tableType] || 'bg-slate-700 text-slate-300'}`}>
      {formatTableType(tableType)}
    </span>
  );
}

function LegRow({ leg }: { leg: Leg }) {
  const [showStops, setShowStops] = useState(false);
  const hasStops = leg.stops && leg.stops.length > 0;
  const intermediateStops = leg.stops.filter(
    s => s.station !== leg.origin && s.station !== leg.destination
  );

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      {/* Header tratta */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-white/60">Treno</span>
            <span className="text-lg font-black text-white">{leg.trainNumber}</span>
            <TableBadge tableType={leg.tableType} />
            <span className="text-xs text-slate-400">
              {formatCategory(leg.category, leg.tableType)}
            </span>
          </div>
          {hasStops && intermediateStops.length > 0 && (
            <button
              onClick={() => setShowStops(!showStops)}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors flex-shrink-0"
            >
              {showStops ? '▲ Nascondi fermate' : `▼ ${intermediateStops.length} fermate intermedie`}
            </button>
          )}
        </div>

        {/* Route */}
        <div className="mt-3 flex items-center gap-3">
          {/* Salita */}
          <div className="flex-1">
            <div className="text-2xl font-black text-white tabular-nums">
              {leg.depTime || '—'}
            </div>
            <div className="text-sm text-slate-300 font-medium mt-0.5">{leg.boardAt}</div>
            {leg.boardAt !== leg.origin && (
              <div className="text-xs text-slate-500">da {leg.origin}</div>
            )}
          </div>

          {/* Freccia */}
          <div className="text-center px-2 flex-shrink-0">
            <div className="text-slate-500 text-xl">→</div>
            {leg.depTime && leg.arrTime && (
              <div className="text-xs text-slate-500 whitespace-nowrap">
                {calcDuration(leg.depTime, leg.arrTime)} min
              </div>
            )}
          </div>

          {/* Discesa */}
          <div className="flex-1 text-right">
            <div className="text-2xl font-black text-white tabular-nums">
              {leg.arrTime || '—'}
            </div>
            <div className="text-sm text-slate-300 font-medium mt-0.5">{leg.alightAt}</div>
            {leg.alightAt !== leg.destination && (
              <div className="text-xs text-slate-500">per {leg.destination}</div>
            )}
          </div>
        </div>

        {/* Note */}
        {leg.notes && (
          <div className="mt-3 text-xs text-yellow-400/90 bg-yellow-900/20 rounded-lg px-3 py-2 border border-yellow-600/20">
            ⚠️ {leg.notes}
          </div>
        )}
      </div>

      {/* Fermate intermedie */}
      {showStops && intermediateStops.length > 0 && (
        <div className="border-t border-white/10 bg-white/[0.02] px-4 py-3">
          <div className="text-xs text-slate-400 mb-2 font-semibold uppercase tracking-wider">Fermate intermedie</div>
          <div className="space-y-1.5">
            {intermediateStops.map((s, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <div className="w-2 h-2 rounded-full bg-slate-500 flex-shrink-0 ml-1" />
                <span className="text-slate-300 flex-1">{s.station}</span>
                <span className="text-slate-500 tabular-nums text-xs">
                  {s.arrival && `arr ${s.arrival}`}
                  {s.arrival && s.departure && ' / '}
                  {s.departure && `dep ${s.departure}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function calcDuration(dep: string, arr: string): number {
  const [dh, dm] = dep.split(':').map(Number);
  const [ah, am] = arr.split(':').map(Number);
  let d = (ah * 60 + am) - (dh * 60 + dm);
  if (d < 0) d += 24 * 60;
  return d;
}

export default function ItineraryCard({ itinerary, index }: Props) {
  const { legs, totalTime, changes, reliability, warnings } = itinerary;
  const firstLeg = legs[0];
  const lastLeg = legs[legs.length - 1];

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden hover:border-white/20 transition-all duration-300">
      {/* Header */}
      <div className="px-5 py-4 bg-white/[0.03] border-b border-white/10">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Numero e riepilogo */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-red-600/80 flex items-center justify-center text-sm font-black text-white flex-shrink-0">
              {index + 1}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xl font-black text-white tabular-nums">
                  {firstLeg.depTime}
                </span>
                <span className="text-slate-400">→</span>
                <span className="text-xl font-black text-white tabular-nums">
                  {lastLeg.arrTime || '—'}
                </span>
                {totalTime > 0 && (
                  <span className="text-sm text-slate-400">
                    ({Math.floor(totalTime / 60)}h{String(totalTime % 60).padStart(2, '0')}min)
                  </span>
                )}
              </div>
              <div className="text-sm text-slate-400 mt-0.5">
                {changes === 0 ? 'Diretto' : `${changes} cambio${changes > 1 ? 'i' : ''}`}
                {' · '}
                <span className={reliabilityColor(reliability)}>
                  Affidabilità {reliabilityLabel(reliability)}
                </span>
              </div>
            </div>
          </div>

          {/* Badge */}
          <div className="flex gap-2 flex-wrap">
            {legs.map(l => (
              <TableBadge key={l.trainNumber} tableType={l.tableType} />
            ))}
          </div>
        </div>

        {/* Avvertenze globali */}
        {warnings.filter(Boolean).length > 0 && (
          <div className="mt-3 space-y-1">
            {[...new Set(warnings.filter(Boolean))].map((w, i) => (
              <div key={i} className="text-xs text-yellow-400/90 bg-yellow-900/20 rounded-lg px-3 py-1.5 border border-yellow-600/20">
                ⚠️ {w}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tratte */}
      <div className="p-4 space-y-3">
        {legs.map((leg, i) => (
          <div key={i}>
            <LegRow leg={leg} />
            {i < legs.length - 1 && (
              <div className="mx-2 my-1 px-1">
                <div className="flex flex-col items-center">
                  <div className="w-px h-2 bg-orange-500/30" />
                  <div className="w-full bg-orange-950/60 border border-orange-600/40 text-orange-200 rounded-xl px-4 py-3">
                    <div className="flex items-center gap-2 font-bold text-sm text-orange-300 mb-1.5">
                      <span>🔄</span>
                      <span>Cambio a <strong className="text-white">{leg.alightAt}</strong></span>
                    </div>
                    <div className="text-xs text-orange-200/80 flex flex-wrap items-center gap-1">
                      <span>Prendere il treno</span>
                      <span className="font-black text-white text-sm">
                        {legs[i + 1].category
                          ? `${legs[i + 1].category} ${legs[i + 1].trainNumber}`
                          : legs[i + 1].trainNumber}
                      </span>
                      <span>→ dir.</span>
                      <span className="font-semibold text-white">
                        {/^\d{1,2}:\d{2}$/.test(legs[i + 1].destination)
                          ? legs[i + 1].alightAt
                          : legs[i + 1].destination}
                      </span>
                      <span className="text-orange-400">·</span>
                      <span>parte alle</span>
                      <span className="font-black text-white tabular-nums text-sm">{legs[i + 1].depTime}</span>
                    </div>
                  </div>
                  <div className="w-px h-2 bg-orange-500/30" />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
