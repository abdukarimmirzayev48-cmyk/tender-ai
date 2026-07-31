// Formatlash yordamchilari (pul, sana, deadline countdown).
import type { Nullable, TenderRow } from './types'

const nf = new Intl.NumberFormat('ru-RU') // bo'shliq bilan ajratadi: 186 374 615 081

type Num = Nullable<number> | undefined

export function money(value: Num, currency?: Nullable<string>): string {
  if (value === null || value === undefined) return '—'
  return `${nf.format(value)} ${currency || ''}`.trim()
}

export function shortMoney(value: Num, currency?: Nullable<string>): string {
  // Katta summalarni qisqartiradi: 186.4 mlrd, 8.6 mln
  if (value === null || value === undefined) return '—'
  const abs = Math.abs(value)
  let out: string
  if (abs >= 1e9) out = (value / 1e9).toFixed(1) + ' mlrd'
  else if (abs >= 1e6) out = (value / 1e6).toFixed(1) + ' mln'
  else if (abs >= 1e3) out = (value / 1e3).toFixed(1) + ' ming'
  else out = nf.format(value)
  return `${out} ${currency || ''}`.trim()
}

export function dateFmt(iso: Nullable<string> | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', {
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
export function agoSec(sec: Num): string {
  if (sec == null) return '—'
  if (sec < 60) return 'hozirgina'
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m} daqiqa oldin`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} soat oldin`
  const d = Math.floor(h / 24)
  return `${d} kun oldin`
}

export function ago(iso: Nullable<string> | undefined): string {
  if (!iso) return '—'
  return agoSec((Date.now() - new Date(iso).getTime()) / 1000)
}

export type DeadlineLevel = 'none' | 'expired' | 'urgent' | 'soon' | 'ok'

export interface DeadlineInfo {
  text: string
  short: string
  level: DeadlineLevel
}

// Deadline holati: close_at ga nisbatan qancha vaqt qolgani + rang darajasi
export function deadline(iso: Nullable<string> | undefined): DeadlineInfo {
  if (!iso) return { text: '—', short: '—', level: 'none' }
  const now = new Date()
  const end = new Date(iso)
  const ms = end.getTime() - now.getTime()
  if (ms <= 0) return { text: 'Muddati o‘tgan', short: 'o‘tgan', level: 'expired' }

  const hours = ms / 36e5
  const days = Math.floor(hours / 24)
  let text: string, short: string
  if (days >= 1) { text = `${days} kun qoldi`; short = `${days} kun` }
  else { const h = Math.floor(hours); text = `${h} soat qoldi`; short = `${h} soat` }

  let level: DeadlineLevel = 'ok'
  if (hours < 24) level = 'urgent'      // 1 kundan kam — qizil
  else if (days < 3) level = 'soon'     // 3 kundan kam — sariq
  return { text, short, level }
}

/** Deadline darajasi -> Tailwind sinflari. Ilgari bu `deadline--<level>` CSS
 *  sinflari orqali edi; Tailwind'da sinf nomlari DINAMIK QURILMAYDI (JIT ularni
 *  topa olmaydi), shuning uchun to'liq sinflar shu jadvalda yozilgan. */
export const DEADLINE_CLASS: Record<DeadlineLevel, string> = {
  none: 'bg-muted text-muted-foreground',
  ok: 'bg-ok-soft text-ok',
  soon: 'bg-soon-soft text-soon',
  urgent: 'bg-urgent-soft text-urgent',
  expired: 'bg-muted text-muted-foreground line-through',
}
