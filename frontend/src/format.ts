// Formatlash yordamchilari (pul, sana, deadline countdown).
//
// TILGA BOG'LIQ. "mlrd", "3 kun qoldi", "hozirgina" — bularning hammasi
// tarjima qilinadi, sonlar va sanalar esa tanlangan lokalga qarab
// formatlanadi (rus tilida "186 374 615", ingliz tilida "186,374,615").
//
// SHUNING UCHUN BU FUNKSIYALAR `t` VA `locale` NI PARAMETR SIFATIDA OLADI,
// modul darajasidagi "joriy til" o'zgaruvchisi EMAS. Sabab: React
// komponenti modul o'zgaruvchisiga obuna bo'lolmaydi — til almashtirilganda
// faqat `useT()` chaqirganlar qayta chizilardi, jadvaldagi summalar esa eski
// tilda qotib qolardi. Komponentlar `useFormat()` hookini chaqiradi, u esa
// kontekstga obuna bo'ladi va til o'zgarishi bilan hammasi yangilanadi.
import { useMemo } from 'react'
import { useI18n } from './i18n'
import type { TKey, TVars } from './i18n'
import type { Nullable, TenderRow } from './types'

type Num = Nullable<number> | undefined
type T = (key: TKey, vars?: TVars) => string

export function money(value: Num, currency: Nullable<string> | undefined,
                      locale: string): string {
  if (value === null || value === undefined) return '—'
  return `${new Intl.NumberFormat(locale).format(value)} ${currency || ''}`.trim()
}

export function shortMoney(value: Num, currency: Nullable<string> | undefined,
                           t: T, locale: string): string {
  // Katta summalarni qisqartiradi: 186.4 mlrd, 8.6 mln
  if (value === null || value === undefined) return '—'
  const abs = Math.abs(value)
  let out: string
  if (abs >= 1e9) out = (value / 1e9).toFixed(1) + ' ' + t('fmt.bln')
  else if (abs >= 1e6) out = (value / 1e6).toFixed(1) + ' ' + t('fmt.mln')
  else if (abs >= 1e3) out = (value / 1e3).toFixed(1) + ' ' + t('fmt.thousand')
  else out = new Intl.NumberFormat(locale).format(value)
  return `${out} ${currency || ''}`.trim()
}

export function dateFmt(iso: Nullable<string> | undefined, locale: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(locale, {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// Fayl hajmi — o'qiladigan ko'rinishda
export function fileSize(bytes: Num): string {
  if (!bytes) return '—'
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB'
  return bytes + ' B'
}

// Tenderning MANBA platformadagi rasmiy sahifasi.
// Hujjatlar (texnik topshiriq, xarid hujjatlari, malaka talablari) ommaviy
// API'da yo'q — faqat shu sahifada. Kelajakda har platforma o'z naqshini oladi.
const SOURCE_URLS: Record<string, (id: number) => string> = {
  'xt-xarid': (id) => `https://xt-xarid.uz/procedure/${id}/core`,
  'uzex': (id) => `https://etender.uzex.uz/lot/${id}`,
}

// MUHIM: manbadagi ASL id (source_id) ishlatiladi — bizning t.id global
// (source_id + platforma ofseti), u manba saytida mavjud emas.
export function sourceUrl(t?: Pick<TenderRow, 'id' | 'source_id' | 'source_platform'>):
  Nullable<string> {
  const sid = t?.source_id ?? t?.id
  if (!sid) return null
  const fn = SOURCE_URLS[t?.source_platform || 'xt-xarid']
  return fn ? fn(sid) : null
}

// "N daqiqa/soat/kun oldin" — nisbiy vaqt (o'tган vaqt uchun)
export function agoSec(sec: Num, t: T): string {
  if (sec == null) return '—'
  if (sec < 60) return t('fmt.justNow')
  const m = Math.floor(sec / 60)
  if (m < 60) return t('fmt.minAgo', { n: m })
  const h = Math.floor(m / 60)
  if (h < 24) return t('fmt.hourAgo', { n: h })
  return t('fmt.dayAgo', { n: Math.floor(h / 24) })
}

export function ago(iso: Nullable<string> | undefined, t: T): string {
  if (!iso) return '—'
  return agoSec((Date.now() - new Date(iso).getTime()) / 1000, t)
}

export type DeadlineLevel = 'none' | 'expired' | 'urgent' | 'soon' | 'ok'

export interface DeadlineInfo {
  text: string
  short: string
  level: DeadlineLevel
}

// Deadline holati: close_at ga nisbatan qancha vaqt qolgani + rang darajasi
export function deadline(iso: Nullable<string> | undefined, t: T): DeadlineInfo {
  if (!iso) return { text: '—', short: '—', level: 'none' }
  const ms = new Date(iso).getTime() - Date.now()
  if (ms <= 0) {
    return { text: t('fmt.expired'), short: t('fmt.expiredShort'), level: 'expired' }
  }

  const hours = ms / 36e5
  const days = Math.floor(hours / 24)
  let text: string, short: string
  if (days >= 1) {
    text = t('fmt.daysLeft', { n: days }); short = t('fmt.daysShort', { n: days })
  } else {
    const h = Math.floor(hours)
    text = t('fmt.hoursLeft', { n: h }); short = t('fmt.hoursShort', { n: h })
  }

  let level: DeadlineLevel = 'ok'
  if (hours < 24) level = 'urgent'      // 1 kundan kam — qizil
  else if (days < 3) level = 'soon'     // 3 kundan kam — sariq
  return { text, short, level }
}

/**
 * Tilga bog'langan formatlash to'plami.
 *
 * Komponentlar `const f = useFormat()` deb oladi va `f.money(...)` deb
 * chaqiradi. Hook `useI18n()` orqali kontekstga OBUNA bo'ladi — til
 * almashtirilganda komponent qayta chiziladi va sonlar ham, so'zlar ham
 * yangi tilga o'tadi.
 */
export function useFormat() {
  const { t, locale } = useI18n()
  return useMemo(() => ({
    money: (v: Num, c?: Nullable<string>) => money(v, c, locale),
    shortMoney: (v: Num, c?: Nullable<string>) => shortMoney(v, c, t, locale),
    dateFmt: (iso: Nullable<string> | undefined) => dateFmt(iso, locale),
    num: (v: Num) => (v == null ? '—' : new Intl.NumberFormat(locale).format(v)),
    fileSize,
    agoSec: (s: Num) => agoSec(s, t),
    ago: (iso: Nullable<string> | undefined) => ago(iso, t),
    deadline: (iso: Nullable<string> | undefined) => deadline(iso, t),
    locale,
  }), [t, locale])
}

/** Deadline darajasi -> Tailwind sinflari. Ilgari bu `deadline--<level>` CSS
 *  sinflari orqali edi; Tailwind'da sinf nomlari DINAMIK QURILMAYDI (JIT ularni
 *  topa olmaydi), shuning uchun to'liq sinflar shu jadvalda yozilgan. */
export const DEADLINE_CLASS: Record<DeadlineLevel, string> = {
  none: 'bg-muted text-muted-foreground',
  ok: 'bg-ok-soft text-ok-strong',
  soon: 'bg-soon-soft text-soon-strong',
  urgent: 'bg-urgent-soft text-urgent-strong',
  expired: 'bg-muted text-muted-foreground line-through',
}
