'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { searchStations, type Station } from '@/lib/api';

interface Props {
  label: string;
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  icon?: string;
}

export default function StationInput({ label, value, onChange, placeholder, icon }: Props) {
  const [query, setQuery] = useState(value);
  const [suggestions, setSuggestions] = useState<Station[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync external value
  useEffect(() => { setQuery(value); }, [value]);

  const search = useCallback(async (q: string) => {
    if (q.trim().length < 2) { setSuggestions([]); return; }
    setLoading(true);
    const res = await searchStations(q);
    setSuggestions(res);
    setOpen(res.length > 0);
    setLoading(false);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setQuery(v);
    onChange(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(v), 280);
  };

  const handleSelect = (s: Station) => {
    setQuery(s.name);
    onChange(s.name);
    setSuggestions([]);
    setOpen(false);
  };

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!inputRef.current?.parentElement?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="relative flex-1">
      <label className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">
        {icon && <span className="mr-1">{icon}</span>}{label}
      </label>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleChange}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder={placeholder || 'Inserisci stazione...'}
          autoComplete="off"
          className="
            w-full px-4 py-3 rounded-xl bg-white/10 border border-white/20
            text-white placeholder-slate-500 font-medium
            focus:outline-none focus:ring-2 focus:ring-red-500/60 focus:border-transparent
            transition-all duration-200
          "
        />
        {loading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 animate-spin">⟳</span>
        )}
      </div>

      {open && suggestions.length > 0 && (
        <ul
          ref={listRef}
          className="
            absolute z-50 top-full left-0 right-0 mt-1
            bg-slate-800 border border-white/10 rounded-xl
            shadow-2xl overflow-hidden max-h-60 overflow-y-auto
          "
        >
          {suggestions.map(s => (
            <li
              key={s.id}
              onMouseDown={() => handleSelect(s)}
              className="
                px-4 py-3 cursor-pointer hover:bg-white/10
                border-b border-white/5 last:border-0
                flex items-center justify-between
                text-sm
              "
            >
              <span className="text-white font-medium">{s.name}</span>
              {s.region && (
                <span className="text-slate-400 text-xs ml-2 flex-shrink-0">{s.region}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
