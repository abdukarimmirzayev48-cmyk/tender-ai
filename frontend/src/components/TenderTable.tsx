import { useState } from 'react'
import { shortMoney, deadline, DEADLINE_CLASS } from '@/format'
import Icon from './Icon'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { cn } from '@/lib/utils'
import type { TenderRow } from '@/types'

// Ball rozetkasi rangi (Sizga mos ko'rinishi uchun).
// Tailwind sinf nomlarini DINAMIK QURIB bo'lmaydi (JIT ularni topa olmaydi),
// shuning uchun to'liq sinflar shu yerda yozilgan.
function scoreClass(s: number) {
  if (s >= 70) return 'bg-ok-soft text-ok'
  if (s >= 40) return 'bg-soon-soft text-soon'
  return 'bg-muted text-muted-foreground'
}

// Manba qisqa yorlig'i — qaysi platformadan kelganini bir qarashda bilish uchun.
const SRC: Record<string, { label: string; cls: string }> = {
  'xt-xarid': { label: 'xt-xarid', cls: 'bg-secondary text-primary' },
  'uzex': { label: 'etender', cls: 'bg-soon-soft text-soon' },
}

interface ThProps {
  label: string
  col?: string
  sort?: string
  onSort?: (col: string) => void
  num?: boolean
  className?: string
}

function Th({ label, col, sort, onSort, num, className }: ThProps) {
  if (!col) {
    return <TableHead className={cn(num && 'text-right', className)}>{label}</TableHead>
  }
  const arrow = sort === col ? '▲' : sort === `-${col}` ? '▼' : ''
  return (
    <TableHead
      className={cn('cursor-pointer select-none hover:text-foreground', num && 'text-right', className)}
      onClick={() => onSort?.(col)}
    >
      {label} <span className="text-[9px] opacity-70">{arrow}</span>
    </TableHead>
  )
}

interface TenderTableProps {
  items: TenderRow[]
  mode: string
  onSelect: (id: number) => void
  sort: string
  onSort: (col: string) => void
  loading: boolean
  showStatus: boolean
}

export default function TenderTable({
  items, mode, onSelect, sort, onSort, loading, showStatus,
}: TenderTableProps) {
  const isMatch = mode === 'match'
  const [open, setOpen] = useState<Set<number>>(() => new Set())

  function toggle(e: React.MouseEvent, id: number) {
    e.stopPropagation()
    setOpen((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  if (loading && items.length === 0) {
    return (
      <div className="space-y-2 rounded-xl border bg-card p-4">
        {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
      </div>
    )
  }

  if (!loading && items.length === 0) {
    return (
      <Empty className="rounded-xl border border-dashed bg-card">
        <EmptyHeader>
          <EmptyTitle>Topilmadi</EmptyTitle>
          <EmptyDescription>Filtrlarni o‘zgartirib ko‘ring.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <Table className="text-[13px]">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {isMatch && <Th label="Ball" num className="w-[64px]" />}
            <Th label="" className="w-[32px]" />
            <Th label="Xarid predmeti" />
            <Th label="Manba" className="w-[96px]" />
            <Th label="Buyurtmachi" className="max-w-[200px]" />
            <Th label="Hudud" className="w-[130px]" />
            <Th label="Yetkazish" num className="w-[96px]" />
            <Th label="Summa" col="totalcost" sort={sort} onSort={onSort} num className="w-[130px]" />
            <Th label="Muddat" col="close_at" sort={sort} onSort={onSort} className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody className={cn(loading && 'opacity-50 transition-opacity')}>
          {items.map((t) => {
            const d = deadline(t.close_at)
            const m = t.match
            const lots = t.lots_summary || []
            const titled = lots.filter((l) => l.title)
            const isOpen = open.has(t.id)
            const cols = 8 + (isMatch ? 1 : 0)
            const src = SRC[t.source_platform] || { label: t.source_platform, cls: 'bg-muted text-muted-foreground' }

            // Sarlavha: lot nomlari (eng aniq), bo'lmasa tender nomi
            const title = titled.length > 0
              ? titled.map((l) => l.title).join('  ·  ')
              : (t.name || `#${t.id}`)

            // Ikkinchi qator FAQAT yangi ma'lumot qo'shsa ko'rsatiladi:
            // sarlavhada allaqachon bor mahsulotlarni takrorlamaymiz.
            const extra = (t.goods_preview || [])
              .filter((g) => g && !title.includes(g))
              .slice(0, 3)

            // Yetkazish muddati — lotlar bo'yicha eng uzuni
            const dlv = lots.reduce(
              (mx, l) => (l.delivery_period != null && l.delivery_period > mx ? l.delivery_period : mx), 0)

            return [
              <TableRow key={t.id} className="cursor-pointer" onClick={() => onSelect(t.id)}>
                {isMatch && (
                  <TableCell className="text-right">
                    <span className={cn(
                      'tabular inline-block min-w-[34px] rounded-md px-2 py-0.5 text-center text-[13px] font-extrabold',
                      scoreClass(m?.score ?? 0),
                    )}>{m?.score ?? 0}</span>
                  </TableCell>
                )}
                <TableCell className="pr-0">
                  {lots.length > 0 && (
                    <button
                      className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      onClick={(e) => toggle(e, t.id)} title={`${lots.length} lot`}
                    >
                      <Icon name="right" size={12} className={cn('transition-transform', isOpen && 'rotate-90')} />
                    </button>
                  )}
                </TableCell>

                <TableCell className="max-w-[420px] py-2.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-medium" title={title}>
                    <span className="line-clamp-2">{title}</span>
                    {lots.length > 1 && (
                      <span className="rounded bg-muted px-1.5 py-px text-[11px] text-muted-foreground">
                        {lots.length} lot
                      </span>
                    )}
                    {!!t.doc_count && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-secondary px-1.5 py-px text-[11px] text-primary"
                        title={`${t.doc_count} ta hujjat`}>
                        <Icon name="clip" size={10} />{t.doc_count}
                      </span>
                    )}
                    {showStatus && (
                      <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                        {t.status_name || t.status}
                      </Badge>
                    )}
                  </div>
                  {extra.length > 0 && (
                    <div className="mt-0.5 truncate text-[12px] text-muted-foreground"
                      title={(t.goods_preview || []).join(', ')}>
                      {extra.join(' · ')}
                    </div>
                  )}
                  {isMatch && !!m?.matched_keywords?.length && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {m.matched_keywords.map((k) => (
                        <span key={k} className="rounded bg-secondary px-1.5 py-px text-[11px] text-primary">
                          {k}
                        </span>
                      ))}
                    </div>
                  )}
                </TableCell>

                <TableCell>
                  <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', src.cls)}>
                    {src.label}
                  </span>
                </TableCell>
                <TableCell className="max-w-[200px] truncate text-muted-foreground" title={t.company?.name ?? ''}>
                  {t.company?.name || '—'}
                </TableCell>
                <TableCell className="truncate text-muted-foreground" title={t.region?.name ?? ''}>
                  {t.region?.name || '—'}
                </TableCell>
                <TableCell className="tabular text-right text-muted-foreground">
                  {dlv ? `${dlv} kun` : '—'}
                </TableCell>
                <TableCell className="tabular text-right font-semibold">
                  {shortMoney(t.totalcost, t.currency)}
                </TableCell>
                <TableCell>
                  <span className={cn('rounded px-2 py-0.5 text-[12px] font-semibold', DEADLINE_CLASS[d.level])}>
                    {d.short}
                  </span>
                </TableCell>
              </TableRow>,

              isOpen ? (
                <TableRow key={`${t.id}-lots`} className="bg-muted/60 hover:bg-muted/60">
                  <TableCell colSpan={cols} className="py-2">
                    {lots.map((l) => (
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-1 text-[12.5px]" key={l.lot_id}>
                        <span className="w-[70px] shrink-0 text-[11px] font-semibold text-muted-foreground">
                          Lot {l.lot_id}
                        </span>
                        <span className="flex-1 min-w-[200px]">{l.title || '— nomsiz —'}</span>
                        <span className="flex flex-wrap items-baseline gap-x-3 text-muted-foreground">
                          {l.total_sum_lot != null && (
                            <b className="tabular text-foreground">{shortMoney(l.total_sum_lot, t.currency)}</b>
                          )}
                          {l.item_count != null && <span>{l.item_count} pozitsiya</span>}
                          {l.delivery_period != null && (
                            <span title="Yetkazish muddati">{l.delivery_period} kun</span>
                          )}
                          {l.guarantee != null && <span title="Kafolat">kafolat {l.guarantee} kun</span>}
                        </span>
                      </div>
                    ))}
                    {(t.goods_preview || []).length > 0 && (
                      <div className="flex gap-3 border-t pt-2 text-[12.5px] text-muted-foreground">
                        <span className="w-[70px] shrink-0 text-[11px] font-semibold">Tovar</span>
                        <span>{t.goods_preview!.join(' · ')}</span>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ) : null,
            ]
          })}
        </TableBody>
      </Table>
    </div>
  )
}
