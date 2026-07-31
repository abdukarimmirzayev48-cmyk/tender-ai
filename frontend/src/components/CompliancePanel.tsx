import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ComplianceItem, ComplianceResult } from '@/types'

// HUJJATLAR TO'LIQLIGI CHEKLISTI (P0-8) — tender panelidagi blok.
//
// Savol: "shu tenderga ariza berish uchun qaysi hujjatlar kerak va ular
// bizda bormi?" Har band uchun: nomi, BOR/YO'Q belgisi, amal qilish muddati
// va "nima uchun talab qilinadi" degan DALIL (tender matnining bo'lagi).
//
// MVP CHEKLOVI OCHIQ AYTILADI: bu STATIK cheklist — hujjat borligini va
// muddatini tekshiradi, mazmunining huquqiy to'g'riligini EMAS. AI ishlamaydi.
const STATUS: Record<ComplianceItem['status'], { mark: string; text: string; cls: string }> = {
  ok: { mark: '✓', text: 'Bazada bor', cls: 'bg-ok-soft text-ok' },
  expiring_soon: { mark: '!', text: 'Muddati tugayapti', cls: 'bg-soon-soft text-soon' },
  expired: { mark: '×', text: 'Muddati tugagan', cls: 'bg-urgent-soft text-urgent' },
  missing: { mark: '×', text: 'Bazada yo‘q', cls: 'bg-urgent-soft text-urgent' },
}

const dateFmt = (iso?: string | null) => (iso ? iso.split('-').reverse().join('.') : null)

interface CompliancePanelProps {
  tenderId: number
  onOpenDocuments?: (docType: string) => void
}

export default function CompliancePanel({ tenderId, onOpenDocuments }: CompliancePanelProps) {
  const [data, setData] = useState<ComplianceResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Hujjat boshqa oynada qo'shilgan bo'lishi mumkin — qayta yuklash kaliti
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let alive = true
    setData(null); setError(null)
    api.compliance(tenderId)
      .then((d) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [tenderId, reloadKey])

  if (error) {
    return (
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
        Cheklist yuklanmadi: {error}
      </div>
    )
  }
  if (!data) return <Skeleton className="mb-4 h-32 w-full rounded-lg" />

  const s = data.summary

  return (
    <Card className="mb-4 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <Icon name="check" size={14} className="text-primary" />
        <span className="text-[13px] font-semibold">Hujjatlar to‘liqligi</span>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone="ok">Tayyor {s.ready}</Pill>
          {s.expiring_soon > 0 && <Pill tone="soon">Tugayapti {s.expiring_soon}</Pill>}
          {s.expired > 0 && <Pill tone="bad" title="Muddati tugagan">Tugagan {s.expired}</Pill>}
          {s.missing > 0 && <Pill tone="bad">Yo‘q {s.missing}</Pill>}
          {s.blocking === 0 && <Pill tone="ok">To‘plam to‘liq</Pill>}
        </div>
        <button
          className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Cheklistni yangilash" onClick={() => setReloadKey((k) => k + 1)}
        >
          <Icon name="refresh" size={12} />
        </button>
      </div>

      {/* HALOL HOLAT: tender matnidan hech narsa topilmasa — jim turmaymiz. */}
      <div className="border-b bg-muted px-3 py-2 text-[12px] text-muted-foreground">{s.note}</div>

      <ul className="divide-y divide-border-soft">
        {data.items.map((it) => {
          const st = STATUS[it.status] || STATUS.missing
          const d = it.document
          return (
            <li className="px-3 py-2.5" key={it.doc_type}>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full text-[12px] font-bold',
                    st.cls,
                  )}
                  aria-hidden="true"
                >{st.mark}</span>

                <span className="text-[13px] font-medium">{it.label}</span>
                <span className={cn(
'rounded px-1.5 py-px text-[10px] font-semibold',
                  it.required_by === 'tender'
                    ? 'bg-secondary text-primary'
                    : 'bg-muted text-muted-foreground',
                )}>
                  {it.required_by === 'tender' ? 'tenderda talab' : 'bazaviy'}
                </span>

                <span className={cn('ml-auto rounded px-2 py-0.5 text-[12px] font-semibold', st.cls)}>
                  {st.text}
                </span>
              </div>

              {d && (
                <div className="mt-1 pl-7 text-[12px] text-muted-foreground">
                  {d.name}
                  {d.number ? ` · № ${d.number}` : ''}
                  {d.valid_until ? ` · amal qiladi: ${dateFmt(d.valid_until)}` : ' · muddatsiz'}
                  {it.days_left != null && it.status === 'expiring_soon'
                    ? ` (${it.days_left} kun qoldi)` : ''}
                  {it.days_left != null && it.status === 'expired'
                    ? ` (${Math.abs(it.days_left)} kun oldin tugagan)` : ''}
                </div>
              )}

              {/* Muammoli band — nima qilish kerakligi darhol aytiladi */}
              {(it.status === 'missing' || it.status === 'expired') && onOpenDocuments && (
                <div className="mt-1 pl-7">
                  <button
                    className="text-[12px] font-semibold text-primary underline-offset-2 hover:underline"
                    onClick={() => onOpenDocuments(it.doc_type)}
                  >
                    {it.status === 'missing' ? 'Hujjat qo‘shish →' : 'Yangilash →'}
                  </button>
                </div>
              )}

              {/* DALIL — shaffoflik: talab qayerdan kelib chiqdi */}
              <details className="mt-1 pl-7 text-[12px]">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  Nega kerak?
                </summary>
                <div className="mt-1 rounded-md bg-muted p-2 leading-relaxed">
                  {it.evidence}
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {it.evidence_source
                      ? `Manba: ${it.evidence_source}${it.confidence ? ` · ishonch ${it.confidence}%` : ''}`
                      : it.hint}
                  </div>
                </div>
              </details>
            </li>
          )
        })}
      </ul>

      {!!data.extra_documents?.length && (
        <div className="border-t px-3 py-2 text-[12px] text-muted-foreground"
          title="Bu tenderda talab qilinmagan">
          Bazangizda yana bor: {data.extra_documents.map((e) => e.label).join(', ')}
        </div>
      )}

      <div className="border-t bg-muted px-3 py-2 text-[11px] text-muted-foreground">
        {s.disclaimer}
      </div>
    </Card>
  )
}

function Pill({ tone, children, title }: {
  tone: 'ok' | 'soon' | 'bad'
  children: React.ReactNode
  title?: string
}) {
  const cls = tone === 'ok' ? 'bg-ok-soft text-ok'
    : tone === 'soon' ? 'bg-soon-soft text-soon' : 'bg-urgent-soft text-urgent'
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', cls)} title={title}>
      {children}
    </span>
  )
}
