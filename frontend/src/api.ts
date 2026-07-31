// Backend API qatlami — barcha so'rovlar shu yerdan o'tadi.
// Bazaviy manzil .env dagi VITE_API_BASE dan (default localhost:8000).
import type {
  AiMatchResult, Category, CompanyDocument, CompanyProfileData, ComplianceResult,
  DocumentTextResult, DocumentType, Freshness, GoNoGoResult, Paged, PricingInputs,
  PricingSaved, Product, ProductSuggestion, Region, SavedSearch, Stats, Status,
  StockCheckResult, TelegramBot, TelegramLink, TelegramLinkStatus,
  TelegramSubscriber, TenderDetail, TenderRow, NotifySettingsData, Nullable,
} from './types'

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Nisbiy havolalarni (masalan fayl yuklab olish proksisi) to'liq manzilga aylantiradi
export const apiUrl = (path?: string): string =>
  path?.startsWith('/') ? BASE + path : (path ?? '')

/** FastAPI 422 validatsiya xatosining bir elementi */
interface ValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

// FastAPI xato tanasini o'qiladigan matnga aylantiradi.
// 400 -> detail satr; 422 (validatsiya) -> detail MASSIV: [{loc, msg}, ...].
// Massivni to'g'ridan-to'g'ri satrga qo'shsak "[object Object]" chiqadi va
// foydalanuvchi qaysi maydon xato ekanini bilmaydi.
export function errMatn(detail: unknown): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return String(detail)
  return (detail as ValidationIssue[]).map((e) => {
    const maydon = (e.loc || []).filter((x) => x !== 'body').join('.')
    const msg = String(e.msg || '').replace(/^Value error,\s*/, '')
    return maydon ? `${maydon}: ${msg}` : msg
  }).join('; ')
}

type Params = Record<string, string | number | boolean | string[] | null | undefined>

interface RequestOpts {
  params?: Params
  body?: unknown
}

async function request<T>(
  method: string, path: string, { params, body }: RequestOpts = {},
): Promise<T> {
  const url = new URL(BASE + path)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue
      // Massiv -> takrorlanuvchi parametr (?product=a&product=b), chunki
      // FastAPI List[str] ni shunday kutadi. set() bo'lsa vergul bilan
      // birlashib bitta qatorga aylanib qolardi.
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x))
      else url.searchParams.set(k, String(v))
    }
  }
  const opts: RequestInit = { method }
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const b = await res.json()
      detail = errMatn(b.detail) || b.error || detail
    } catch { /* JSON emas */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  // 204 No Content — TANA BO'SH. DELETE va /catalog/seen shunday javob beradi.
  // Shartsiz res.json() chaqirilsa bu yerda SyntaxError chiqadi va chaqiruvchi
  // muvaffaqiyatli amalni XATO deb qabul qiladi: o'chirish serverda bajarilib,
  // interfeys yangilanmay qolardi.
  if (res.status === 204) return null as T
  const text = await res.text()
  return (text ? JSON.parse(text) : null) as T
}

export const api = {
  tenders: (params?: Params) => request<Paged<TenderRow>>('GET', '/tenders', { params }),
  tender: (id: number) => request<TenderDetail>('GET', `/tenders/${id}`),
  stats: (params?: Params) => request<Stats>('GET', '/stats', { params }),
  regions: (params?: Params) => request<Region[]>('GET', '/regions', { params }),
  statuses: () => request<Status[]>('GET', '/statuses'),
  categories: () => request<Category[]>('GET', '/categories'),
  freshness: () => request<Freshness>('GET', '/freshness'),
  // Mahsulot bo'yicha filtr uchun takliflar (tenderlardagi haqiqiy tovar nomlari)
  products: (params?: Params) => request<ProductSuggestion[]>('GET', '/products', { params }),
  // AI moslik tahlili — tender katalogga mos keladimi (natija backendда keshlanadi)
  aiMatch: (id: number, params?: Params) =>
    request<AiMatchResult>('POST', `/tenders/${id}/ai-match`, { params }),
  // AI Go/No-Go tavsiyasi — qatnashish kerakmi (11 mezon)
  aiGoNogo: (id: number, params?: Params) =>
    request<GoNoGoResult>('POST', `/tenders/${id}/ai-gonogo`, { params }),

  // --- P0-2: hujjat matni holati (deterministik parserlar, AI emas) ---
  documentsText: (id: number) =>
    request<DocumentTextResult>('GET', `/tenders/${id}/documents/text`),

  // --- P0-6: ombor qoldig'ini tekshirish (mos pozitsiyalar bo'yicha) ---
  stockCheck: (id: number) => request<StockCheckResult>('GET', `/tenders/${id}/stock-check`),

  // --- P0-7: narx hisobi (sof formula) ---
  pricingSettings: () => request<Partial<PricingInputs>>('GET', '/pricing/settings'),
  savePricingSettings: (body: unknown) => request<unknown>('PUT', '/pricing/settings', { body }),
  tenderPricing: (id: number) => request<Nullable<PricingSaved>>('GET', `/tenders/${id}/pricing`),
  saveTenderPricing: (id: number, body: unknown) =>
    request<PricingSaved>('POST', `/tenders/${id}/pricing`, { body }),

  // --- P0-8: hujjatlar to'liqligi cheklisti ---
  compliance: (id: number) => request<ComplianceResult>('GET', `/tenders/${id}/compliance`),
  documentTypes: () => request<DocumentType[]>('GET', '/company/document-types'),
  companyDocuments: () => request<CompanyDocument[]>('GET', '/company/documents'),
  createCompanyDocument: (body: unknown) =>
    request<CompanyDocument>('POST', '/company/documents', { body }),
  updateCompanyDocument: (id: number, body: unknown) =>
    request<CompanyDocument>('PUT', `/company/documents/${id}`, { body }),
  deleteCompanyDocument: (id: number) =>
    request<null>('DELETE', `/company/documents/${id}`),

  // --- P0-10: bildirishnoma (email + Telegram) ---
  notifySettings: () => request<NotifySettingsData>('GET', '/notify/settings'),
  saveNotifySettings: (body: unknown) =>
    request<NotifySettingsData>('PUT', '/notify/settings', { body }),
  notifyTest: () => request<{ sent: boolean; to: string }>('POST', '/notify/test'),
  // Telegram: bot kim, obunachilar, sinov xabari.
  // BOT TOKENI bu yerdan HECH QACHON o'tmaydi — u serverdagi .env da.
  telegramBot: () => request<TelegramBot>('GET', '/notify/telegram/bot'),
  // Obunachi = botga /start bosgan suhbat. Ro'yxatni server yuritadi.
  telegramSubscribers: () =>
    request<{ subscribers: TelegramSubscriber[]; ready: boolean }>(
      'GET', '/notify/telegram/subscribers'),
  // ULASH: bir martalik havola yaratadi (https://t.me/<bot>?start=<token>)
  telegramCreateLink: () => request<TelegramLink>('POST', '/notify/telegram/link'),
  // Havola bosildimi — interfeys qisqa oraliqda shuni so'rab turadi
  telegramLinkStatus: (token: string) =>
    request<TelegramLinkStatus>(
      'GET', `/notify/telegram/link/${encodeURIComponent(token)}`),
  telegramSetSubscriber: (chatId: string, enabled: boolean) =>
    request<{ subscribers: TelegramSubscriber[] }>(
      'PUT', `/notify/telegram/subscribers/${encodeURIComponent(chatId)}`,
      { body: { enabled } }),
  telegramDeleteSubscriber: (chatId: string) =>
    request<{ subscribers: TelegramSubscriber[] }>(
      'DELETE', `/notify/telegram/subscribers/${encodeURIComponent(chatId)}`),
  telegramTest: (chatId?: string) =>
    request<{ sent: boolean; chats: string[]; errors: { chat_id: string; error: string }[] }>(
      'POST', '/notify/telegram/test', { params: { chat_id: chatId } }),

  // Aqlli moslashtirish
  getProfile: () => request<Nullable<CompanyProfileData>>('GET', '/profile'),
  saveProfile: (body: unknown) => request<CompanyProfileData>('PUT', '/profile', { body }),
  match: (body: unknown) => request<Paged<TenderRow>>('POST', '/match', { body }),

  // Saqlangan qidiruvlar (A bosqich)
  searches: () => request<SavedSearch[]>('GET', '/searches'),
  createSearch: (body: unknown) => request<SavedSearch>('POST', '/searches', { body }),
  updateSearch: (id: number, body: unknown) =>
    request<SavedSearch>('PUT', `/searches/${id}`, { body }),
  deleteSearch: (id: number) => request<null>('DELETE', `/searches/${id}`),

  // Mahsulot katalogi + katalog-asosli moslik
  catalog: () => request<Product[]>('GET', '/catalog'),
  createProduct: (body: unknown) => request<Product>('POST', '/catalog', { body }),
  updateProduct: (id: number, body: unknown) => request<Product>('PUT', `/catalog/${id}`, { body }),
  deleteProduct: (id: number) => request<null>('DELETE', `/catalog/${id}`),
  catalogMatch: (body: unknown) => request<Paged<TenderRow>>('POST', '/catalog/match', { body }),
  catalogNewCount: () => request<{ new: number; total: number }>('GET', '/catalog/new-count'),
  catalogSeen: () => request<null>('POST', '/catalog/seen'),
}
