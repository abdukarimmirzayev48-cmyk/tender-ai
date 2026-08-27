import { useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import AiDocsNote from './AiDocsNote'
import { useT } from '@/i18n'
import type { TKey } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { AiMatchResult } from '@/types'

// AI MOSLIK TAHLILI — "bu tender menga mos keladimi?"
//
// TALAB BO'YICHA ishlaydi (avtomatik emas): har tahlil Claude chaqiruvi, ya'ni
// pul. Foydalanuvchi o'zi bosadi. Natija backendda keshlanadi, shuning uchun
// bir tenderni qayta ochsa yangi so'rov ketmaydi.
const VERDICT: Record<string, { label: TKey; edge: string; text: string }> = {
  mos: { label: 'ai.verdict.mos', edge: 'border-l-ok', text: 'text-ok-strong' },
  qisman: { label: 'ai.verdict.qisman', edge: 'border-l-soon', text: 'text-soon-strong' },
  mos_emas: { label: 'ai.verdict.mos_emas', edge: 'border-l-urgent', text: 'text-urgent-strong' },
}

export default function AiMatch({ tenderId }: { tenderId: number }) {
  const t = useT()
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
        title={t('ai.buttonTitle')}>
        <Icon name="sparkle" size={14} />
        {t('ai.button')}
      </Button>
    )
  }

  if (loading) {
    // Tahlil 5-20 soniya oladi. Avval bu yerda "sparkle" ikoni lipillab
    // turardi — u qancha kutishni ham, ish borayotganini ham bildirmasdi.
    // Noaniq (indeterminate) chiziq esa aynan shuni bildiradi: jarayon
    // ketyapti, tugash vaqti oldindan noma'lum.
    return (
      <div className="mb-4 rounded-lg border bg-card px-4 py-3" role="status" aria-live="polite">
        <div className="flex items-center gap-2 text-body text-muted-foreground">
          <Icon name="sparkle" size={14} />
          {t('ai.loading')}
        </div>
        <div className="mt-2.5 h-0.5 overflow-hidden rounded-full bg-border">
          <div className="h-full w-1/3 rounded-full bg-primary motion-safe:animate-[indeterminate_1.4s_ease-in-out_infinite]" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mb-4 space-y-2 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-body text-urgent-strong">
        <div>{error}</div>
        <Button variant="outline" size="sm" onClick={() => run(false)}>{t('common.retry')}</Button>
      </div>
    )
  }

  const known = VERDICT[data!.verdict]
  const v = known || { label: null, edge: 'border-l-primary', text: 'text-primary' }
  const verdictLabel = known ? t(known.label) : data!.verdict
  return (
    <Card className={cn('mb-4 border-l-4', v.edge)}>
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <Icon name="sparkle" size={13} className={v.text} />
          <span className={cn('text-lead font-semibold', v.text)}>{verdictLabel}</span>
          <span className="tabular ml-auto text-lead font-semibold">
            {data!.score}
            <span className="text-caption font-normal text-muted-foreground">/100</span>
          </span>
          <button
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label={t('ai.reanalyze')} title={t('ai.reanalyze')} onClick={() => run(true)}
          >
            <Icon name="refresh" size={12} />
          </button>
        </div>

        <p className="text-body leading-relaxed">{data!.reason_uz}</p>

        {!!data!.matched_items?.length && (
          <div className="flex flex-wrap items-center gap-1.5 text-caption">
            <b>{t('ai.fromCatalog')}</b>
            {data!.matched_items!.map((m) => (
              <span key={m} className="rounded bg-secondary px-1.5 py-px text-primary">{m}</span>
            ))}
          </div>
        )}

        {!!data!.requirements?.length && (
          <Block label={t('ai.requirements')} items={data!.requirements!} />
        )}
        {!!data!.risks?.length && (
          <Block label={t('ai.risks')} items={data!.risks!} tone="warn" />
        )}

        {/* Tahlil qaysi hujjatlarga tayangani — TZ shaffoflik talabi */}
        <AiDocsNote meta={data!.documents} />

        <div className="text-micro text-muted-foreground">
          {t(data!.cached ? 'ai.cached' : 'ai.fresh')}{data!.model ? ` · ${data!.model}` : ''}
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
      <div className="mb-1 text-micro font-semibold text-muted-foreground">
        {label}
      </div>
      <ul className="list-disc space-y-0.5 pl-4 text-body">
        {items.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  )
}
