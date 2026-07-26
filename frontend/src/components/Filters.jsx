import { useEffect, useState } from 'react'
import Icon from './Icon.jsx'
import CategoryFilter from './CategoryFilter.jsx'

const SORT_OPTIONS = [
  { value: 'close_at', label: 'Deadline (yaqin)' },
  { value: '-totalcost', label: 'Summa (katta)' },
  { value: '-publicated_at', label: 'Yangi e’lon' },
]

// Gorizontal filtr paneli (numeo.ai uslubi). Qidiruv debounce bilan.
export default function Filters({ filters, regions, statuses, categories, onChange, onReset, showSort = true }) {
  const [q, setQ] = useState(filters.q || '')
  useEffect(() => { setQ(filters.q || '') }, [filters.q])
  useEffect(() => {
    const id = setTimeout(() => { if (q !== (filters.q || '')) onChange({ q }) }, 400)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  return (
    <div className="filters">
      <div className="searchbox">
        <Icon name="search" size={15} className="searchbox__icon" />
        <input
          className="filters__search"
          type="search"
          placeholder="Tender, buyurtmachi yoki tovar nomi…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <CategoryFilter tree={categories} value={filters.category}
        onChange={(code) => onChange({ category: code })} />
      <select className="filters__select" value={filters.status}
        onChange={(e) => onChange({ status: e.target.value })}>
        <option value="">Barcha statuslar</option>
        {statuses.map((s) => <option key={s.status_code} value={s.status_code}>{s.name || s.status_code}</option>)}
      </select>
      <select className="filters__select" value={filters.region}
        onChange={(e) => onChange({ region: e.target.value })}>
        <option value="">Butun respublika</option>
        {regions.map((r) => <option key={r.area_id} value={r.area_id}>{r.name || r.area_id}</option>)}
      </select>
      <select className="filters__select" value={filters.currency}
        onChange={(e) => onChange({ currency: e.target.value })}>
        <option value="">Valyuta</option>
        <option value="UZS">UZS</option>
        <option value="USD">USD</option>
      </select>
      {showSort && (
        <select className="filters__select" value={filters.sort}
          onChange={(e) => onChange({ sort: e.target.value })}>
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
      <button className="btn btn--ghost" onClick={onReset}>Tozalash</button>
    </div>
  )
}
