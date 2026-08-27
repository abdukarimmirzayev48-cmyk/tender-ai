// NARX HISOBI — `api/pricing.py` ning AYNAN NUSXASI (brauzer uchun)
// =================================================================
// NEGA IKKI NUSXA: TZ talab qiladi — "kiruvchi parametrlar o'zgarganda hisob
// SAHIFANI QAYTA YUKLAMASDAN qayta hisoblanadi". Har tugmachada serverga
// so'rov yuborish sezilarli kechikish beradi va offline ishlamaydi, shuning
// uchun hisob brauzerda ham bajariladi. Server esa yakuniy manba bo'lib
// qoladi: SAQLASHda natijani u qayta hisoblaydi.
//
// IKKI MANBA CHETGA CHIQMASLIGI UCHUN:
//   - kiruvchi/chiquvchi obyekt shakli bir xil,
//   - arifmetika bir xil (float64 — Python floati ham IEEE 754 double),
//   - yaxlitlash funksiyasi bir xil (round2 pastda).
// `_tests/pricing_test.py` shu faylni Node bilan ishga tushirib, Python
// natijasi bilan AYNAN solishtiradi. Formulani o'zgartirsangiz —
// `api/pricing.py` ni ham o'zgartiring, aks holda sinov yiqiladi.
//
// TYPESCRIPT ESLATMASI: bu fayl Node tomonidan TO'G'RIDAN-TO'G'RI import
// qilinadi (sinov harnessi orqali), shuning uchun unda FAQAT "o'chiriladigan"
// TS sintaksisi bo'lishi kerak — interfeys va tur izohlari. `enum`, `namespace`
// yoki konstruktor parametr-xossalari kod generatsiyasini talab qiladi va
// Node'ning tur-tozalash rejimida YIQILADI.
//
// To'liq izohlar (formula tarkibi, yaxlitlash qoidasi, valyuta cheklovi,
// "foyda" atamasining ikki ma'nosi) `api/pricing.py` docstringida.

export const DEFAULTS = {
  markup_percent: 15,
  risk_reserve_percent: 5,
  risk_reserve_fixed: 0,
  logistics_percent: 0,
  logistics_fixed: 0,
  vat_percent: 12,
}

const MAX_FORMULA_ITEMS = 4

/** Kiruvchi qiymat: forma inputidan matn, bazadan son, bo'sh maydondan null */
export type Raw = number | string | null | undefined

export interface RawItem {
  name?: string | null
  unit?: string | null
  qty?: Raw
  unit_cost?: Raw
  currency?: string | null
  ref_price?: Raw
}

export interface CalcInput {
  currency?: string | null
  items?: (RawItem | null)[]
  markup_percent?: Raw
  risk_reserve_percent?: Raw
  risk_reserve_fixed?: Raw
  logistics_percent?: Raw
  logistics_fixed?: Raw
  vat_percent?: Raw
  manual_price?: Raw
  budget?: Raw
  budget_currency?: string | null
  min_margin_percent?: Raw
}

import type { TKey, TVars } from './i18n'

/** Tarjima funksiyasi — `useI18n().t`. */
export type T = (key: TKey, vars?: TVars) => string

export interface CalcItem {
  name: string
  unit: string | null
  qty: number
  unit_cost: number
  currency: string | null
  ref_price: number | null
  total: number
}

export interface CalcStep {
  key: string
  label: string
  rule: string
  formula: string
  value: number
}

export interface CalcMessage {
  code: string
  message: string
}

export interface CalcTotals {
  cost_base: number
  logistics: number
  risk_reserve: number
  total_cost: number
  markup: number
  price_ex_vat: number
  vat: number
  recommended_price: number
  manual_price: number | null
  manual_used: boolean
  final_price: number
  final_ex_vat: number
  profit: number
  profit_percent: number
  budget: number | null
  budget_left: number | null
  budget_ratio_percent: number | null
}

export interface CalcNormalized {
  currency: string | null
  items: CalcItem[]
  markup_percent: number
  risk_reserve_percent: number
  risk_reserve_fixed: number
  logistics_percent: number
  logistics_fixed: number
  vat_percent: number
  manual_price: number | null
  budget: number | null
  budget_currency: string | null
  min_margin_percent: number | null
}

export interface CalcResult {
  ok: boolean
  currency: string | null
  items: CalcItem[]
  steps: CalcStep[]
  totals: CalcTotals
  warnings: CalcMessage[]
  errors: CalcMessage[]
  inputs: CalcNormalized
}

// 2 kasrgacha, noldan uzoqlashtirib (half-up). Math.round(v) === floor(v+0.5),
// Pythonda ham math.floor(v + 0.5) — natija bir xil.
// 1e-9: ikkilik kasr xatosini tuzatadi (1.005*100 = 100.49999999999999).
export function round2(x: number): number {
  if (!Number.isFinite(x)) return 0
  const sign = x < 0 ? -1 : 1
  const v = Math.abs(x) * 100
  const r = Math.floor(v + 1e-9 + 0.5)
  const out = (sign * r) / 100
  return out === 0 ? 0 : out
}

// Har qanday kiruvchi -> son. Bo'sh/xato bo'lsa default.
// Inputdan matn keladi ("15", "15,5") — vergul ham qabul qilinadi.
function num(v: Raw | boolean, dflt = 0): number {
  if (v === null || v === undefined || v === '') return dflt
  if (typeof v === 'boolean') return dflt
  if (typeof v === 'string') {
    const s = v.trim().replace(/\s/g, '').replace(',', '.')
    const n = Number(s)
    return Number.isFinite(n) ? n : dflt
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : dflt
}

// Formuladagi son: ortiqcha nollarsiz ("650", "6.67", "1000.5")
function fmt(x: number): string {
  let s = round2(x).toFixed(2)
  if (s.endsWith('.00')) s = s.slice(0, -3)
  else if (s.endsWith('0')) s = s.slice(0, -1)
  return s
}

// Bosqich matnlari tilga bog'liq, lekin HISOB emas — shuning uchun `t`
// modulga PARAMETR sifatida kiradi (`calculate(inp, t)`). Modul darajasidagi
// "joriy til" o'zgaruvchisi bo'lganda funksiya sof bo'lmasdi va uni tilsiz
// sinash ham qiyinlashardi.
const step = (t: T, key: string, formula: string, value: number): CalcStep => ({
  key,
  label: t(`prc.s.${key}` as TKey),
  rule: t(`prc.r.${key}` as TKey),
  formula,
  value: round2(value),
})
const msg = (code: string, message: string): CalcMessage => ({ code, message })

function emptyTotals(): CalcTotals {
  return {
    cost_base: 0, logistics: 0, risk_reserve: 0, total_cost: 0, markup: 0,
    price_ex_vat: 0, vat: 0, recommended_price: 0, manual_price: null,
    manual_used: false, final_price: 0, final_ex_vat: 0, profit: 0,
    profit_percent: 0, budget: null, budget_left: null,
    budget_ratio_percent: null,
  }
}

export function calculate(inp: CalcInput = {}, t: T): CalcResult {
  inp = inp || {}
  const errors: CalcMessage[] = []
  const warnings: CalcMessage[] = []

  const currency = String(inp.currency || '').trim().toUpperCase() || null

  // --- 1. Pozitsiyalar ---
  const items: CalcItem[] = []
  const seen: string[] = []
  ;(inp.items || []).forEach((raw0, i) => {
    const raw = raw0 || {}
    const qty = num(raw.qty)
    const unitCost = num(raw.unit_cost)
    const cur = String(raw.currency || '').trim().toUpperCase() || null
    const name = raw.name || t('prc.item', { n: i + 1 })
    if (cur && !seen.includes(cur)) seen.push(cur)
    if (qty < 0) {
      errors.push(msg('qty_negative',
        t('prc.err.qtyNegative', { name, v: fmt(qty) })))
    }
    if (unitCost < 0) {
      errors.push(msg('cost_negative',
        t('prc.err.costNegative', { name, v: fmt(unitCost) })))
    }
    items.push({
      name,
      unit: raw.unit || null,
      qty,
      unit_cost: unitCost,
      currency: cur,
      ref_price: (raw.ref_price === null || raw.ref_price === undefined || raw.ref_price === '')
        ? null : round2(num(raw.ref_price)),
      total: round2(qty * unitCost),
    })
  })

  // --- 2. Valyuta nazorati ---
  if (seen.length > 1 || (currency && seen.length > 0 && seen.some((c) => c !== currency))) {
    const all = Array.from(new Set(currency ? seen.concat([currency]) : seen)).sort()
    errors.push(msg('currency_mix',
      t('prc.err.currencyMix', { list: all.join(', ') })))
  }

  // --- 3. Parametrlar ---
  const markup = num(inp.markup_percent, DEFAULTS.markup_percent)
  const riskPct = num(inp.risk_reserve_percent, DEFAULTS.risk_reserve_percent)
  const riskFix = num(inp.risk_reserve_fixed, DEFAULTS.risk_reserve_fixed)
  const logPct = num(inp.logistics_percent, DEFAULTS.logistics_percent)
  const logFix = num(inp.logistics_fixed, DEFAULTS.logistics_fixed)
  const vat = num(inp.vat_percent, DEFAULTS.vat_percent)

  const checks: [string, number, TKey][] = [
    ['markup_percent', markup, 'prc.p.markup'],
    ['risk_reserve_percent', riskPct, 'prc.p.riskPct'],
    ['risk_reserve_fixed', riskFix, 'prc.p.riskFixed'],
    ['logistics_percent', logPct, 'prc.p.logiPct'],
    ['logistics_fixed', logFix, 'prc.p.logiFixed'],
    ['vat_percent', vat, 'prc.p.vat'],
  ]
  for (const [key, val, label] of checks) {
    if (val < 0) {
      errors.push(msg(`${key}_negative`,
        t('prc.err.paramNegative', { label: t(label), v: fmt(val) })))
    }
  }
  if (vat > 100) {
    errors.push(msg('vat_range', t('prc.err.vatRange', { v: fmt(vat) })))
  }

  let manual: number | null = null
  if (inp.manual_price !== null && inp.manual_price !== undefined && inp.manual_price !== '') {
    manual = round2(num(inp.manual_price))
    if (manual < 0) {
      errors.push(msg('manual_negative',
        t('prc.err.manualNegative', { v: fmt(manual) })))
    }
  }

  const budget = (inp.budget === null || inp.budget === undefined || inp.budget === '')
    ? null : round2(num(inp.budget))
  const budgetCurrency = String(inp.budget_currency || '').trim().toUpperCase() || null
  const minMargin = (inp.min_margin_percent === null || inp.min_margin_percent === undefined
    || inp.min_margin_percent === '') ? null : num(inp.min_margin_percent)

  const normalized: CalcNormalized = {
    currency, items,
    markup_percent: markup, risk_reserve_percent: riskPct,
    risk_reserve_fixed: riskFix, logistics_percent: logPct,
    logistics_fixed: logFix, vat_percent: vat,
    manual_price: manual, budget, budget_currency: budgetCurrency,
    min_margin_percent: minMargin,
  }

  if (errors.length) {
    return {
      ok: false, currency, items, steps: [], totals: emptyTotals(),
      warnings, errors, inputs: normalized,
    }
  }

  if (!items.length) {
    warnings.push(msg('no_items', t('prc.warn.noItems')))
  }

  // --- 4. Bosqichlar ---
  const steps: CalcStep[] = []

  const costBase = round2(items.reduce((a, it) => a + it.total, 0))
  const parts = items.slice(0, MAX_FORMULA_ITEMS)
    .map((it) => `${fmt(it.qty)} × ${fmt(it.unit_cost)}`)
  if (items.length > MAX_FORMULA_ITEMS) {
    parts.push(t('prc.f.more', { n: items.length - MAX_FORMULA_ITEMS }))
  }
  steps.push(step(t, 'cost_base', parts.length ? parts.join(' + ') : '0', costBase))

  const logistics = round2((costBase * logPct) / 100 + logFix)
  steps.push(step(t, 'logistics',
    `${fmt(costBase)} × ${fmt(logPct)}% + ${fmt(logFix)}`, logistics))

  const riskBase = round2(costBase + logistics)
  const risk = round2((riskBase * riskPct) / 100 + riskFix)
  steps.push(step(t, 'risk_reserve',
    `(${fmt(costBase)} + ${fmt(logistics)}) × ${fmt(riskPct)}% + ${fmt(riskFix)}`, risk))

  const totalCost = round2(costBase + logistics + risk)
  steps.push(step(t, 'total_cost',
    `${fmt(costBase)} + ${fmt(logistics)} + ${fmt(risk)}`, totalCost))

  const markupSum = round2((totalCost * markup) / 100)
  steps.push(step(t, 'markup', `${fmt(totalCost)} × ${fmt(markup)}%`, markupSum))

  const priceExVat = round2(totalCost + markupSum)
  steps.push(step(t, 'price_ex_vat',
    `${fmt(totalCost)} + ${fmt(markupSum)}`, priceExVat))

  const vatSum = round2((priceExVat * vat) / 100)
  steps.push(step(t, 'vat', `${fmt(priceExVat)} × ${fmt(vat)}%`, vatSum))

  const recommended = round2(priceExVat + vatSum)
  steps.push(step(t, 'recommended_price',
    `${fmt(priceExVat)} + ${fmt(vatSum)}`, recommended))

  const manualUsed = manual !== null
  const finalPrice = manualUsed ? manual! : recommended
  steps.push(step(t, 'final_price',
    t(manualUsed ? 'prc.f.manual' : 'prc.f.recommended', { v: fmt(finalPrice) }),
    finalPrice))

  const finalExVat = round2(finalPrice / (1 + vat / 100))
  steps.push(step(t, 'final_ex_vat',
    `${fmt(finalPrice)} ÷ (1 + ${fmt(vat)}%)`, finalExVat))

  const profit = round2(finalExVat - totalCost)
  steps.push(step(t, 'profit', `${fmt(finalExVat)} − ${fmt(totalCost)}`, profit))

  const profitPercent = finalExVat ? round2((profit / finalExVat) * 100) : 0
  steps.push(step(t, 'profit_percent',
    finalExVat ? `${fmt(profit)} ÷ ${fmt(finalExVat)} × 100` : t('prc.f.zeroPrice'),
    profitPercent))

  // --- 5. Byudjetga nisbat ---
  let budgetLeft: number | null = null
  let budgetRatio: number | null = null
  let comparable = budget !== null
  if (budget !== null && budgetCurrency && currency && budgetCurrency !== currency) {
    comparable = false
    warnings.push(msg('budget_currency',
      t('prc.warn.budgetCurrency', { bcur: budgetCurrency, cur: currency })))
  }
  if (comparable && budget !== null) {
    budgetLeft = round2(budget - finalPrice)
    steps.push(step(t, 'budget_left',
      `${fmt(budget)} − ${fmt(finalPrice)}`, budgetLeft))
    budgetRatio = budget ? round2((finalPrice / budget) * 100) : 0
    steps.push(step(t, 'budget_ratio',
      budget ? `${fmt(finalPrice)} ÷ ${fmt(budget)} × 100` : t('prc.f.zeroBudget'),
      budgetRatio))
    if (budgetLeft < 0) {
      warnings.push(msg('over_budget',
        t('prc.warn.overBudget', { v: fmt(Math.abs(budgetLeft)), cur: currency || '' })
          .replace(/ {2}/g, ' ')))
    }
  }

  // --- 6. Ogohlantirishlar ---
  if (profit < 0) {
    warnings.push(msg('loss',
      t('prc.warn.loss', { v: fmt(profit), cur: currency || '' }).replace(/ {2}/g, ' ')))
  } else if (profit === 0) {
    warnings.push(msg('zero_profit', t('prc.warn.zeroProfit')))
  }
  if (minMargin !== null && profitPercent < minMargin) {
    warnings.push(msg('below_min_margin',
      t('prc.warn.belowMinMargin', { v: fmt(profitPercent), min: fmt(minMargin) })))
  }

  const totals: CalcTotals = {
    cost_base: costBase,
    logistics,
    risk_reserve: risk,
    total_cost: totalCost,
    markup: markupSum,
    price_ex_vat: priceExVat,
    vat: vatSum,
    recommended_price: recommended,
    manual_price: manual,
    manual_used: manualUsed,
    final_price: finalPrice,
    final_ex_vat: finalExVat,
    profit,
    profit_percent: profitPercent,
    budget,
    budget_left: budgetLeft,
    budget_ratio_percent: budgetRatio,
  }
  return { ok: true, currency, items, steps, totals, warnings, errors, inputs: normalized }
}
