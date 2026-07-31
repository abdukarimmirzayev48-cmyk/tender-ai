import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api'
import { calculate, DEFAULTS } from '@/pricing'
import type { CalcInput, RawItem } from '@/pricing'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { TenderDetail } from '@/types'

// NARX HISOBI — "qancha narx qo'yamiz?" (REJA.md P0-7)
//
// TZ ning ikki qabul mezoni shu komponentda bajariladi:
//   1. "Hisoblash FORMULASI KO'RINADI va TAHRIRLANADI" — pastdagi "Hisob
//      ketma-ketligi" jadvali har bosqichning formulasini RAQAMLARI bilan
//      ko'rsatadi; yuqoridagi barcha maydonlar tahrirlanadi.
//   2. "Kiruvchi o'zgarganda SAHIFANI QAYTA YUKLAMASDAN qayta hisoblanadi" —
//      hisob `src/pricing.ts` da, React stateda bajariladi. Har tugmachada
//      natija darhol yangilanadi, SERVERGA SO'ROV YO'Q.
//
// Server bilan aloqa faqat ikki joyda: boshlang'ich yuklash (sozlamalar +
// saqlangan smeta) va SAQLASH. Saqlashda server o'z nusxasi bilan qayta
// hisoblaydi — bazaga yozilgani doim serverning natijasi (yagona haqiqat).
//
// AI YO'Q: bu sof arifmetika. Barcha izohlar `api/pricing.py` da.

const nf = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const fmtNum = (v: number | null | undefined) =>
  (v === null || v === undefined ? '—' : nf.format(v))

// Foizda o'lchanadigan bosqichlar — qolganlari pul.
const PERCENT_STEPS = new Set(['profit_percent', 'budget_ratio'])
// Ajratib ko'rsatiladigan hal qiluvchi bosqichlar
const KEY_STEPS = new Set(['total_cost', 'recommended_price', 'final_price', 'profit'])

const emptyRow = (): RawItem => ({ name: '', unit: '', qty: '', unit_cost: '', ref_price: null })

// Tenderning barcha lotlaridagi tovarlarni bitta ro'yxatga yig'adi.
// MUHIM: `unit_cost` (bizning tannarximiz) BO'SH qoladi — tenderdagi narx
// buyurtmachining narxi, uni tannarx deb olish smetani soxta qilardi.
function positionsFromTender(t: TenderDetail | null): RawItem[] {
  const out: RawItem[] = []
  for (const lot of t?.lots || []) {
    for (const g of lot.goods || []) {
      out.push({
        name: g.name || g.good_code || 'Pozitsiya',
        unit: g.unit || '',
        qty: g.amount ?? '',
        unit_cost: '',
        ref_price: g.price ?? null,
      })
    }
  }
  return out
}

type Params = Omit<CalcInput, 'items' | 'manual_price' | 'budget' | 'budget_currency' | 'min_margin_percent'>

export default function PricingPanel({ tender }: { tender: TenderDetail | null }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)   // oxirgi saqlangan vaqt
  const [error, setError] = useState<string | null>(null)   // server xatosi (hisob emas)
  const [minMargin, setMinMargin] = useState<number | null>(null)

  const [items, setItems] = useState<RawItem[]>([])
  const [p, setP] = useState<Params>({ ...DEFAULTS, currency: '' })
  const [manual, setManual] = useState<string>('')
  const [note, setNote] = useState('')

  // Boshlang'ich yuklash: sozlamalar + shu tender uchun saqlangan smeta.
  // Endpointlar hali ulanmagan bo'lsa (404) — komponent BARIBIR ishlaydi:
  // parametrlar `pricing.ts` dagi DEFAULTS dan, pozitsiyalar tenderdan.
  useEffect(() => {
    if (!open || !tender?.id) return
    let alive = true
    setLoading(true); setError(null)
    Promise.allSettled([
      api.pricingSettings(),
      api.tenderPricing(tender.id),
      // Minimal maqbul foyda — kompaniya profilidan FAQAT O'QILADI.
      api.getProfile(),
    ]).then(([s, saved0, prof]) => {
      if (!alive) return
      const set = s.status === 'fulfilled' && s.value ? s.value : null
      const prev = saved0.status === 'fulfilled' && saved0.value ? saved0.value : null
      const profile = prof.status === 'fulfilled' && prof.value ? prof.value : null
      const inp = prev?.inputs ?? null
      setP({
        markup_percent: inp?.markup_percent ?? set?.markup_percent ?? DEFAULTS.markup_percent,
        risk_reserve_percent: inp?.risk_reserve_percent ?? set?.risk_reserve_percent ?? DEFAULTS.risk_reserve_percent,
        risk_reserve_fixed: inp?.risk_reserve_fixed ?? set?.risk_reserve_fixed ?? DEFAULTS.risk_reserve_fixed,
        logistics_percent: inp?.logistics_percent ?? set?.logistics_percent ?? DEFAULTS.logistics_percent,
        logistics_fixed: inp?.logistics_fixed ?? set?.logistics_fixed ?? DEFAULTS.logistics_fixed,
        vat_percent: inp?.vat_percent ?? set?.vat_percent ?? DEFAULTS.vat_percent,
        currency: inp?.currency ?? tender.currency ?? set?.currency ?? '',
      })
      const rows = inp?.items?.length ? (inp.items as RawItem[]) : positionsFromTender(tender)
      setItems(rows.length ? rows : [emptyRow()])
      setManual(inp?.manual_price != null ? String(inp.manual_price) : '')
      setNote(prev?.note ?? '')
      setMinMargin(profile?.min_margin_percent ?? inp?.min_margin_percent ?? null)
      if (prev?.updated_at) setSaved(prev.updated_at)
    }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [open, tender])

  // HISOB — har renderda, ya'ni har tugmachadan keyin DARHOL. Serverga
  // so'rov yo'q, sahifa qayta yuklanmaydi.
  const inputs = useMemo<CalcInput>(() => ({
    ...p,
    currency: p.currency || null,
    items,
    manual_price: manual === '' ? null : manual,
    budget: tender?.totalcost ?? null,
    budget_currency: tender?.currency ?? null,
    min_margin_percent: minMargin,
  }), [p, items, manual, tender, minMargin])

  const res = useMemo(() => calculate(inputs), [inputs])
  const cur = res.currency || ''

  function setItem(i: number, field: keyof RawItem, value: string) {
    setItems((old) => old.map((it, k) => (k === i ? { ...it, [field]: value } : it)))
    setSaved(null)
  }
  function setParam(field: keyof Params, value: string) {
    setP((old) => ({ ...old, [field]: value }))
    setSaved(null)
  }

  async function save() {
    if (!tender?.id) return
    setSaving(true); setError(null)
    try {
      // `res.inputs` — NORMALLASHTIRILGAN kiruvchi (matnlar songa aylangan,
      // bo'sh qiymatlar null). Xom `inputs` yuborilsa "" kabi qiymatlar
      // serverda 422 berardi. Byudjet va minimal marjani server O'ZI
      // bazadan oladi — mijoz yuborganiga ishonmaydi.
      const out = await api.saveTenderPricing(tender.id, { ...res.inputs, note })
      setSaved(out?.updated_at || new Date().toISOString())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <Button variant="outline" className="mb-4 w-full justify-start" onClick={() => setOpen(true)}
        title="Tannarx, ustama va tavsiya etilgan taklif narxi">
        <Icon name="stats" size={14} />
        Narx hisobi
      </Button>
    )
  }

  return (
    <Card className="mb-4 overflow-hidden">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Icon name="stats" size={14} className="text-primary" />
        <span className="text-[13px] font-semibold">Narx hisobi</span>
        <button
          className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Yopish" onClick={() => setOpen(false)}
        >
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className="space-y-4 p-3">
        {loading && <div className="text-[13px] text-muted-foreground">Yuklanmoqda…</div>}

        {/* ---- POZITSIYALAR ---- */}
        <Section>Pozitsiyalar</Section>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="border-b text-[11px] text-muted-foreground">
                <th className="p-1.5 text-left font-semibold">Nomi</th>
                <th className="w-[86px] p-1.5 text-right font-semibold">Miqdor</th>
                <th className="w-[74px] p-1.5 text-left font-semibold">Birlik</th>
                <th className="w-[110px] p-1.5 text-right font-semibold">Tannarx</th>
                <th className="w-[100px] p-1.5 text-right font-semibold"
                  title="Buyurtmachi e'lon qilgan narx — mo'ljal uchun, hisobga kirmaydi">
                  Tenderda
                </th>
                <th className="w-[110px] p-1.5 text-right font-semibold">Summa</th>
                <th className="w-[30px]" />
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-b border-border-soft">
                  <td className="p-1">
                    <Input className="h-8 text-[12.5px]" value={String(it.name ?? '')}
                      placeholder={`Pozitsiya ${i + 1}`}
                      onChange={(e) => setItem(i, 'name', e.target.value)} />
                  </td>
                  <td className="p-1">
                    <Input className="tabular h-8 text-right text-[12.5px]" type="number" step="any"
                      value={String(it.qty ?? '')}
                      onChange={(e) => setItem(i, 'qty', e.target.value)} />
                  </td>
                  <td className="p-1">
                    <Input className="h-8 text-[12.5px]" value={String(it.unit ?? '')}
                      onChange={(e) => setItem(i, 'unit', e.target.value)} />
                  </td>
                  <td className="p-1">
                    <Input className="tabular h-8 text-right text-[12.5px]" type="number" step="any"
                      value={String(it.unit_cost ?? '')}
                      onChange={(e) => setItem(i, 'unit_cost', e.target.value)} />
                  </td>
                  <td className="tabular p-1.5 text-right text-muted-foreground">
                    {fmtNum(it.ref_price as number | null)}
                  </td>
                  <td className="tabular p-1.5 text-right font-semibold">
                    {fmtNum(res.items[i]?.total)}
                  </td>
                  <td className="p-1">
                    <button
                      className="rounded p-1 text-muted-foreground transition-colors hover:bg-urgent-soft hover:text-urgent"
                      title="O‘chirish"
                      onClick={() => { setItems(items.filter((_, k) => k !== i)); setSaved(null) }}
                    >
                      <Icon name="trash" size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button variant="ghost" size="sm"
          onClick={() => { setItems([...items, emptyRow()]); setSaved(null) }}>
          <Icon name="plus" size={13} /> Pozitsiya qo‘shish
        </Button>

        {/* ---- PARAMETRLAR ---- */}
        <Section>Parametrlar</Section>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Field label="Ustama, %" value={p.markup_percent}
            onChange={(v) => setParam('markup_percent', v)} />
          <Field label="Xavf zaxirasi, %" value={p.risk_reserve_percent}
            onChange={(v) => setParam('risk_reserve_percent', v)} />
          <Field label="Xavf zaxirasi, summa" value={p.risk_reserve_fixed}
            onChange={(v) => setParam('risk_reserve_fixed', v)} />
          <Field label="Logistika, %" value={p.logistics_percent}
            onChange={(v) => setParam('logistics_percent', v)} />
          <Field label="Logistika, summa" value={p.logistics_fixed}
            onChange={(v) => setParam('logistics_fixed', v)} />
          <Field label="QQS, %" value={p.vat_percent}
            onChange={(v) => setParam('vat_percent', v)} />
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-muted-foreground">Valyuta</span>
            <Select value={p.currency || 'none'}
              onValueChange={(v) => setParam('currency', v === 'none' ? '' : v)}>
              <SelectTrigger className="h-8 text-[12.5px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">—</SelectItem>
                <SelectItem value="UZS">UZS</SelectItem>
                <SelectItem value="USD">USD</SelectItem>
              </SelectContent>
            </Select>
          </label>
        </div>

        {/* ---- XATO / OGOHLANTIRISH ---- */}
        {res.errors.map((e) => (
          <div key={e.code}
            className="rounded-md border border-urgent/40 bg-urgent-soft px-3 py-2 text-[12.5px] text-urgent">
            {e.message}
          </div>
        ))}
        {res.warnings.map((w) => (
          <div key={w.code}
            className="rounded-md border border-soon/40 bg-soon-soft px-3 py-2 text-[12.5px] text-soon">
            {w.message}
          </div>
        ))}

        {/* ---- HISOB KETMA-KETLIGI — formulalar ko'rinadi ---- */}
        {res.ok && (
          <>
            <Section>Hisob ketma-ketligi</Section>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <tbody>
                  {res.steps.map((s) => (
                    <tr key={s.key} className={cn(
                      'border-b border-border-soft',
                      KEY_STEPS.has(s.key) && 'bg-muted font-semibold',
                    )}>
                      <td className="p-1.5 align-top">
                        {s.label}
                        <span className="block text-[11px] font-normal text-muted-foreground">
                          {s.rule}
                        </span>
                      </td>
                      <td className="tabular p-1.5 align-top text-[11.5px] text-muted-foreground">
                        {s.formula}
                      </td>
                      <td className="tabular whitespace-nowrap p-1.5 text-right align-top">
                        {PERCENT_STEPS.has(s.key)
                          ? `${fmtNum(s.value)}%`
                          : `${fmtNum(s.value)} ${cur}`.trim()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* ---- BROKER QO'LDA NARX ---- */}
        <Section>Broker narxi</Section>
        <div className="grid gap-2 sm:grid-cols-[1fr_2fr]">
          <label className="block" title="Bo‘sh qoldirilsa tizim tavsiyasi qabul qilinadi">
            <span className="mb-1 block text-[11px] font-semibold text-muted-foreground">
              Qo‘lda narx
            </span>
            <Input className="tabular h-8 text-[12.5px]" type="number" step="any" value={manual}
              placeholder={res.ok ? String(res.totals.recommended_price) : ''}
              onChange={(e) => { setManual(e.target.value); setSaved(null) }} />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-muted-foreground">Izoh</span>
            <Input className="h-8 text-[12.5px]" value={note} placeholder="nega o‘zgartirildi"
              onChange={(e) => { setNote(e.target.value); setSaved(null) }} />
          </label>
        </div>

        {/* ---- YAKUN ---- */}
        {res.ok && (
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
            <Sum label="Jami xarajat" value={`${fmtNum(res.totals.total_cost)} ${cur}`.trim()} />
            <Sum label="Tavsiya" value={`${fmtNum(res.totals.recommended_price)} ${cur}`.trim()} accent />
            <Sum label="Yakuniy narx" value={`${fmtNum(res.totals.final_price)} ${cur}`.trim()}
              hint={res.totals.manual_used ? 'qo‘lda' : 'tavsiya'} />
            <Sum label="Kutilayotgan foyda"
              value={`${fmtNum(res.totals.profit)} ${cur}`.trim()}
              hint={`${fmtNum(res.totals.profit_percent)}%`}
              tone={res.totals.profit > 0 ? 'ok' : res.totals.profit < 0 ? 'bad' : undefined} />
            {res.totals.budget_left !== null && (
              <Sum label="Byudjet zaxirasi"
                value={`${fmtNum(res.totals.budget_left)} ${cur}`.trim()}
                hint={`byudjet ${fmtNum(res.totals.budget)}`}
                tone={res.totals.budget_left < 0 ? 'bad' : 'ok'} />
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t pt-3">
          <Button onClick={save} disabled={saving || !res.ok}>
            {saving ? 'Saqlanmoqda…' : 'Smetani saqlash'}
          </Button>
          {saved && (
            <span className="flex items-center gap-1 text-[12.5px] text-ok">
              <Icon name="check" size={12} /> saqlandi
            </span>
          )}
          {error && <span className="text-[12.5px] text-urgent">{error}</span>}
        </div>
      </div>
    </Card>
  )
}

function Section({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-b pb-1 text-[11px] font-bold text-muted-foreground">
      {children}
    </div>
  )
}

function Field({ label, value, onChange }: {
  label: string
  value: unknown
  onChange: (v: string) => void
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-semibold text-muted-foreground">{label}</span>
      <Input className="tabular h-8 text-[12.5px]" type="number" step="any"
        value={value == null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

function Sum({ label, value, hint, accent, tone }: {
  label: string
  value: string
  hint?: string
  accent?: boolean
  tone?: 'ok' | 'bad'
}) {
  return (
    <div className={cn(
      'rounded-lg border px-3 py-2',
      accent ? 'border-primary bg-secondary' : 'bg-card',
    )}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn(
        'tabular text-[15px] font-bold',
        tone === 'ok' && 'text-ok', tone === 'bad' && 'text-urgent',
        accent && !tone && 'text-primary',
      )}>{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}
