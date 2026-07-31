// Backend javoblarining turlari.
//
// MANBA: `api/queries.py` SELECT'lari va `api/main.py` javob modellari.
// Bu yerda FAQAT interfeys ko'rinishida yozilgan — hech qanday mantiq yo'q,
// shuning uchun backend maydonni o'zgartirsa, xato KOMPILYATSIYA paytida
// chiqadi, foydalanuvchi ekranida "undefined" bo'lib emas.
//
// Ixtiyoriy (`?`) va `| null` farqi ataylab: `?` — maydon javobda BO'LMASLIGI
// mumkin (endpointga qarab), `| null` — maydon bor, lekin qiymati bo'sh.

export type Nullable<T> = T | null

// --- umumiy ---------------------------------------------------------------
export interface Paged<T> {
  items: T[]
  total: number
}

export interface Region {
  area_id: string
  name: Nullable<string>
  level: number
}

export interface Status {
  status_code: string
  name: Nullable<string>
}

export interface Category {
  code: string
  name: string
  /** Shu kategoriyadagi tenderlar soni (filtr ro'yxatida ko'rsatiladi) */
  count?: number
  children: Category[]
}

// --- tender ---------------------------------------------------------------
export interface LotSummary {
  lot_id: number
  title: Nullable<string>
  total_sum_lot: Nullable<number>
  item_count: Nullable<number>
  delivery_period: Nullable<number>
  guarantee: Nullable<number>
}

export interface Good {
  good_code: string
  name: Nullable<string>
  unit: Nullable<string>
  amount: Nullable<number>
  price: Nullable<number>
}

export interface LotItemProperty {
  prop_name: string
  val_name: string | number
}

export interface LotItem {
  item_id: number
  name: Nullable<string>
  product_code: Nullable<string>
  delivery_period: Nullable<number>
  guarantee: Nullable<number>
  prod_year: Nullable<number>
  spec: Nullable<string>
  properties?: LotItemProperty[]
}

export interface Lot {
  lot_id: number
  title: Nullable<string>
  total_sum_lot: Nullable<number>
  goods?: Good[]
  items?: LotItem[]
}

/** Moslik balli — ikki manbadan keladi: katalog va saqlangan qidiruv.
 *  Shuning uchun maydonlar IXTIYORIY (manbaga qarab to'plam farq qiladi). */
export interface MatchInfo {
  score?: number
  matched_keywords?: string[]
  reasons?: string[]
}

export interface CatalogMatchInfo {
  score: number
  products: string[]
  by: 'category' | 'name'
}

export interface TenderRow {
  id: number
  source_id?: number
  name: Nullable<string>
  status: string
  status_name: Nullable<string>
  totalcost: Nullable<number>
  currency: Nullable<string>
  close_at: Nullable<string>
  publicated_at: Nullable<string>
  first_seen_at?: Nullable<string>
  source_platform: string
  doc_count?: number
  company?: { name: Nullable<string> }
  region?: { name: Nullable<string> }
  lots_summary?: LotSummary[]
  goods_preview?: string[]
  match?: MatchInfo
  catalog?: CatalogMatchInfo
}

export interface AiSummary {
  summary_uz: string
  supplier_profile: Nullable<string>
  key_points?: string[]
  category_tags?: string[]
}

export interface TenderDetail extends TenderRow {
  lot_count?: number
  good_count?: number
  ai?: Nullable<AiSummary>
  detail?: {
    method_marks?: Nullable<string>
    close_time?: Nullable<string>
    company_details?: Nullable<string>
  }
  document_sections?: {
    section: string
    files: {
      file_id: string
      file_ref: Nullable<string>
      name: Nullable<string>
      file_type: Nullable<string>
      size_bytes: Nullable<number>
      download_url: string
    }[]
  }[]
  lots?: Lot[]
}

// --- statistika -----------------------------------------------------------
export interface Stats {
  count: number
  by_currency: { currency: string; total_value: number; tender_count: number }[]
  by_region?: { name: string; tender_count: number; total_value: number }[]
  by_status?: { status: string; name: Nullable<string>; tender_count: number }[]
}

export interface FreshnessPlatform {
  source_platform: string
  status: string
  age_sec: Nullable<number>
  new: number
}

export interface Freshness {
  overall_age_sec: Nullable<number>
  any_error: boolean
  platforms: FreshnessPlatform[]
  detection?: {
    sample: number
    median_hours: Nullable<number>
    within_1h_pct: Nullable<number>
  }
}

// --- katalog / profil -----------------------------------------------------
export interface Product {
  id: number
  name: string
  category_code: Nullable<string>
  keywords: string[]
  unit: Nullable<string>
  price: Nullable<number>
  currency: Nullable<string>
  stock_qty: Nullable<number>
  stock_unit: Nullable<string>
  match_count: number
  notify: boolean
}

export interface ProductSuggestion {
  name: string
  tender_count: number
}

export interface CompanyProfileData {
  contact_name: Nullable<string>
  email: Nullable<string>
  phone: Nullable<string>
  position: Nullable<string>
  name: Nullable<string>
  about: Nullable<string>
  constraints_note: Nullable<string>
  certificates: string[]
  clearances: string[]
  experience_years: Nullable<number>
  max_contract_value: Nullable<number>
  max_contract_currency: Nullable<string>
  employees: Nullable<number>
  capacity_note: Nullable<string>
  lead_time_days: Nullable<number>
  min_margin_percent: Nullable<number>
  regions: string[]
  min_cost: Nullable<number>
  max_cost: Nullable<number>
  keywords: string[]
  currency: Nullable<string>
}

export interface SavedSearch {
  id: number
  name: string
  keywords: string[]
  regions: string[]
  currency: Nullable<string>
  min_cost: Nullable<number>
  max_cost: Nullable<number>
  match_count?: number
}

// --- AI -------------------------------------------------------------------
export interface AiMatchResult {
  verdict: 'mos' | 'qisman' | 'mos_emas'
  score: number
  reason_uz: string
  matched_items?: string[]
  requirements?: string[]
  risks?: string[]
  cached: boolean
  model: Nullable<string>
}

export interface GoNoGoResult {
  decision: 'go' | 'review' | 'no_go'
  confidence: number
  summary_uz: string
  blockers?: string[]
  next_steps?: string[]
  missing_data?: string[]
  criteria?: { key: string; status: string; note_uz: string }[]
  criteria_labels?: { key: string; label: string }[]
  cached: boolean
  model: Nullable<string>
}

// --- hujjatlar ------------------------------------------------------------
export interface DocumentTextItem {
  file_ref: string
  name: Nullable<string>
  status: string
  reason: Nullable<string>
  char_count: Nullable<number>
  page_count: Nullable<number>
  preview: Nullable<string>
}

export interface DocumentTextResult {
  documents: DocumentTextItem[]
  summary: { ok: number; manual_review: number }
}

export interface DocumentType {
  code: string
  label: string
  hint: Nullable<string>
}

export interface CompanyDocument {
  id: number
  doc_type: string
  label: Nullable<string>
  name: string
  number: Nullable<string>
  issued_at: Nullable<string>
  valid_until: Nullable<string>
  file_name: Nullable<string>
  file_ref: Nullable<string>
  note: Nullable<string>
  status: 'ok' | 'expiring_soon' | 'expired'
  days_left: Nullable<number>
}

export interface ComplianceItem {
  doc_type: string
  label: string
  status: 'ok' | 'expiring_soon' | 'expired' | 'missing'
  required_by: 'tender' | 'base'
  evidence: string
  evidence_source: Nullable<string>
  confidence: Nullable<number>
  hint: Nullable<string>
  days_left: Nullable<number>
  document: Nullable<CompanyDocument>
}

export interface ComplianceResult {
  items: ComplianceItem[]
  extra_documents?: { label: string }[]
  summary: {
    ready: number
    expiring_soon: number
    expired: number
    missing: number
    blocking: number
    note: string
    disclaimer: string
  }
}

// --- ombor ----------------------------------------------------------------
export interface StockItem {
  lot_id: number
  item_id: number
  name: string
  unit: Nullable<string>
  required_qty: Nullable<number>
  available_qty: Nullable<number>
  shortfall_qty: Nullable<number>
  status: 'yetarli' | 'yetishmaydi' | 'nomalum'
  status_label: string
  reason: Nullable<string>
  qty_note: Nullable<string>
  product: { name: string; stock_age_days: Nullable<number> }
}

export interface StockCheckResult {
  items: StockItem[]
  shortages: StockItem[]
  preliminary: boolean
  stock?: { warning: Nullable<string> }
  summary: {
    positions: number
    matched: number
    ok: number
    short: number
    unknown: number
    unmatched: number
  }
}

// --- import ---------------------------------------------------------------
export interface ImportIssue {
  row: number
  field: string
  column: string
  value: Nullable<string>
  message: string
}

export interface ImportResult {
  rows_total: number
  rows_ok: number
  rows_error: number
  inserted: number
  updated: number
  header_row: number
  format: string
  errors?: ImportIssue[]
  warnings?: ImportIssue[]
  columns?: { detected: Record<string, string>; unknown: string[] }
  preview?: {
    row: number
    name: string
    keywords: string[]
    unit: Nullable<string>
    stock_qty: Nullable<number>
    cost_price: Nullable<number>
  }[]
}

// --- narx hisobi ----------------------------------------------------------
export interface PricingItem {
  name: string
  unit: string
  qty: number | string
  unit_cost: number | string
  ref_price?: Nullable<number>
}

export interface PricingInputs {
  markup_percent: number | string
  risk_reserve_percent: number | string
  risk_reserve_fixed: number | string
  logistics_percent: number | string
  logistics_fixed: number | string
  vat_percent: number | string
  currency: Nullable<string>
  items: PricingItem[]
  manual_price: number | string | null
  budget?: Nullable<number>
  budget_currency?: Nullable<string>
  min_margin_percent?: Nullable<number>
}

export interface PricingSaved {
  inputs: PricingInputs
  note: Nullable<string>
  updated_at: string
}

// --- bildirishnoma --------------------------------------------------------
export interface NotifySettingsData {
  enabled: boolean
  /** Foydalanuvchi kiritadigan YAGONA email maydoni — qabul qiluvchi. */
  email: Nullable<string>
  min_score: number
  base_url: string
  telegram_enabled: boolean
  /** ESKI maydon — obunachilar jadvaliga ko'chirilgan, endi ishlatilmaydi. */
  telegram_chat_id: Nullable<string>
  /** Platforma email yubora oladimi (server .env sozlamasi) */
  smtp_ready: boolean
  /** Xabar qaysi manzildan ketadi (server .env: SMTP_FROM) */
  smtp_from: Nullable<string>
  telegram_token_set: boolean
  telegram_ready: boolean
  /** `notify_telegram_subscriber` jadvali bazadami (patch qo'llanganmi) */
  subscribers_ready: boolean
  effective_email: Nullable<string>
}

/** Bir martalik Telegram ulash havolasi */
export interface TelegramLink {
  token: string
  url: string
  bot: string
  expires_at: Nullable<string>
  ttl_minutes: number
}

export interface TelegramLinkStatus {
  found: boolean
  connected: boolean
  chat_id?: Nullable<string>
  expired?: boolean
  subscribers: TelegramSubscriber[]
}

/** Telegram obunachisi — botga /start bosgan suhbat.
 *  Ro'yxatni server yuritadi (`notify_telegram_subscriber`), interfeys faqat
 *  `enabled` ni o'zgartira oladi: qolgani Telegramdan keladi. */
export interface TelegramSubscriber {
  chat_id: string
  title: Nullable<string>
  chat_type: Nullable<string>
  username: Nullable<string>
  enabled: boolean
  /** 'link' = ulash havolasi bilan tasdiqlangan; 'legacy' = eski usulda */
  source: string
  first_seen_at: Nullable<string>
  last_seen_at: Nullable<string>
}

export interface TelegramBot {
  id: number
  username: Nullable<string>
  first_name: Nullable<string>
}
