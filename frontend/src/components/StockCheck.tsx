import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
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
  yetarli: 'bg-ok-soft text-ok',
  yetishmaydi: 'bg-urgent-soft text-urgent',
  nomalum: 'bg-soon-soft text-soon',
}

const num = (v: number | null | undefined) =>
  (v == null ? '—' : Number(v).toLocaleString('ru-RU'))

export default function StockCheck({ tenderId }: { tenderId: number }) {
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
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
        {error}
      </div>
    )
  }
  if (!data) return null

  const s = data.summary
  if (s.matched === 0) {
    return (
      <div className="mb-4 rounded-lg border border-dashed bg-card px-4 py-3 text-center text-[13px] text-muted-foreground">
        {s.positions} ta pozitsiyaning hech biri katalogingizga mos kelmadi.
      </div>
    )
  }

  return (
    <div className="mb-4 space-y-3">
      {/* Qoldiq yangiligi — TZ: eskirgan/yuklanmagan bo'lsa OGOHLANTIRISH */}
      {data.stock?.warning && (
        <div className="rounded-lg border border-soon/40 bg-soon-soft px-3 py-2 text-[13px] text-soon">
          {data.stock.warning}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat n={s.matched} label="Mos pozitsiya" />
        <Stat n={s.ok} label="Yetarli" tone="ok" />
        <Stat n={s.short} label="Yetishmayapti" tone="bad" />
        <Stat n={s.unknown} label="Noma’lum" tone="warn" />
        <Stat n={s.unmatched} label="Katalogda yo‘q" />
      </div>

      {/* --- YETISHMAYOTGANLAR: alohida ajratilgan ro'yxat --- */}
      {data.shortages.length > 0 && (
        <Card className="overflow-hidden border-urgent/40">
          <div className="flex items-center gap-2 bg-urgent-soft px-3 py-2 text-[13px] font-semibold text-urgent">
            <Icon name="box" size={14} />
            Yetishmayapti — {data.shortages.length} ta
            {data.preliminary && <span className="font-normal opacity-80">(dastlabki)</span>}
          </div>
          <StockTable items={data.shortages} shortage />
        </Card>
      )}

      {/* --- Barcha mos pozitsiyalar --- */}
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b px-3 py-2 text-[13px] font-semibold">
          Mos pozitsiyalar
          {data.preliminary && (
            <span className="text-[12px] font-normal text-muted-foreground">dastlabki</span>
          )}
        </div>
        <StockTable items={data.items} />
      </Card>
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: 'ok' | 'bad' | 'warn' }) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'bad' ? 'text-urgent'
    : tone === 'warn' ? 'text-soon' : 'text-foreground'
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-center">
      <div className={cn('tabular text-[19px] font-bold leading-tight', color)}>{n}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  )
}

function StockTable({ items, shortage }: { items: StockItem[]; shortage?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <Table className="text-[13px]">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Pozitsiya</TableHead>
            <TableHead className="w-[110px] text-right">So‘ralgan</TableHead>
            <TableHead className="w-[100px] text-right">{shortage ? 'Qoldiq' : 'Ombor'}</TableHead>
            {shortage
              ? <TableHead className="w-[110px] text-right">Yetishmaydi</TableHead>
              : <TableHead className="w-[130px]">Holat</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((it, i) => (
            <TableRow key={`${it.lot_id}-${it.item_id}-${i}`} className="hover:bg-transparent">
              <TableCell>
                {it.name}
                <div className="text-[12px] text-muted-foreground">
                  {it.product.name}
                  {!shortage && it.product.stock_age_days != null &&
                    ` · ${it.product.stock_age_days} kun oldin`}
                </div>
              </TableCell>
              <TableCell className="tabular text-right">
                {num(it.required_qty)} {it.unit || ''}
                {it.required_qty == null && it.qty_note && (
                  <div className="text-[11px] font-normal text-muted-foreground">{it.qty_note}</div>
                )}
              </TableCell>
              <TableCell className="tabular text-right">{num(it.available_qty)}</TableCell>
              {shortage ? (
                <TableCell className="tabular text-right font-bold text-urgent">
                  {num(it.shortfall_qty)}
                </TableCell>
              ) : (
                <TableCell>
                  <span className={cn('rounded px-2 py-0.5 text-[12px] font-semibold', BADGE[it.status])}>
                    {it.status_label}
                  </span>
                  {it.reason && (
                    <div className="text-[11px] text-muted-foreground">{it.reason}</div>
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
