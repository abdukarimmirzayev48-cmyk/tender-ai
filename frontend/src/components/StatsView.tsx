import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis, YAxis,
} from 'recharts'
import { api } from '@/api'
import { money, shortMoney } from '@/format'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { AnimatedNumber } from '@/components/ui/animated-number'
import {
  ChartContainer, ChartTooltip, ChartTooltipContent,
} from '@/components/ui/chart'
import type { ChartConfig } from '@/components/ui/chart'
import type { Stats } from '@/types'

// Statistika sahifasi: valyuta bo'yicha (ALOHIDA) + hudud bo'yicha taqsimot.
//
// GRAFIK — Vengeance UI `chart` komponenti (ichida Recharts). Ilgari hudud
// taqsimoti qo'lda yozilgan CSS chiziqchalar edi: qiymatni faqat uzunlikdan
// taxmin qilish mumkin edi, tooltip ham yo'q edi. Endi o'q, panjara va
// tooltip bor — raqamni o'qish uchun sichqonchani olib borish yetarli.
//
// VALYUTALAR ARALASHTIRILMAYDI: kartochkalar har valyuta uchun alohida
// (kurs konvertatsiyasi tizimda yo'q — `api/pricing.py` bilan bir xil qoida).

// Har ustunga o'z rangi. Tailwind `--chart-N` tokenlari `index.css` da.
const BAR_COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
  'var(--chart-4)', 'var(--chart-5)',
]

const chartConfig = {
  tender_count: { label: 'Tender', color: 'var(--chart-1)' },
  total_value: { label: 'Summa', color: 'var(--chart-2)' },
} satisfies ChartConfig

export default function StatsView() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.stats({ status: 'open' }).then(setStats).catch((e: Error) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
        Xatolik: {error}
      </div>
    )
  }
  if (!stats) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-[320px] w-full" />
      </div>
    )
  }

  const regions = (stats.by_region || [])
    .slice()
    .sort((a, b) => b.tender_count - a.tender_count)
    .slice(0, 14)

  return (
    <div className="space-y-5">
      <h2 className="text-[18px] font-bold">Statistika — ochiq tenderlar</h2>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Card className="p-4">
          <div className="tabular text-[26px] font-bold leading-tight">
            <AnimatedNumber value={stats.count} />
          </div>
          <div className="text-[12px] text-muted-foreground">Jami ochiq tender</div>
        </Card>
        {(stats.by_currency || []).map((c) => (
          <Card className="p-4" key={c.currency}>
            <div className="tabular text-[26px] font-bold leading-tight">
              {money(c.total_value, c.currency)}
            </div>
            <div className="text-[12px] text-muted-foreground">
              {c.tender_count} ta · {c.currency} umumiy summa
            </div>
          </Card>
        ))}
      </div>

      <Card className="p-4">
        <h3 className="mb-1 text-[15px] font-semibold">Hudud bo‘yicha taqsimot</h3>
        <p className="mb-3 text-[12px] text-muted-foreground">
          Tender soni · eng ko‘pi bo‘yicha tartiblangan
          {(stats.by_region || []).length > regions.length &&
            ` · eng yuqori ${regions.length} tasi`}
        </p>

        {regions.length === 0 ? (
          <div className="py-8 text-center text-[13px] text-muted-foreground">
            Ma'lumot yo‘q.
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="h-[420px] w-full">
            <BarChart
              data={regions}
              layout="vertical"
              margin={{ left: 4, right: 44, top: 4, bottom: 4 }}
            >
              <CartesianGrid horizontal={false} strokeDasharray="3 3" />
              <XAxis type="number" dataKey="tender_count" tickLine={false} axisLine={false}
                fontSize={11} />
              {/* Hudud nomlari uzun — o'q kengligi qat'iy, matn kesilmasin */}
              <YAxis type="category" dataKey="name" width={150} tickLine={false} axisLine={false}
                fontSize={12} interval={0} />
              <ChartTooltip
                cursor={{ fill: 'var(--muted)' }}
                content={
                  <ChartTooltipContent
                    formatter={(value, name, item) => (
                      <div className="flex w-full flex-col gap-0.5">
                        <span className="tabular font-semibold">{String(value)} ta tender</span>
                        <span className="tabular text-muted-foreground">
                          {shortMoney((item?.payload as { total_value?: number })?.total_value)}
                        </span>
                        <span className="sr-only">{String(name)}</span>
                      </div>
                    )}
                  />
                }
              />
              <Bar dataKey="tender_count" radius={[0, 5, 5, 0]} barSize={18}>
                {regions.map((r, i) => (
                  <Cell key={r.name} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
                <LabelList dataKey="tender_count" position="right" fontSize={11}
                  fill="var(--muted-foreground)" />
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </Card>
    </div>
  )
}
