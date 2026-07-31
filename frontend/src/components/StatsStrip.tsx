import { shortMoney } from '@/format'
import Icon from './Icon'
import { AnimatedNumber } from '@/components/ui/animated-number'
import type { Stats } from '@/types'

interface StatsStripProps {
  stats: Stats | null
  total: number
  lastUpdated: Date | null
}

// Jadval ustidagi ixcham statistika chizig'i.
// Sonlar Vengeance UI `AnimatedNumber` bilan — filtr o'zgarganda qiymat
// sakramaydi, sanab o'tadi (o'zgargani sezilsin).
export default function StatsStrip({ stats, total, lastUpdated }: StatsStripProps) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-card px-4 py-2.5 text-[13px]">
      <span className="flex items-center gap-1.5">
        <b className="tabular text-[15px] font-bold"><AnimatedNumber value={total} /></b>
        <span className="text-muted-foreground">tender</span>
      </span>
      {stats && (
        <>
          <span className="h-4 w-px bg-border" />
          <span className="flex items-center gap-1.5">
            <b className="tabular text-[15px] font-bold text-ok">
              <AnimatedNumber value={stats.count} />
            </b>
            <span className="text-muted-foreground">ochiq</span>
          </span>
          {(stats.by_currency || []).map((c) => (
            <span className="tabular text-muted-foreground" key={c.currency}>
              <b className="font-semibold text-foreground">
                {shortMoney(c.total_value, c.currency)}
              </b>{' '}
              ({c.tender_count})
            </span>
          ))}
        </>
      )}
      {lastUpdated && (
        <span className="ml-auto flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <Icon name="refresh" size={12} />
          {lastUpdated.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
        </span>
      )}
    </div>
  )
}
