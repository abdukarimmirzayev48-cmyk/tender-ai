import { useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AnimatedScore } from '@/components/ui/animated-number'
import { cn } from '@/lib/utils'
import type { AiMatchResult } from '@/types'

// DIQQAT — bu yerda `GlowBorderCard` ISHLATILMAYDI. U qat'iy o'lchamli
// (`width: 320px` + `aspect-ratio: 1`) dekorativ karta: xulosa matni uzun
// bo'lsa kesilib qolardi. Hukm rangi oddiy `Card` ning chap chekkasi orqali
// beriladi — balandlik matnga moslashadi.

// AI MOSLIK TAHLILI — "bu tender menga mos keladimi?"
//
// TALAB BO'YICHA ishlaydi (avtomatik emas): har tahlil Claude chaqiruvi, ya'ni
// pul. Foydalanuvchi o'zi bosadi. Natija backendda keshlanadi, shuning uchun
// bir tenderni qayta ochsa yangi so'rov ketmaydi.
const VERDICT: Record<string, { label: string; edge: string; text: string }> = {
  mos: { label: 'Mos keladi', edge: 'border-l-ok', text: 'text-ok' },
  qisman: { label: 'Qisman mos', edge: 'border-l-soon', text: 'text-soon' },
  mos_emas: { label: 'Mos emas', edge: 'border-l-urgent', text: 'text-urgent' },
}

export default function AiMatch({ tenderId }: { tenderId: number }) {
  const [data, setData] = useState<AiMatchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function run(refresh = false) {
    setLoading(true); setError(null)
    api.aiMatch(tenderId, refresh ? { refresh: true } : undefined)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  if (!data && !loading && !error) {
    return (
      <Button variant="outline" className="mb-4 w-full justify-start" onClick={() => run(false)}
        title="Katalogingizga nisbatan AI hukmi: mos / qisman / mos emas">
        <Icon name="sparkle" size={14} />
        AI tahlil — mos keladimi?
      </Button>
    )
  }

  if (loading) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg border bg-card px-4 py-3 text-[13px] text-muted-foreground">
        <Icon name="sparkle" size={14} className="animate-pulse" />
        AI tahlil qilmoqda…
      </div>
    )
  }

  if (error) {
    return (
      <div className="mb-4 space-y-2 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
        <div>{error}</div>
        <Button variant="outline" size="sm" onClick={() => run(false)}>Qayta urinish</Button>
      </div>
    )
  }

  const v = VERDICT[data!.verdict] || { label: data!.verdict, edge: 'border-l-primary', text: 'text-primary' }
  return (
    <Card className={cn('mb-4 border-l-4', v.edge)}>
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <Icon name="sparkle" size={13} className={v.text} />
          <span className={cn('text-[15px] font-bold', v.text)}>{v.label}</span>
          <span className="tabular ml-auto text-[15px] font-bold">
            <AnimatedScore value={data!.score} />
            <span className="text-[12px] font-normal text-muted-foreground">/100</span>
          </span>
          <button
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="Qayta tahlil qilish" onClick={() => run(true)}
          >
            <Icon name="refresh" size={12} />
          </button>
        </div>

        <p className="text-[13px] leading-relaxed">{data!.reason_uz}</p>

        {!!data!.matched_items?.length && (
          <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
            <b>Katalogingizdan:</b>
            {data!.matched_items!.map((m) => (
              <span key={m} className="rounded bg-secondary px-1.5 py-px text-primary">{m}</span>
            ))}
          </div>
        )}

        {!!data!.requirements?.length && (
          <Block label="Talablar" items={data!.requirements!} />
        )}
        {!!data!.risks?.length && (
          <Block label="E’tibor bering" items={data!.risks!} tone="warn" />
        )}

        <div className="text-[11px] text-muted-foreground">
          {data!.cached ? 'keshdan' : 'yangi tahlil'}{data!.model ? ` · ${data!.model}` : ''}
        </div>
      </div>
    </Card>
  )
}

function Block({ label, items, tone }: { label: string; items: string[]; tone?: 'warn' }) {
  return (
    <div className={cn(
      'rounded-lg border px-3 py-2',
      tone === 'warn' ? 'border-soon/40 bg-soon-soft' : 'bg-muted',
    )}>
      <div className="mb-1 text-[11px] font-bold text-muted-foreground">
        {label}
      </div>
      <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
        {items.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  )
}
