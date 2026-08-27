import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
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
  const t = useT()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [items, setItems] = useState<ProductSuggestion[]>([])

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
      : t('common.pcs', { n: value.length })

  return (
    // TOZALASH TUGMASI PANEL TASHQARISIDA. Avval u ochish tugmasi ICHIDA,
    // `role="button"` bilan yozilgan `<span>` edi — tugma ichida tugma
    // HTML'da haqiqiy emas, va bosilganda `stopPropagation` bo'lmasa panel
    // ham ochilib ketardi. Endi ikkalasi yonma-yon, ikkalasi ham `<button>`.
    <div className={cn(
      'inline-flex h-9 items-center rounded-md border bg-card transition-colors',
      value.length ? 'border-primary text-primary' : 'border-input text-foreground',
    )}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              'inline-flex h-full max-w-[200px] items-center gap-2 rounded-md px-3 text-body',
              'transition-colors hover:bg-accent',
            )}
          >
            <Icon name={icon} size={14} />
            <span className="truncate">{label}</span>
          </button>
        </PopoverTrigger>

        <PopoverContent className="w-[19rem] max-w-[calc(100vw-2rem)]">
          <input
            className="w-full border-b bg-transparent px-3 py-2 text-base md:text-body outline-none placeholder:text-muted-foreground"
            type="text"
            autoFocus
            aria-label={placeholder}
            placeholder={placeholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <ul className="max-h-[18rem] overflow-y-auto p-1.5">
            {items.length === 0 && (
              <li className="px-3 py-4 text-center text-body text-muted-foreground">{t('common.notFound')}</li>
            )}
            {items.map((p) => (
              <li key={p.name}>
                <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-body hover:bg-accent">
                  <Checkbox
                    checked={value.includes(p.name)}
                    onCheckedChange={() => toggle(p.name)}
                  />
                  <span className="flex-1 truncate" title={p.name}>{p.name}</span>
                  <span className="tabular text-micro text-muted-foreground">{p.tender_count}</span>
                </label>
              </li>
            ))}
          </ul>
          {value.length > 0 && (
            <div className="flex items-center justify-between gap-2 border-t px-3 py-2 text-caption text-muted-foreground">
              <span>{t('common.selectedN', { n: value.length })}</span>
              <Button variant="ghost" size="sm" onClick={() => onChange([])}>{t('common.clear')}</Button>
            </div>
          )}
        </PopoverContent>
      </Popover>

      {value.length > 0 && (
        <button
          type="button"
          aria-label={t('filters.clearOne', { name: label0 })}
          title={t('common.clear')}
          className="mr-1 flex size-6 shrink-0 items-center justify-center rounded transition-colors hover:bg-secondary"
          onClick={() => onChange([])}
        >
          <Icon name="close" size={12} />
        </button>
      )}
    </div>
  )
}
