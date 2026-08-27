import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { useT } from '@/i18n'
import type { TKey } from '@/i18n'
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
const STATUS: Record<ComplianceItem['status'], { mark: string; text: TKey; cls: string }> = {
  ok: { mark: '✓', text: 'compliance.status.ok', cls: 'bg-ok-soft text-ok-strong' },
  expiring_soon: {
    mark: '!', text: 'compliance.status.expiring_soon', cls: 'bg-soon-soft text-soon-strong',
  },
  expired: { mark: '×', text: 'compliance.status.expired', cls: 'bg-urgent-soft text-urgent-strong' },
  missing: { mark: '×', text: 'compliance.status.missing', cls: 'bg-urgent-soft text-urgent-strong' },
}

const dateFmt = (iso?: string | null) => (iso ? iso.split('-').reverse().join('.') : null)

interface CompliancePanelProps {
  tenderId: number
  onOpenDocuments?: (docType: string) => void
}

export default function CompliancePanel({ tenderId, onOpenDocuments }: CompliancePanelProps) {
  const t = useT()
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
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-body text-urgent-strong">
        {t('compliance.loadFailed', { msg: error })}
      </div>
    )
  }
  if (!data) return <Skeleton className="mb-4 h-32 w-full rounded-lg" />

  const s = data.summary

  return (
    <Card className="mb-4 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <Icon name="check" size={14} className="text-primary" />
        <span className="text-body font-semibold">{t('compliance.title')}</span>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone="ok">{t('compliance.ready', { n: s.ready })}</Pill>
          {s.expiring_soon > 0 && (
            <Pill tone="soon">{t('compliance.expiringSoon', { n: s.expiring_soon })}</Pill>
          )}
          {s.expired > 0 && (
            <Pill tone="bad" title={t('compliance.expiredTitle')}>
              {t('compliance.expired', { n: s.expired })}
            </Pill>
          )}
          {s.missing > 0 && <Pill tone="bad">{t('compliance.missing', { n: s.missing })}</Pill>}
          {s.blocking === 0 && <Pill tone="ok">{t('compliance.complete')}</Pill>}
        </div>
        <button
          className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label={t('compliance.refresh')} title={t('compliance.refresh')} onClick={() => setReloadKey((k) => k + 1)}
        >
          <Icon name="refresh" size={12} />
        </button>
      </div>

      {/* HALOL HOLAT: tender matnidan hech narsa topilmasa — jim turmaymiz. */}
      <div className="border-b bg-muted px-3 py-2 text-caption text-muted-foreground">{s.note}</div>

      <ul className="divide-y divide-border-soft">
        {data.items.map((it) => {
          const st = STATUS[it.status] || STATUS.missing
          const d = it.document
          return (
            <li className="px-3 py-2.5" key={it.doc_type}>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full text-caption font-semibold',
                    st.cls,
                  )}
                  aria-hidden="true"
                >{st.mark}</span>

                <span className="text-body font-medium">{it.label}</span>
                <span className={cn(
'rounded px-1.5 py-px text-micro font-semibold',
                  it.required_by === 'tender'
                    ? 'bg-secondary text-primary'
                    : 'bg-muted text-muted-foreground',
                )}>
                  {t(it.required_by === 'tender'
                    ? 'compliance.requiredByTender' : 'compliance.requiredByBase')}
                </span>

                <span className={cn('ml-auto rounded px-2 py-0.5 text-caption font-semibold', st.cls)}>
                  {t(st.text)}
                </span>
              </div>

              {d && (
                <div className="mt-1 pl-7 text-caption text-muted-foreground">
                  {d.name}
                  {d.number ? ` · № ${d.number}` : ''}
                  {d.valid_until
                    ? ` · ${t('compliance.validUntil', { date: dateFmt(d.valid_until)! })}`
                    : ` · ${t('compliance.perpetual')}`}
                  {it.days_left != null && it.status === 'expiring_soon'
                    ? ` ${t('compliance.daysLeft', { n: it.days_left })}` : ''}
                  {it.days_left != null && it.status === 'expired'
                    ? ` ${t('compliance.daysAgo', { n: Math.abs(it.days_left) })}` : ''}
                </div>
              )}

              {/* Muammoli band — nima qilish kerakligi darhol aytiladi */}
              {(it.status === 'missing' || it.status === 'expired') && onOpenDocuments && (
                <div className="mt-1 pl-7">
                  <button
                    className="text-caption font-semibold text-primary underline-offset-2 hover:underline"
                    onClick={() => onOpenDocuments(it.doc_type)}
                  >
                    {t(it.status === 'missing' ? 'compliance.addDoc' : 'compliance.renewDoc')}
                  </button>
                </div>
              )}

              {/* DALIL — shaffoflik: talab qayerdan kelib chiqdi */}
              <details className="mt-1 pl-7 text-caption">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  {t('compliance.why')}
                </summary>
                <div className="mt-1 rounded-md bg-muted p-2 leading-relaxed">
                  {it.evidence}
                  <div className="mt-1 text-micro text-muted-foreground">
                    {it.evidence_source
                      ? t('compliance.evidenceSource', { source: it.evidence_source })
                        + (it.confidence ? ` · ${t('compliance.confidence', { n: it.confidence })}` : '')
                      : it.hint}
                  </div>
                </div>
              </details>
            </li>
          )
        })}
      </ul>

      {!!data.extra_documents?.length && (
        <div className="border-t px-3 py-2 text-caption text-muted-foreground"
          title={t('compliance.alsoHaveTitle')}>
          {t('compliance.alsoHave', {
            items: data.extra_documents.map((e) => e.label).join(', '),
          })}
        </div>
      )}

      <div className="border-t bg-muted px-3 py-2 text-micro text-muted-foreground">
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
  const cls = tone === 'ok' ? 'bg-ok-soft text-ok-strong'
    : tone === 'soon' ? 'bg-soon-soft text-soon-strong' : 'bg-urgent-soft text-urgent-strong'
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-micro font-semibold', cls)} title={title}>
      {children}
    </span>
  )
}
