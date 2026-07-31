import { useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { GoNoGoResult } from '@/types'

// GO / NO-GO TAVSIYASI — "bu tenderda qatnashaymi?"
//
// AiMatch dan farqi: u faqat "mahsulotim mos keladimi" deydi. Bu esa
// qatnashish qarorini butun kesimda ko'radi — muddat, byudjet, sertifikat,
// tajriba, resurs. 11 mezon alohida ko'rsatiladi.
//
// MVP CHEKLOVI OCHIQ KO'RSATILADI: profil to'ldirilmagan bo'lsa, tegishli
// mezon "ma'lumot yo'q" bo'lib chiqadi va qaror Review ga tushadi.
const DECISION: Record<string, { label: string; edge: string; text: string }> = {
  go: { label: 'Go — qatnashing', edge: 'border-l-ok', text: 'text-ok' },
  review: { label: 'Review — tekshirish kerak', edge: 'border-l-soon', text: 'text-soon' },
  no_go: { label: 'No-Go — qatnashmang', edge: 'border-l-urgent', text: 'text-urgent' },
}

const STATUS: Record<string, { cls: string; text: string }> = {
  ok: { cls: 'bg-ok', text: 'Bajariladi' },
  risk: { cls: 'bg-soon', text: 'Xavf bor' },
  fail: { cls: 'bg-urgent', text: 'Bajarilmaydi' },
  malumot_yoq: { cls: 'bg-border ring-1 ring-inset ring-muted-foreground/40', text: 'Ma’lumot yo‘q' },
}

export default function GoNoGo({ tenderId }: { tenderId: number }) {
  const [data, setData] = useState<GoNoGoResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function run(refresh = false) {
    setLoading(true); setError(null)
    api.aiGoNogo(tenderId, refresh ? { refresh: true } : undefined)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  if (!data && !loading && !error) {
    return (
      <Button variant="outline" className="mb-4 w-full justify-start" onClick={() => run(false)}
        title="Muddat, byudjet, sertifikat, tajriba va resurs bo‘yicha AI qarori">
        <Icon name="check" size={14} />
        Go / No-Go — qatnashaymi?
      </Button>
    )
  }
  if (loading) {
    return (
      <div className="mb-4 rounded-lg border bg-card px-4 py-3 text-[13px] text-muted-foreground">
        AI qaror chiqarmoqda…
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

  const d = DECISION[data!.decision] || { label: data!.decision, edge: 'border-l-border', text: '' }
  const labels = new Map((data!.criteria_labels || []).map((c) => [c.key, c.label]))

  return (
    <Card className={cn('mb-4 border-l-4', d.edge)}>
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-3">
          <span className={cn('text-[15px] font-bold', d.text)}>{d.label}</span>
          <div className="ml-auto flex items-center gap-2" title="Qarorga ishonch">
            <Progress value={data!.confidence} className="h-1.5 w-16" />
            <span className="tabular text-[13px] font-semibold">{data!.confidence}%</span>
          </div>
          <button
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="Qayta baholash" onClick={() => run(true)}
          >
            <Icon name="refresh" size={12} />
          </button>
        </div>

        <p className="text-[13px] leading-relaxed">{data!.summary_uz}</p>

        {!!data!.blockers?.length && (
          <div className="rounded-lg border border-urgent/40 bg-urgent-soft px-3 py-2">
            <div className="mb-1 text-[11px] font-bold text-urgent">
              To‘siqlar
            </div>
            <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
              {data!.blockers!.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          </div>
        )}

        <table className="w-full text-[13px]">
          <tbody>
            {(data!.criteria || []).map((c) => {
              const s = STATUS[c.status] || STATUS.malumot_yoq
              return (
                <tr key={c.key} className="border-b border-border-soft last:border-0">
                  <td className="w-4 py-1.5 align-top">
                    <span className={cn('mt-1.5 block size-2 rounded-full', s.cls)} title={s.text} />
                  </td>
                  <td className="w-[38%] py-1.5 pr-3 align-top font-medium">
                    {labels.get(c.key) || c.key}
                  </td>
                  <td className="py-1.5 align-top text-muted-foreground">{c.note_uz}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {!!data!.next_steps?.length && (
          <div className="rounded-lg bg-muted px-3 py-2">
            <div className="mb-1 text-[11px] font-bold text-muted-foreground">
              Keyingi qadamlar
            </div>
            <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
              {data!.next_steps!.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}

        {!!data!.missing_data?.length && (
          <div className="rounded-lg border border-soon/40 bg-soon-soft px-3 py-2">
            <div className="mb-1 text-[11px] font-bold text-soon">
              Profilga qo‘shing — qaror aniqroq bo‘ladi
            </div>
            <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
              {data!.missing_data!.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}

        <div className="text-[11px] text-muted-foreground">
          {data!.cached ? 'keshdan' : 'yangi tahlil'}{data!.model ? ` · ${data!.model}` : ''} · qaror sizniki
        </div>
      </div>
    </Card>
  )
}
