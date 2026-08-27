import { useState, useMemo } from 'react'
import Icon from './Icon'
import { useT } from '@/i18n'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { Category } from '@/types'

interface CategoryFilterProps {
  tree: Category[]
  value: string
  onChange: (code: string) => void
}

// Ikki darajali kategoriya filtri (qidiruv + tender soni bilan).
export default function CategoryFilter({ tree, value, onChange }: CategoryFilterProps) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')

  // Tanlangan kategoriya nomi (tugma yorlig'i uchun)
  const label = useMemo(() => {
    if (!value) return t('filters.allCategories')
    for (const p of tree) {
      if (p.code === value) return p.name
      for (const c of p.children) if (c.code === value) return c.name
    }
    return value
  }, [value, tree, t])

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

  const row = 'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-body transition-colors hover:bg-accent'
  const sel = 'bg-secondary font-semibold text-primary'

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ('') }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex h-9 max-w-[15rem] items-center gap-2 rounded-md border bg-card px-3',
            'text-body transition-colors hover:bg-accent',
            value ? 'border-primary text-primary' : 'border-input text-foreground',
          )}
        >
          <Icon name="grid" size={14} />
          <span className="truncate">{label}</span>
          <Icon name="chevron" size={14} className={cn('transition-transform', open && 'rotate-180')} />
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-[20rem] max-w-[calc(100vw-2rem)]">
        <div className="flex items-center gap-2 border-b px-3 py-2">
          <Icon name="search" size={14} className="text-muted-foreground" />
          <input
            autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={t('filters.categorySearch')}
            aria-label={t('filters.categorySearch')}
            className="w-full bg-transparent text-base md:text-body outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-[20rem] overflow-y-auto p-1.5">
          <button className={cn(row, !value && sel)} onClick={() => pick('')}>
            {t('filters.allCategories')}
          </button>
          {filtered.map((p) => (
            <div key={p.code}>
              <button className={cn(row, 'font-medium', value === p.code && sel)}
                onClick={() => pick(p.code)}>
                <span className="flex-1 truncate" title={p.name}>{p.name}</span>
                {!!p.count && (
                  <span className="tabular text-micro text-muted-foreground">{p.count}</span>
                )}
              </button>
              {p.children.filter((c) => (c.count ?? 0) > 0 || value === c.code).map((c) => (
                <button key={c.code} className={cn(row, 'pl-6', value === c.code && sel)}
                  onClick={() => pick(c.code)}>
                  <span className="flex-1 truncate" title={c.name}>{c.name}</span>
                  {!!c.count && (
                    <span className="tabular text-micro text-muted-foreground">{c.count}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="px-3 py-4 text-center text-body text-muted-foreground">
              {t('common.notFound')}
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
