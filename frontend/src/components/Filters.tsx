import { useEffect, useState } from 'react'
import Icon from './Icon'
import CategoryFilter from './CategoryFilter'
import ProductFilter from './ProductFilter'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import type { Category, Region, Status } from '@/types'

const SORT_OPTIONS = [
  { value: 'close_at', label: 'Deadline (yaqin)' },
  { value: '-totalcost', label: 'Summa (katta)' },
  { value: '-publicated_at', label: 'Yangi e’lon' },
]

// `Select` bo'sh qatorni qiymat sifatida qabul qilmaydi (Radix cheklovi:
// bo'sh satr "tanlanmagan" degani). Shuning uchun "hammasi" varianti maxsus
// belgi bilan yuritiladi va filtrga uzatilganда bo'sh qatorga aylanadi.
const ALL = '__all__'
const toFilter = (v: string) => (v === ALL ? '' : v)
const toSelect = (v: string) => (v === '' ? ALL : v)

export interface FiltersState {
  status: string
  region: string
  currency: string
  q: string
  category: string
  products: string[]
  services: string[]
  sort: string
}

interface FiltersProps {
  filters: FiltersState
  regions: Region[]
  statuses: Status[]
  categories: Category[]
  onChange: (patch: Partial<FiltersState>) => void
  onReset: () => void
  showSort?: boolean
}

// Gorizontal filtr paneli. Qidiruv debounce bilan.
export default function Filters({
  filters, regions, statuses, categories, onChange, onReset, showSort = true,
}: FiltersProps) {
  const [q, setQ] = useState(filters.q || '')
  useEffect(() => { setQ(filters.q || '') }, [filters.q])
  useEffect(() => {
    const id = setTimeout(() => { if (q !== (filters.q || '')) onChange({ q }) }, 400)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const trigger = 'h-9 w-auto min-w-[130px] bg-card text-[13px]'

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {/* Erkin qidiruv — tender nomi, buyurtmachi, tovar, AI kalit so'zlari.
          Mahsulot filtri ATAYIN alohida: u faqat tovar ro'yxatiga qaraydi. */}
      <div className="relative min-w-[240px] flex-1">
        <Icon name="search" size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          className="h-9 w-full rounded-md border border-input bg-card pl-9 pr-3 text-[13px] outline-none transition-colors focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring placeholder:text-muted-foreground"
          type="search"
          placeholder="Tender, buyurtmachi, tovar…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <ProductFilter
        value={filters.products} status={filters.status}
        kind="product" label0="Mahsulot" icon="box"
        placeholder="Mahsulot nomi — lotin yoki kirill"
        onChange={(products) => onChange({ products })} />
      <ProductFilter
        value={filters.services} status={filters.status}
        kind="service" label0="Xizmatlar" icon="wrench"
        placeholder="Xizmat nomi — lotin yoki kirill"
        onChange={(services) => onChange({ services })} />

      <CategoryFilter tree={categories} value={filters.category}
        onChange={(category) => onChange({ category })} />

      <Select value={toSelect(filters.status)}
        onValueChange={(v) => onChange({ status: toFilter(v) })}>
        <SelectTrigger className={trigger}><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Barcha statuslar</SelectItem>
          {statuses.map((s) => (
            <SelectItem key={s.status_code} value={s.status_code}>
              {s.name || s.status_code}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={toSelect(filters.region)}
        onValueChange={(v) => onChange({ region: toFilter(v) })}>
        <SelectTrigger className={trigger}><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Butun respublika</SelectItem>
          {regions.map((r) => (
            <SelectItem key={r.area_id} value={r.area_id}>{r.name || r.area_id}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={toSelect(filters.currency)}
        onValueChange={(v) => onChange({ currency: toFilter(v) })}>
        <SelectTrigger className="h-9 w-auto min-w-[110px] bg-card text-[13px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Valyuta</SelectItem>
          <SelectItem value="UZS">UZS</SelectItem>
          <SelectItem value="USD">USD</SelectItem>
        </SelectContent>
      </Select>

      {showSort && (
        <Select value={filters.sort} onValueChange={(sort) => onChange({ sort })}>
          <SelectTrigger className={trigger}><SelectValue /></SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <Button variant="ghost" size="sm" onClick={onReset}>Tozalash</Button>
    </div>
  )
}
