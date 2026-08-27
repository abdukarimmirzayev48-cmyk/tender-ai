import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { useT } from '@/i18n'
import { useFormat } from '@/format'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { StockCheckResult, StockItem } from '@/types'

// MOS KELGAN POZITSIYALAR BO'YICHA OMBOR QOLDIG'I (TZ P0-6)
//
// Ko'rsatiladi:
//   * har bir mos pozitsiya: so'ralgan miqdor / ombordagi qoldiq / YETARLIMI
//   * yetishmayotganlar ALOHIDA, qizil blokda ajratilgan ro'yxatda
//   * qoldiq yuklanmagan yoki eskirgan bo'lsa — ogohlantirish va solishtiruv
//     "DASTLABKI" deb belgilanadi
const BADGE: Record<StockItem['status'], string> = {
  yetarli: 'bg-ok-soft text-ok-strong',
  yetishmaydi: 'bg-urgent-soft text-urgent-strong',
  nomalum: 'bg-soon-soft text-soon-strong',
}

export default function StockCheck({ tenderId }: { tenderId: number }) {
  const t = useT()
  const [data, setData] = useState<StockCheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null); setData(null)
    api.stockCheck(tenderId)
      .then((b) => { if (alive) setData(b) })
      .catch((e: Error) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [tenderId])

  if (loading) return <Skeleton className="mb-4 h-24 w-full rounded-lg" />
  if (error) {
    return (
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-body text-urgent-strong">
        {error}
      </div>
    )
  }
  if (!data) return null

  const s = data.summary
  if (s.matched === 0) {
    return (
      <div className="mb-4 rounded-lg border border-dashed bg-card px-4 py-3 text-center text-body text-muted-foreground">
        {t('stock.noMatch', { n: s.positions })}
      </div>
    )
  }

  return (
    <div className="mb-4 space-y-3">
      {/* Qoldiq yangiligi — TZ: eskirgan/yuklanmagan bo'lsa OGOHLANTIRISH */}
      {data.stock?.warning && (
        <div className="rounded-lg border border-soon/40 bg-soon-soft px-3 py-2 text-body text-soon-strong">
          {data.stock.warning}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat n={s.matched} label={t('stock.matched')} />
        <Stat n={s.ok} label={t('stock.enough')} tone="ok" />
        <Stat n={s.short} label={t('stock.short')} tone="bad" />
        <Stat n={s.unknown} label={t('stock.unknown')} tone="warn" />
        <Stat n={s.unmatched} label={t('stock.notInCatalog')} />
      </div>

      {/* --- YETISHMAYOTGANLAR: alohida ajratilgan ro'yxat --- */}
      {data.shortages.length > 0 && (
        <Card className="overflow-hidden border-urgent/40">
          <div className="flex items-center gap-2 bg-urgent-soft px-3 py-2 text-body font-semibold text-urgent-strong">
            <Icon name="box" size={14} />
            {t('stock.shortagesTitle', { n: data.shortages.length })}
            {data.preliminary && (
              <span className="font-normal opacity-80">({t('stock.preliminary')})</span>
            )}
          </div>
          <StockTable items={data.shortages} shortage />
        </Card>
      )}

      {/* --- Barcha mos pozitsiyalar --- */}
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b px-3 py-2 text-body font-semibold">
          {t('stock.matchedTitle')}
          {data.preliminary && (
            <span className="text-caption font-normal text-muted-foreground">
              {t('stock.preliminary')}
            </span>
          )}
        </div>
        <StockTable items={data.items} />
      </Card>
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: 'ok' | 'bad' | 'warn' }) {
  const color = tone === 'ok' ? 'text-ok-strong' : tone === 'bad' ? 'text-urgent-strong'
    : tone === 'warn' ? 'text-soon-strong' : 'text-foreground'
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-center">
      <div className={cn('tabular text-title font-semibold leading-tight', color)}>{n}</div>
      <div className="text-micro text-muted-foreground">{label}</div>
    </div>
  )
}

function StockTable({ items, shortage }: { items: StockItem[]; shortage?: boolean }) {
  const t = useT()
  const f = useFormat()
  const num = (v: number | null | undefined) => f.num(v)
  return (
    <div className="overflow-x-auto">
      <Table className="text-body">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>{t('stock.thPosition')}</TableHead>
            <TableHead className="w-[110px] text-right">{t('stock.thRequired')}</TableHead>
            <TableHead className="w-[100px] text-right">
              {t(shortage ? 'stock.thStockLeft' : 'stock.thStock')}
            </TableHead>
            {shortage
              ? <TableHead className="w-[110px] text-right">{t('stock.thShortfall')}</TableHead>
              : <TableHead className="w-[130px]">{t('stock.thStatus')}</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((it, i) => (
            <TableRow key={`${it.lot_id}-${it.item_id}-${i}`} className="hover:bg-transparent">
              <TableCell>
                {it.name}
                <div className="text-caption text-muted-foreground">
                  {it.product.name}
                  {!shortage && it.product.stock_age_days != null &&
                    ` · ${t('stock.ageDays', { n: it.product.stock_age_days })}`}
                </div>
              </TableCell>
              <TableCell className="tabular text-right">
                {num(it.required_qty)} {it.unit || ''}
                {it.required_qty == null && it.qty_note && (
                  <div className="text-micro font-normal text-muted-foreground">{it.qty_note}</div>
                )}
              </TableCell>
              <TableCell className="tabular text-right">{num(it.available_qty)}</TableCell>
              {shortage ? (
                <TableCell className="tabular text-right font-semibold text-urgent-strong">
                  {num(it.shortfall_qty)}
                </TableCell>
              ) : (
                <TableCell>
                  <span className={cn('rounded px-2 py-0.5 text-caption font-semibold', BADGE[it.status])}>
                    {it.status_label}
                  </span>
                  {it.reason && (
                    <div className="text-micro text-muted-foreground">{it.reason}</div>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
