import { useFormat } from '@/format'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'
import type { Stats } from '@/types'

interface StatsStripProps {
  stats: Stats | null
  total: number
  lastUpdated: Date | null
}

// Jadval ustidagi ixcham statistika chizig'i.
//
// SONLAR ANIMATSIYASIZ. Avval ular nolddan sanab chiqardi. Filtr har
// o'zgarganda — ya'ni foydalanuvchi aynan natijani bilmoqchi bo'lganda —
// qiymat yarim soniya davomida YOLG'ON ko'rsatib turardi. Ish qurolida son
// darhol o'qiladigan bo'lishi kerak.
export default function StatsStrip({ stats, total, lastUpdated }: StatsStripProps) {
  const t = useT()
  const f = useFormat()
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border bg-card px-4 py-2.5 text-body">
      <Metric value={f.num(total)} label={t('strip.tenders')} />
      {stats && (
        <>
          <span aria-hidden="true" className="h-4 w-px bg-border" />
          <Metric value={f.num(stats.count)} label={t('strip.open')} tone="text-ok-strong" />
          {(stats.by_currency || []).map((c) => (
            <Metric
              key={c.currency}
              value={f.shortMoney(c.total_value, c.currency)}
              label={t('strip.inTenders', { n: c.tender_count })}
            />
          ))}
        </>
      )}
      {lastUpdated && (
        <span className="ml-auto text-caption text-muted-foreground">
          {t('strip.checkedAt', {
            time: lastUpdated.toLocaleTimeString(f.locale, { hour: '2-digit', minute: '2-digit' }),
          })}
        </span>
      )}
    </div>
  )
}

function Metric({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <b className={cn('tabular text-lead font-semibold', tone)}>{value}</b>
      <span className="text-muted-foreground">{label}</span>
    </span>
  )
}
