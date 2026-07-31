import { useState, useEffect, useRef, useMemo } from 'react'
import Icon from './Icon'
import { cn } from '@/lib/utils'
import type { Category } from '@/types'

interface CategoryFilterProps {
  tree: Category[]
  value: string
  onChange: (code: string) => void
}

// Ikki darajali kategoriya filtri (qidiruv + tender soni bilan).
export default function CategoryFilter({ tree, value, onChange }: CategoryFilterProps) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  // Tashqariga bosilsa yopiladi
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // Tanlangan kategoriya nomi (tugma yorlig'i uchun)
  const label = useMemo(() => {
    if (!value) return 'Barcha kategoriyalar'
    for (const p of tree) {
      if (p.code === value) return p.name
      for (const c of p.children) if (c.code === value) return c.name
    }
    return value
  }, [value, tree])

  // Qidiruv bo'yicha filtrlash (nom ichidan)
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return tree
    return tree
      .map((p) => {
        const kids = p.children.filter((c) => c.name.toLowerCase().includes(needle))
        if (p.name.toLowerCase().includes(needle)) return p          // parent mos — hammasi
        if (kids.length) return { ...p, children: kids }             // faqat mos ichkilar
        return null
      })
      .filter((x): x is Category => x !== null)
  }, [q, tree])

  function pick(code: string) { onChange(code); setOpen(false); setQ('') }

  const row = 'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors hover:bg-accent'
  const sel = 'bg-secondary font-semibold text-primary'

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex h-9 max-w-[240px] items-center gap-2 rounded-md border bg-card px-3',
          'text-[13px] transition-colors hover:bg-accent focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none',
          value ? 'border-primary text-primary' : 'border-input text-foreground',
        )}
      >
        <Icon name="grid" size={14} />
        <span className="truncate">{label}</span>
        <Icon name="chevron" size={14} className={cn('transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute left-0 top-[calc(100%+4px)] z-50 w-[320px] overflow-hidden rounded-lg border bg-popover shadow-lg">
          <div className="flex items-center gap-2 border-b px-3 py-2">
            <Icon name="search" size={14} className="text-muted-foreground" />
            <input
              autoFocus value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Kategoriya qidirish…"
              className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="max-h-[320px] overflow-y-auto p-1.5">
            <button className={cn(row, !value && sel)} onClick={() => pick('')}>
              Barcha kategoriyalar
            </button>
            {filtered.map((p) => (
              <div key={p.code}>
                <button className={cn(row, 'font-medium', value === p.code && sel)}
                  onClick={() => pick(p.code)}>
                  <span className="flex-1 truncate">{p.name}</span>
                  {!!p.count && (
                    <span className="tabular text-[11px] text-muted-foreground">{p.count}</span>
                  )}
                </button>
                {p.children.filter((c) => (c.count ?? 0) > 0 || value === c.code).map((c) => (
                  <button key={c.code} className={cn(row, 'pl-6', value === c.code && sel)}
                    onClick={() => pick(c.code)}>
                    <span className="flex-1 truncate">{c.name}</span>
                    {!!c.count && (
                      <span className="tabular text-[11px] text-muted-foreground">{c.count}</span>
                    )}
                  </button>
                ))}
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-center text-[13px] text-muted-foreground">
                Topilmadi
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
