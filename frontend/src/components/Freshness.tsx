import { useState, useRef, useEffect } from 'react'
import { agoSec } from '@/format'
import { cn } from '@/lib/utils'
import type { Freshness as FreshnessData } from '@/types'

const SRC_LABEL: Record<string, string> = { 'xt-xarid': 'xt-xarid', 'uzex': 'etender.uzex' }

const DOT: Record<string, string> = {
  ok: 'bg-ok',
  soon: 'bg-soon',
  urgent: 'bg-urgent',
}

// Ma'lumot yangiligi ko'rsatkichi. Yashil = yangi + xatosiz,
// sariq = eskirgan (>2 soat), qizil = biror manbada xato.
export default function Freshness({ data }: { data: FreshnessData | null }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  if (!data) return null
  const age = data.overall_age_sec
  const level = data.any_error ? 'urgent' : (age != null && age > 7200 ? 'soon' : 'ok')

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-3 text-[12.5px] transition-colors hover:bg-accent"
        title="Manba saytlardan (xt-xarid, etender.uzex) oxirgi marta ma'lumot yig'ilgan vaqt"
      >
        <span className={cn('size-2 rounded-full', DOT[level])} />
        <span className="text-muted-foreground">
          {data.any_error ? 'ETL xatosi' : `Manbadan: ${agoSec(age)}`}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] z-50 w-[300px] overflow-hidden rounded-lg border bg-popover p-1.5 shadow-lg">
          <div className="px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground">
            Manbalar holati
          </div>
          {data.platforms.map((p) => (
            <div className="flex items-center gap-2 px-2.5 py-1.5 text-[13px]" key={p.source_platform}>
              <span className={cn('size-2 rounded-full', p.status === 'error' ? DOT.urgent : DOT.ok)} />
              <span className="flex-1 truncate">
                {SRC_LABEL[p.source_platform] || p.source_platform}
              </span>
              <span className="text-[12px] text-muted-foreground">
                {p.status === 'error' ? 'xato' : agoSec(p.age_sec)}
                {p.new > 0 && (
                  <span className="ml-1.5 rounded bg-ok-soft px-1.5 py-px text-[11px] font-semibold text-ok">
                    +{p.new}
                  </span>
                )}
              </span>
            </div>
          ))}
          {!!data.detection?.sample && (
            <div
              className="mt-1 border-t px-2.5 pb-1 pt-2 text-[12px] text-muted-foreground"
              title="E'lon chiqishi bilan bizda paydo bo'lishi orasidagi vaqt"
            >
              Aniqlash kechikishi: <b className="text-foreground">{data.detection.median_hours} soat</b>
              {data.detection.within_1h_pct != null && <> · 1 soatda: {data.detection.within_1h_pct}%</>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
