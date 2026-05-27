'use client';

import { useState } from 'react';
import SearchForm from '@/components/SearchForm';
import ItineraryCard from '@/components/ItineraryCard';
import { searchJourney, type JourneyResponse, type SearchParams } from '@/lib/api';

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: JourneyResponse }
  | { status: 'error'; message: string };

export default function Home() {
  const [state, setState] = useState<State>({ status: 'idle' });

  const handleSearch = async (params: SearchParams) => {
    setState({ status: 'loading' });
    try {
      const data = await searchJourney(params);
      setState({ status: 'success', data });
    } catch (e) {
      setState({ status: 'error', message: e instanceof Error ? e.message : 'Errore sconosciuto' });
    }
  };

  return (
    <main className="min-h-screen p-4 md:p-8">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <header className="text-center pt-4 pb-2">
          <div className="inline-flex items-center gap-2 bg-red-900/30 border border-red-500/30 rounded-full px-4 py-1.5 text-sm text-red-300 mb-4">
            <span>🚨</span>
            <span>Modalità Sciopero Ferroviario</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-black text-white tracking-tight">
            TripInStrike
          </h1>
          <p className="text-slate-400 mt-2 text-base">
            Itinerari garantiti in caso di sciopero – Dati ufficiali Trenitalia
          </p>
        </header>

        {/* Scheda info */}
        <InfoBanner />

        {/* Form di ricerca */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-5 md:p-6 shadow-2xl">
          <SearchForm
            onSearch={handleSearch}
            loading={state.status === 'loading'}
          />
        </div>

        {/* Risultati */}
        {state.status === 'loading' && (
          <div className="text-center py-16">
            <div className="text-5xl animate-spin inline-block mb-4">🚆</div>
            <p className="text-slate-400">Calcolo itinerari garantiti...</p>
          </div>
        )}

        {state.status === 'error' && (
          <div className="rounded-2xl border border-red-500/30 bg-red-900/20 p-5 text-red-300">
            <p className="font-bold">Errore nella ricerca</p>
            <p className="text-sm mt-1 text-red-400">{state.message}</p>
            <p className="text-xs mt-3 text-red-500/70">
              Verifica che i nomi delle stazioni siano scritti correttamente. Se il problema persiste prova a ricaricare la pagina.
            </p>
          </div>
        )}

        {state.status === 'success' && (
          <ResultsSection data={state.data} />
        )}

        {/* Footer */}
        <footer className="text-center text-xs text-slate-600 pb-8 space-y-1">
          <p>Dati: Trenitalia – Orario dicembre 2025 / giugno 2026</p>
          <p>App non ufficiale – Verificare sempre con trenitalia.com in caso di sciopero</p>
        </footer>
      </div>
    </main>
  );
}

function InfoBanner() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-blue-500/20 bg-blue-900/10 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex items-center justify-between text-sm text-blue-300 hover:bg-blue-900/20 transition-colors"
      >
        <span className="flex items-center gap-2">
          <span>ℹ️</span>
          <span className="font-semibold">Come funziona? Tabella A vs Tabella B</span>
        </span>
        <span>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-slate-300 space-y-3 border-t border-blue-500/10">
          <div className="mt-3 space-y-2">
            <p><strong className="text-blue-300">Tabella A:</strong> Treni lunga percorrenza (AV, Intercity, EuroCity) garantiti in OGNI giornata di sciopero, sia feriale che festiva.</p>
            <p><strong className="text-purple-300">Tabella B:</strong> Treni aggiuntivi garantiti solo in caso di sciopero generale nazionale effettuato in giornata festiva per rinnovo CCNL, di durata non superiore alle 24 ore e con inizio alle ore 21:00 del giorno prefestivo.</p>
            <p><strong className="text-green-300">Treni regionali:</strong> Servizi minimi garantiti per ogni regione, diversi tra giornata feriale e festiva.</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3 space-y-1 text-xs text-slate-400">
            <p>⚠️ Gli orari indicati come "potrebbero essere posticipati" potrebbero subire variazioni di max 60 minuti.</p>
            <p>⚠️ I dati fanno riferimento all&apos;orario Trenitalia 14/12/2025 – 13/06/2026.</p>
          </div>
        </div>
      )}
    </div>
  );
}

function ResultsSection({ data }: { data: JourneyResponse }) {
  const { query, count, itineraries, meta } = data;

  return (
    <div className="space-y-4">
      {/* Header risultati */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-bold text-white">
            {count === 0 ? 'Nessun itinerario' : `${count} itinerar${count === 1 ? 'io' : 'i'} garantit${count === 1 ? 'o' : 'i'}`}
          </h2>
          <p className="text-sm text-slate-400">
            {query.from} → {query.to}
            {' · '}
            {query.day_type === 'feriale' ? 'Giornata feriale' : 'Giornata festiva'}
            {query.table_type && ` · ${query.table_type === 'tabella_a' ? 'Tabella A' : 'Tabella B'}`}
          </p>
        </div>
        <div className="text-xs text-slate-500">
          {meta.trains_available} treni nel database
        </div>
      </div>

      {/* Nessun risultato */}
      {count === 0 && (
        <div className="rounded-2xl border border-yellow-500/20 bg-yellow-900/10 p-6 text-center">
          <div className="text-4xl mb-3">😔</div>
          <p className="text-yellow-300 font-semibold">Nessun itinerario garantito trovato</p>
          <p className="text-yellow-500/80 text-sm mt-2">
            {meta.note || 'Prova a verificare i nomi delle stazioni o cerca percorsi alternativi.'}
          </p>
          <div className="mt-4 text-xs text-slate-500 space-y-1">
            <p>Suggerimenti:</p>
            <p>• Scrivi il nome completo della stazione (es. &quot;Roma Termini&quot; non &quot;Roma&quot;)</p>
            <p>• In giornata di sciopero potrebbero non esserci treni garantiti sulla tua tratta</p>
            <p>• Considera stazioni di testa/cambio principali</p>
          </div>
        </div>
      )}

      {/* Itinerari */}
      <div className="space-y-4">
        {itineraries.map((it, i) => (
          <ItineraryCard key={i} itinerary={it} index={i} />
        ))}
      </div>
    </div>
  );
}
