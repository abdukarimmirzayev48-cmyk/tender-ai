import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis,
} from 'recharts'
import { ChevronLeft } from 'lucide-react'
import { api } from '@/api'
import { useFormat } from '@/format'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ChartContainer, ChartTooltip, ChartTooltipContent,
} from '@/components/ui/chart'
import type { ChartConfig } from '@/components/ui/chart'
import type { Region, Stats } from '@/types'

// Statistika sahifasi: valyuta bo'yicha (ALOHIDA) + hudud bo'yicha taqsimot.
//
// GRAFIK — `ui/chart` komponenti (ichida Recharts). Ilgari hudud
// taqsimoti qo'lda yozilgan CSS chiziqchalar edi: qiymatni faqat uzunlikdan
// taxmin qilish mumkin edi, tooltip ham yo'q edi. Endi o'q, panjara va
// tooltip bor — raqamni o'qish uchun sichqonchani olib borish yetarli.
//
// VALYUTALAR ARALASHTIRILMAYDI: kartochkalar har valyuta uchun alohida
// (kurs konvertatsiyasi tizimda yo'q — `api/pricing.py` bilan bir xil qoida).

// BITTA SERIYA — BITTA RANG.
//
// Avval har ustun beshta rangdan birini OLARDI (`BAR_COLORS[i % 5]`). Bu
// ikki jihatdan noto'g'ri edi:
//   · rang HECH NARSANI kodlamasdi — hudud nomi allaqachon o'qda turibdi,
//     ya'ni rangda ma'lumot yo'q, faqat shovqin;
//   · rang ustunning TARTIB RAQAMIGA bog'langan edi, hududning o'ziga
//     emas. Ro'yxat qayta tartiblansa yoki filtrlansa, o'sha hudud boshqa
//     rangga o'tib ketardi — ya'ni rang yolg'on gapirardi.
// Yagona seriya uchun afsona ham kerak emas: sarlavha uni nomlaydi.
const BAR_COLOR = 'var(--chart-1)'
const ALL_PROVINCES = '__all_provinces__'

export default function StatsView() {
  const t = useT()
  const f = useFormat()
  const [stats, setStats] = useState<Stats | null>(null)
  const [selectedRegion, setSelectedRegion] = useState('')
  const [provinceOptions, setProvinceOptions] = useState<Region[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    api.regions()
      .then((rows) => setProvinceOptions(
        rows.filter((row) => row.level === 1)
          .sort((a, b) => (a.name || '').localeCompare(b.name || '')),
      ))
      // Grafik ustunlari ham drill-down qiladi; dropdown yuklanmasa sahifa
      // butunlay yiqilmasin.
      .catch(() => {})
  }, [])

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    api.stats({ status: 'open', region: selectedRegion || undefined })
      .then((next) => { if (live) setStats(next) })
      .catch((e: Error) => { if (live) setError(e.message) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [selectedRegion, retryKey])

  // Grafik afsonasi tilga bog'liq — `t` o'zgarganda qayta yasaladi.
  const chartConfig = {
    tender_count: { label: t('stats.legendCount'), color: 'var(--chart-1)' },
  } satisfies ChartConfig

  if (error) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-body text-urgent-strong"
        role="alert">
        <span>{t('common.errorWith', { msg: error })}</span>
        <Button type="button" variant="outline" className="h-11"
          onClick={() => setRetryKey((key) => key + 1)}>
          {t('common.retry')}
        </Button>
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

  const regions = stats.by_region
    .map((row) => ({
      ...row,
      display_name: row.name || t(
        stats.scope === 'localities' ? 'stats.unknownLocality' : 'stats.unknownRegion',
      ),
    }))
    .slice()
    .sort((a, b) => b.tender_count - a.tender_count)
  const selectedName = stats.selected_region?.name
    || provinceOptions.find((row) => row.area_id === selectedRegion)?.name
    || ''
  const chartHeight = Math.max(360, regions.length * 30 + 56)

  function chooseRegion(areaId: string | null | undefined) {
    if (stats?.scope === 'provinces' && areaId) setSelectedRegion(areaId)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-title font-semibold">{t('stats.title')}</h2>
          <div className="mt-1 min-h-5 text-caption text-muted-foreground"
            role="status" aria-live="polite">
            {loading ? t('common.loading') : selectedName || t('stats.allProvinces')}
          </div>
        </div>

        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          {selectedRegion && (
            <Button type="button" variant="outline" className="h-11"
              onClick={() => setSelectedRegion('')}>
              <ChevronLeft className="size-4" aria-hidden="true" />
              {t('stats.backToProvinces')}
            </Button>
          )}
          <Select value={selectedRegion || ALL_PROVINCES}
            onValueChange={(value) => setSelectedRegion(
              value === ALL_PROVINCES ? '' : value,
            )}>
            <SelectTrigger className="h-11 w-full sm:w-64"
              aria-label={t('stats.chooseProvince')}>
              <SelectValue placeholder={t('stats.chooseProvince')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PROVINCES}>{t('stats.allProvinces')}</SelectItem>
              {provinceOptions.map((region) => (
                <SelectItem key={region.area_id} value={region.area_id}>
                  {region.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className={`grid gap-3 transition-opacity motion-reduce:transition-none sm:grid-cols-2 lg:grid-cols-3 ${loading ? 'opacity-60' : ''}`}
        aria-busy={loading}>
        <Card className="p-4">
          <div className="tabular text-display font-semibold leading-tight">
            {f.num(stats.count)}
          </div>
          <div className="text-caption text-muted-foreground">
            {stats.selected_region
              ? t('stats.totalOpenInRegion', { region: stats.selected_region.name })
              : t('stats.totalOpen')}
          </div>
        </Card>
        {/* KARTOCHKADA QISQARTIRILGAN SUMMA.
            Avval bu yerda to'liq son turardi — "747,142,659,355.07 UZS".
            O'n besh xonali raqamni bir qarashda o'qib bo'lmaydi, holbuki
            kartochkaning butun vazifasi shu: bir qarashda ko'rsatish.
            Aniq qiymat yo'qolmadi — u `title` da, sichqoncha olib borilsa
            chiqadi. */}
        {(stats.by_currency || []).map((c) => (
          <Card className="p-4" key={c.currency}>
            <div className="tabular text-display font-semibold leading-tight"
              title={f.money(c.total_value, c.currency)}>
              {f.shortMoney(c.total_value, c.currency)}
            </div>
            <div className="text-caption text-muted-foreground">
              {t('stats.currencyTotal', { n: c.tender_count, cur: c.currency })}
            </div>
          </Card>
        ))}
      </div>

      <Card className={`p-4 transition-opacity motion-reduce:transition-none ${loading ? 'opacity-60' : ''}`}
        aria-busy={loading}>
        <h3 className="mb-1 text-lead font-semibold">
          {stats.scope === 'localities'
            ? t('stats.byLocality', { region: stats.selected_region?.name || selectedName })
            : t('stats.byProvince')}
        </h3>
        <p className="mb-3 text-caption text-muted-foreground">
          {stats.scope === 'localities' ? t('stats.localityHint') : t('stats.provinceHint')}
        </p>

        {regions.length === 0 ? (
          <div className="py-8 text-center text-body text-muted-foreground">
            {t('stats.noData')}
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="w-full"
            style={{ height: chartHeight }}
            role="img"
            aria-label={stats.scope === 'localities'
              ? t('stats.byLocality', { region: stats.selected_region?.name || selectedName })
              : t('stats.byProvince')}>
            <BarChart
              data={regions}
              layout="vertical"
              margin={{ left: 4, right: 44, top: 4, bottom: 4 }}
            >
              <CartesianGrid horizontal={false} strokeDasharray="3 3" />
              {/* `tick={{fill}}` ATAYIN ochiq yozilgan. Recharts o'q
                  yozuvlariga `fill="#666"` ni ATRIBUT sifatida qo'yadi va u
                  bizning tokenlarimizni umuman ko'rmaydi. Yorug' mavzuda bu
                  sezilmasdi (5.7:1), qorong'ida esa 2.85:1 — WCAG chegarasidan
                  ancha past, ya'ni o'q qiymatlari o'qilmas holga kelardi. */}
              <XAxis type="number" dataKey="tender_count" tickLine={false} axisLine={false}
                fontSize={11} tick={{ fill: 'var(--muted-foreground)' }} />
              {/* Hudud nomlari uzun — o'q kengligi qat'iy, matn kesilmasin */}
              <YAxis type="category" dataKey="display_name" width={150} tickLine={false} axisLine={false}
                fontSize={12} interval={0} tick={{ fill: 'var(--foreground)' }} />
              <ChartTooltip
                cursor={{ fill: 'var(--muted)' }}
                content={
                  <ChartTooltipContent
                    formatter={(value, name, item) => {
                      const totals = (item?.payload as {
                        totals_by_currency?: { currency: string | null; total_value: number }[]
                      })?.totals_by_currency || []
                      return (
                        <div className="flex w-full flex-col gap-0.5">
                          <span className="tabular font-semibold">
                            {t('stats.tenderCount', { n: Number(value) })}
                          </span>
                          {totals.map((total, index) => (
                            <span key={`${total.currency || 'none'}-${index}`}
                              className="tabular text-muted-foreground">
                              {f.shortMoney(total.total_value, total.currency)}
                            </span>
                          ))}
                          <span className="sr-only">{String(name)}</span>
                        </div>
                      )
                    }}
                  />
                }
              />
              {/* Har ustunda soni yozib qo'yiladi — qiymatni o'qish uchun
                  sichqonchani olib borish shart emas. Matn rangi ustun
                  rangi EMAS, oddiy ikkilamchi siyoh: rangni faqat belgining
                  o'zi tashiydi. */}
              <Bar dataKey="tender_count" fill={BAR_COLOR} radius={[0, 4, 4, 0]} barSize={24}
                isAnimationActive={false}
                className={stats.scope === 'provinces' ? 'cursor-pointer' : undefined}
                onClick={(row) => chooseRegion(
                  (row as { payload?: { area_id?: string | null } }).payload?.area_id,
                )}>
                <LabelList dataKey="tender_count" position="right" fontSize={11}
                  fill="var(--muted-foreground)" />
              </Bar>
            </BarChart>
          </ChartContainer>
        )}

        {/* Grafikning ekran o'quvchi uchun jadval muqobili. Drill-downning
            klaviatura muqobili yuqoridagi Radix Select; qiymatlar esa shu
            jadvalda hover/ko'rishga bog'liq bo'lmasdan to'liq o'qiladi. */}
        <table className="sr-only">
          <caption>
            {stats.scope === 'localities'
              ? t('stats.byLocality', { region: stats.selected_region?.name || selectedName })
              : t('stats.byProvince')}
          </caption>
          <thead>
            <tr>
              <th scope="col">{t('stats.area')}</th>
              <th scope="col">{t('stats.legendCount')}</th>
              <th scope="col">{t('stats.legendSum')}</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((region) => (
              <tr key={region.area_id || 'unknown'}>
                <th scope="row">{region.display_name}</th>
                <td>{f.num(region.tender_count)}</td>
                <td>
                  {region.totals_by_currency.map((total) =>
                    f.money(total.total_value, total.currency)).join('; ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
