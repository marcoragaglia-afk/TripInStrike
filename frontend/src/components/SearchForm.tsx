'use client';

import { useState } from 'react';
import StationInput from './StationInput';
import type { SearchParams } from '@/lib/api';

interface Props {
  onSearch: (params: SearchParams) => void;
  loading: boolean;
}

export default function SearchForm({ onSearch, loading }: Props) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [depTime, setDepTime] = useState('');
  const [dayType, setDayType] = useState<'feriale' | 'festivo'>('feriale');
  const [tableType, setTableType] = useState<'tabella_a' | 'tabella_b'>('tabella_a');

  const swapStations = () => {
    const tmp = from;
    setFrom(to);
    setTo(tmp);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!from.trim() || !to.trim()) return;
    onSearch({
      from: from.trim(),
      to: to.trim(),
      depTime: depTime || undefined,
      dayType,
      tableType,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">

      {/* Tipo giornata */}
      <div>
        <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
          Tipo di Giornata
        </label>
        <div className="grid grid-cols-2 gap-2">
          {(['feriale', 'festivo'] as const).map(dt => (
            <button
              key={dt}
              type="button"
              onClick={() => setDayType(dt)}
              className={`
                py-3 rounded-xl font-semibold text-sm transition-all duration-200 border
                ${dayType === dt
                  ? 'bg-red-600 border-red-500 text-white shadow-lg shadow-red-900/40'
                  : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'}
              `}
            >
              {dt === 'feriale' ? '🗓 Giorno Feriale' : '🎉 Giorno Festivo'}
            </button>
          ))}
        </div>
      </div>

      {/* Tabella lunga percorrenza */}
      <div>
        <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
          Treni Lunga Percorrenza (AV / Intercity)
        </label>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setTableType('tabella_a')}
            className={`
              py-3 px-3 rounded-xl font-semibold text-sm transition-all duration-200 border text-left
              ${tableType === 'tabella_a'
                ? 'bg-blue-700 border-blue-500 text-white shadow-lg shadow-blue-900/40'
                : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'}
            `}
          >
            <span className="block font-bold">Tabella A</span>
            <span className="text-xs font-normal opacity-80">Feriali + Festivi</span>
          </button>
          <button
            type="button"
            onClick={() => setTableType('tabella_b')}
            className={`
              py-3 px-3 rounded-xl font-semibold text-sm transition-all duration-200 border text-left
              ${tableType === 'tabella_b'
                ? 'bg-purple-700 border-purple-500 text-white shadow-lg shadow-purple-900/40'
                : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'}
            `}
          >
            <span className="block font-bold">Tabella B</span>
            <span className="text-xs font-normal opacity-80">Sciopero gen. festivo</span>
          </button>
        </div>
        {tableType === 'tabella_b' && (
          <p className="mt-2 text-xs text-yellow-400/90 bg-yellow-900/20 rounded-lg px-3 py-2 border border-yellow-600/20">
            Tabella B si applica solo a: sciopero generale nazionale in giornata festiva (rinnovo CCNL), durata ≤ 24 ore, inizio ore 21:00 del giorno prefestivo.
          </p>
        )}
      </div>

      {/* Stazioni */}
      <div className="space-y-3">
        <div className="flex gap-3 items-end">
          <StationInput
            label="Partenza"
            value={from}
            onChange={setFrom}
            placeholder="Es: Roma Termini"
            icon="🚉"
          />
          <button
            type="button"
            onClick={swapStations}
            title="Inverti stazioni"
            className="
              mb-0.5 p-3 rounded-xl bg-white/5 border border-white/10
              text-slate-300 hover:bg-white/15 hover:text-white
              transition-all duration-200 flex-shrink-0
            "
          >
            ⇄
          </button>
          <StationInput
            label="Arrivo"
            value={to}
            onChange={setTo}
            placeholder="Es: Milano Centrale"
            icon="🏁"
          />
        </div>

        {/* Ora di partenza */}
        <div>
          <label className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">
            ⏰ Ora di Partenza (opzionale)
          </label>
          <input
            type="time"
            value={depTime}
            onChange={e => setDepTime(e.target.value)}
            className="
              w-full px-4 py-3 rounded-xl bg-white/10 border border-white/20
              text-white font-medium
              focus:outline-none focus:ring-2 focus:ring-red-500/60
              transition-all duration-200
              [color-scheme:dark]
            "
          />
        </div>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={loading || !from.trim() || !to.trim()}
        className="
          w-full py-4 rounded-xl font-bold text-lg
          bg-red-600 hover:bg-red-500 disabled:bg-slate-700 disabled:text-slate-500
          text-white transition-all duration-200
          shadow-lg shadow-red-900/40 hover:shadow-red-900/60
          disabled:shadow-none
          flex items-center justify-center gap-2
        "
      >
        {loading ? (
          <>
            <span className="animate-spin">⟳</span>
            <span>Ricerca in corso...</span>
          </>
        ) : (
          <>
            <span>🔍</span>
            <span>Cerca Itinerario Garantito</span>
          </>
        )}
      </button>
    </form>
  );
}
