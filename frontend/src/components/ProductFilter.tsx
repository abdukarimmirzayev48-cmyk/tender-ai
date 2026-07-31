import { useEffect, useRef, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { ProductSuggestion } from '@/types'

// MAHSULOT / XIZMAT FILTRI — erkin qidiruvdan (`q`) ATAYIN ALOHIDA.
//
// NEGA ALOHIDA: `q` tender nomi va BUYURTMACHI nomini ham qidiradi. Mahsulot
// uchun bu soxta natija beradi — "qurilish" so'rovi "Курилиш дирекцияси" MCHJ
// e'lon qilgan 39 ta tenderni tortadi, ularда qurilish tovari bo'lmasa ham.
// Bu filtr faqat tender TOVARLARI ro'yxatiga qaraydi.
//
// Bitta komponent ikkala tugma uchun: `kind` faqat TAKLIFLAR ro'yxatini
// ajratadi, filtrlash mantiqi bir xil. Tanlanganlar ORASIDA "yoki", boshqa
// filtrlar bilan esa "va".
interface ProductFilterProps {
  value?: string[]
  status: string
  kind?: 'product' | 'service'
  label0: string
  icon: string
  placeholder: string
  onChange: (value: string[]) => void
}

export default function ProductFilter({
  value = [], status, kind = 'product', label0, icon, placeholder, onChange,
}: ProductFilterProps) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [items, setItems] = useState<ProductSuggestion[]>([])
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  useEffect(() => {
    if (!open) return
    let alive = true
    const id = setTimeout(() => {
      api.products({ q: text || undefined, kind, status: status || '', limit: 12 })
        .then((rs) => { if (alive) setItems(rs) })
        .catch(() => { if (alive) setItems([]) })
    }, 250)
    return () => { alive = false; clearTimeout(id) }
  }, [text, status, kind, open])

  const toggle = (name: string) => {
    onChange(value.includes(name) ? value.filter((v) => v !== name) : [...value, name])
  }

  const label = value.length === 0 ? label0
    : value.length === 1 ? value[0]
      : `${value.length} ta`

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex h-9 max-w-[220px] items-center gap-2 rounded-md border bg-card px-3',
          'text-[13px] transition-colors hover:bg-accent focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none',
          value.length ? 'border-primary text-primary' : 'border-input text-foreground',
        )}
      >
        <Icon name={icon} size={14} />
        <span className="truncate">{label}</span>
        {value.length > 0 && (
          <span
            role="button"
            tabIndex={0}
            title="Tozalash"
            className="-mr-1 ml-0.5 rounded px-1 text-base leading-none hover:bg-secondary"
            onClick={(e) => { e.stopPropagation(); onChange([]) }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onChange([]) } }}
          >×</span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-[calc(100%+4px)] z-50 w-[300px] overflow-hidden rounded-lg border bg-popover shadow-lg">
          <input
            className="w-full border-b bg-transparent px-3 py-2 text-[13px] outline-none placeholder:text-muted-foreground"
            type="text"
            autoFocus
            placeholder={placeholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <ul className="max-h-[300px] overflow-y-auto p-1.5">
            {items.length === 0 && (
              <li className="px-3 py-4 text-center text-[13px] text-muted-foreground">Topilmadi</li>
            )}
            {items.map((p) => (
              <li key={p.name}>
                <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] hover:bg-accent">
                  <Checkbox
                    checked={value.includes(p.name)}
                    onCheckedChange={() => toggle(p.name)}
                  />
                  <span className="flex-1 truncate">{p.name}</span>
                  <span className="tabular text-[11px] text-muted-foreground">{p.tender_count}</span>
                </label>
              </li>
            ))}
          </ul>
          {value.length > 0 && (
            <div className="flex items-center justify-between border-t px-3 py-2 text-[12px] text-muted-foreground">
              <span>{value.length} ta tanlandi</span>
              <Button variant="ghost" size="sm" onClick={() => onChange([])}>Tozalash</Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
