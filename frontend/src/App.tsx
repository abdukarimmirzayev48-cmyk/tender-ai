import { useEffect, useState, useCallback, useRef, lazy, Suspense } from 'react'
import { api } from '@/api'
import Icon from './components/Icon'
import Sidebar from './components/Sidebar'
import Filters from './components/Filters'
import type { FiltersState } from './components/Filters'
import SourceChips from './components/SourceChips'
import StatsStrip from './components/StatsStrip'
import TenderTable from './components/TenderTable'
import Pagination from './components/Pagination'
import ProfileForm from './components/ProfileForm'
import CatalogView from './components/CatalogView'
import AccountSettings from './components/AccountSettings'
import CompanyDocuments from './components/CompanyDocuments'
import Freshness from './components/Freshness'
import { Button } from '@/components/ui/button'
import { FlipText } from '@/components/ui/flip-text'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// Statistika sahifasi ALOHIDA CHUNK'da. Sabab: u yagona joy bo'lib Recharts
// ni tortadi (~400 KB) — uni asosiy paketga qo'shsak, tenderlar ro'yxatini
// ochgan HAR BIR foydalanuvchi hech qachon ko'rmasligi mumkin bo'lgan grafik
// kutubxonasini yuklab olardi.
const StatsView = lazy(() => import('./components/StatsView'))

// Tender paneli ham alohida: u AI, narx hisobi, cheklist va ombor
// panellarini tortadi, lekin faqat qatorga bosilganda ochiladi.
const TenderDrawer = lazy(() => import('./components/TenderDrawer'))
import type {
  Category, CompanyProfileData, CatalogMatchInfo, Freshness as FreshnessData,
  Product, Region, SavedSearch, Stats, Status, TenderRow,
} from '@/types'

const PAGE_SIZE = 25
const REFRESH_MS = 180_000

// `products` / `services` — tender tarkibidagi pozitsiyalar bo'yicha filtr.
// `q` dan alohida: `q` buyurtmachi nomini ham qidiradi va soxta natija beradi
// ("qurilish" -> "Курилиш дирекцияси" MCHJ). Ikkalasi tanlansa — ORASIDA "yoki".
const DEFAULT_FILTERS: FiltersState = {
  status: 'open', region: '', currency: '', q: '', category: '',
  products: [], services: [], sort: 'close_at',
}

// Katalog mosligini o'qiladigan sabablarga aylantiradi (drawer shuni ko'rsatadi).
function catalogReasons(c?: CatalogMatchInfo): string[] {
  if (!c) return []
  const items = c.products || []
  if (!items.length) return []
  return [`${c.by === 'category' ? 'Kategoriya' : 'Nom'} bo‘yicha mos: ${items.join(', ')}`]
}

const VIEW_TITLES: Record<string, string> = {
  tenders: 'Tenderlar',
  match: 'Sizga mos',
  catalog: 'Mahsulot katalogi',
  documents: 'Hujjatlarim',
  stats: 'Statistika',
  profile: 'Saqlangan qidiruv',
  account: 'Akkaunt',
}

export default function App() {
  const [view, setView] = useState('tenders')
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)
  const [offset, setOffset] = useState(0)
  // Ikkala manba ham yoqilgan — foydalanuvchi hammasini bir joyda ko'rsin.
  const [sources, setSources] = useState<string[]>(['xt-xarid', 'uzex'])

  const [data, setData] = useState<{ items: TenderRow[]; total: number }>({ items: [], total: 0 })
  const [stats, setStats] = useState<Stats | null>(null)
  const [regions, setRegions] = useState<Region[]>([])
  const [statuses, setStatuses] = useState<Status[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [fresh, setFresh] = useState<FreshnessData | null>(null)
  // profile = joriy QO'LLANGAN qidiruv (moslashtirish shunga qarab ballaydi)
  const [profile, setProfile] = useState<Partial<SavedSearch> | null>(null)
  const [searches, setSearches] = useState<SavedSearch[]>([])
  const [activeSearchId, setActiveSearchId] = useState<number | null>(null)
  const [editing, setEditing] = useState<SavedSearch | 'new' | null>(null)
  // Akkaunt profili — yon paneldagi foydalanuvchi bloki shundan o'qiydi
  const [account, setAccount] = useState<CompanyProfileData | null>(null)
  // Cheklistdan "hujjatlarim" ga o'tilganda qaysi tur formasi ochilsin
  const [docFocus, setDocFocus] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<Product[]>([])
  const [catalogNew, setCatalogNew] = useState({ new: 0, total: 0 })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ id: number; match?: TenderRow['match'] } | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  // Bir martalik ma'lumotlar
  const loadSearches = useCallback(
    () => api.searches().then(setSearches).catch(() => {}), [])
  const loadCatalog = useCallback(() => {
    api.catalog().then(setCatalog).catch(() => {})
    api.catalogNewCount().then(setCatalogNew).catch(() => {})
  }, [])
  useEffect(() => {
    api.regions().then((rs) => setRegions(rs.filter((r) => r.level === 1))).catch(() => {})
    api.statuses().then(setStatuses).catch(() => {})
    api.categories().then(setCategories).catch(() => {})
    api.freshness().then(setFresh).catch(() => {})
    api.getProfile().then(setAccount).catch(() => {})
    // Bildirishnomadagi kartochka havolasi: /?tender=123 -> drawer ochiladi.
    // TZ P0-10 qabul mezoni: xabardagi havola BOSILGANDA aynan o'sha kartochka.
    const deep = new URLSearchParams(window.location.search).get('tender')
    if (deep) setSelected({ id: Number(deep) })
    loadSearches()
    loadCatalog()
  }, [loadSearches, loadCatalog])

  // Saqlangan qidiruvni qo'llash — profilga o'giradi va "Sizga mos"ga o'tadi
  function applySearch(s: SavedSearch) {
    setProfile({
      keywords: s.keywords, regions: s.regions, currency: s.currency,
      min_cost: s.min_cost, max_cost: s.max_cost,
    })
    setActiveSearchId(s.id)
    setEditing(null)
    setView('match'); setOffset(0)
  }
  function newSearch() { setEditing('new'); setView('profile'); setOffset(0) }
  function editSearch(s: SavedSearch) { setEditing(s); setView('profile'); setOffset(0) }
  async function removeSearch(s: SavedSearch) {
    if (!window.confirm(`"${s.name}" qidiruvini o‘chirasizmi?`)) return
    try { await api.deleteSearch(s.id) } catch { /* ignore */ }
    if (activeSearchId === s.id) { setActiveSearchId(null); setProfile(null) }
    loadSearches()
  }

  const source = sources.length === 1 ? sources[0] : ''

  // Asosiy yuklovchi — view'ga qarab /tenders yoki /match
  const load = useCallback(async (opts: { silent?: boolean } = {}) => {
    // "Yangilangan: N oldin" ko'rsatkichi ETL yurishidan o'qiladi va u
    // BU YERDA yangilanishi kerak — aks holda ETL yurgan bo'lsa ham
    // ko'rsatkich sahifa yangilanmaguncha eski qiymatda qotib qolardi.
    api.freshness().then(setFresh).catch(() => {})

    // Ro'yxatsiz ko'rinishlar tender so'ramaydi
    if (['stats', 'profile', 'catalog', 'account', 'documents'].includes(view)) return
    if (!opts.silent) setLoading(true)
    setError(null)
    try {
      let t: { items: TenderRow[]; total: number }
      if (view === 'match' && activeSearchId) {
        // Saqlangan qidiruv faol — kalit so'z bo'yicha ballaydi
        t = await api.match({
          profile: profile || { keywords: [], regions: [], currency: null, min_cost: null, max_cost: null },
          status: filters.status, region: filters.region, currency: filters.currency,
          q: filters.q, category: filters.category,
          products: filters.products, services: filters.services,
          limit: PAGE_SIZE, offset,
        })
      } else if (view === 'match') {
        // Standart "Sizga mos" — KATALOG bo'yicha (kategoriya + nom)
        const r = await api.catalogMatch({
          region: filters.region, currency: filters.currency,
          products: filters.products, services: filters.services,
          limit: PAGE_SIZE, offset,
        })
        // catalog -> match shakliga moslaymiz (TenderTable o'zgarmaydi).
        // `reasons` HAM berilishi SHART: drawer uni ro'yxat qilib ko'rsatadi.
        t = {
          ...r,
          items: r.items.map((it) => ({
            ...it,
            match: {
              score: it.catalog?.score,
              matched_keywords: it.catalog?.products,
              reasons: catalogReasons(it.catalog),
            },
          })),
        }
        api.catalogSeen().then(() => setCatalogNew((n) => ({ ...n, new: 0 }))).catch(() => {})
      } else {
        t = await api.tenders({
          status: filters.status, region: filters.region,
          currency: filters.currency, q: filters.q, category: filters.category,
          product: filters.products, service: filters.services, source,
          limit: PAGE_SIZE, offset, sort: filters.sort,
        })
      }
      const s = await api.stats({ status: filters.status || 'open' })
      setData(t)
      setStats(s)
      setLastUpdated(new Date())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      if (!opts.silent) setLoading(false)
    }
  }, [view, filters, offset, source, profile, activeSearchId])

  useEffect(() => { load() }, [load])

  // Avtomatik yangilash
  const loadRef = useRef(load); loadRef.current = load
  useEffect(() => {
    const id = setInterval(() => loadRef.current({ silent: true }), REFRESH_MS)
    return () => clearInterval(id)
  }, [])

  function updateFilter(patch: Partial<FiltersState>) {
    setFilters((f) => ({ ...f, ...patch })); setOffset(0)
  }
  function goto(v: string) {
    // "Sizga mos"ga nav orqali kirilsa — katalog rejimi (qidiruv rejimidan chiqamiz)
    if (v === 'match') { setActiveSearchId(null); setProfile(null) }
    setView(v); setOffset(0)
  }
  // Katalogda mahsulot "N mos"ini bosish -> shu mahsulotni mos ko'rsatadi
  function openProductMatch(p: Product) {
    setActiveSearchId(null)
    updateFilter({ category: p.category_code || '' })
    setView('match'); setOffset(0)
  }
  // Tender cheklistidagi "Hujjatlarim bo'limiga o'tish"
  function openDocuments(docType: string) {
    setDocFocus(docType || null)
    setSelected(null)          // tender panelini yopamiz
    setView('documents'); setOffset(0)
  }
  function toggleSource(id: string) {
    setSources((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])
    setOffset(0)
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1
  const isList = view === 'tenders' || view === 'match'
  const activeSearch = searches.find((s) => s.id === activeSearchId)
  const emptyCatalog = view === 'match' && !activeSearchId && catalog.length === 0

  return (
    <div className="grid min-h-screen grid-cols-[232px_1fr] max-md:grid-cols-1">
      <Sidebar
        active={view} onNavigate={goto}
        newMatchCount={catalogNew.new} account={account}
        searches={searches} activeSearchId={activeSearchId}
        onApplySearch={applySearch} onNewSearch={newSearch}
        onEditSearch={editSearch} onDeleteSearch={removeSearch}
      />

      <main className="min-w-0 px-6 pb-16 pt-5">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {/* Sahifa sarlavhasi — Vengeance UI `FlipText`, `loop={false}`:
              ko'rinish almashganda harflar bir marta ag'darilib chiqadi,
              ya'ni qayerga o'tganingiz ko'zga tashlanadi.
              `key={view}` SHART — u bo'lmasa React bir xil elementni qayta
              ishlatadi va animatsiya faqat birinchi marta ishlaydi.
              (`MorphText` ATAYIN olinmadi: u so'zlarni taymer bilan
              aylantiradigan, `clamp(3rem,15vw,10rem)` o'lchamli landing-page
              komponenti — dashboard sarlavhasi uchun emas.) */}
          <h1 className="text-[22px] font-bold">
            <FlipText key={view} loop={false} duration={0.9}>
              {VIEW_TITLES[view] || ''}
            </FlipText>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            <Freshness data={fresh} />
            {/* DIQQAT: quyidagi tugma manba saytlarga BORMAYDI. U ro'yxatni o'z
                bazamizdan qayta o'qiydi. Manbadan yig'ish — ETL ishi. */}
            {isList && (
              <Button variant="outline" size="sm" onClick={() => load()} disabled={loading}
                title="Ro'yxatni bazadan qayta o'qiydi (manba saytlarga so'rov yubormaydi)">
                <Icon name="refresh" size={14} className={cn(loading && 'animate-spin')} />
                Yangilash
              </Button>
            )}
          </div>
        </div>

        {isList && (
          <>
            <Filters
              filters={filters} regions={regions} statuses={statuses} categories={categories}
              onChange={updateFilter}
              onReset={() => { setFilters(DEFAULT_FILTERS); setOffset(0) }}
              showSort={view === 'tenders'}
            />
            <SourceChips selected={sources} onToggle={toggleSource} />

            {view === 'match' && activeSearch && (
              <Info>
                Saqlangan qidiruv: <b>{activeSearch.name}</b>
                <button className="ml-1.5 font-semibold underline-offset-2 hover:underline"
                  onClick={() => goto('match')}>Katalog bo‘yicha →</button>
              </Info>
            )}
            {emptyCatalog && (
              <Info>
                Katalogingiz bo‘sh — to‘ldirsangiz mos tenderlar shu yerda chiqadi.
                <button className="ml-1.5 font-semibold underline-offset-2 hover:underline"
                  onClick={() => goto('catalog')}>Katalogga o‘tish →</button>
              </Info>
            )}

            <StatsStrip stats={stats} total={data.total} lastUpdated={lastUpdated} />

            {error && (
              <div className="mb-3 rounded-lg border border-urgent/40 bg-urgent-soft px-3.5 py-2.5 text-[13px] text-urgent">
                Xatolik: {error}
                <div className="mt-0.5 text-[12px] opacity-80">Backend ishlayaptimi? (:8000)</div>
              </div>
            )}

            <TenderTable
              items={data.items}
              mode={view}
              loading={loading}
              /* Status ustuni behuda: filtr bitta statusda bo'lsa har qator bir xil
                 bo'ladi. Faqat "barcha statuslar" tanlanganda ko'rsatamiz. */
              showStatus={!filters.status}
              sort={filters.sort}
              onSort={(col) => updateFilter({ sort: filters.sort === col ? `-${col}` : col })}
              onSelect={(id) => {
                const row = data.items.find((x) => x.id === id)
                setSelected({ id, match: row?.match })
              }}
            />

            <Pagination
              page={currentPage} totalPages={totalPages}
              onPrev={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              onNext={() => setOffset(offset + PAGE_SIZE)}
            />
          </>
        )}

        {view === 'catalog' && (
          <CatalogView
            items={catalog} categories={categories}
            onChanged={loadCatalog}
            onOpenMatch={openProductMatch}
          />
        )}
        {/* Saqlangach yon paneldagi ism/email darhol yangilanadi */}
        {view === 'account' && <AccountSettings onSaved={setAccount} />}
        {view === 'documents' && <CompanyDocuments focusType={docFocus} />}
        {view === 'stats' && (
          <Suspense fallback={<Skeleton className="h-[420px] w-full rounded-xl" />}>
            <StatsView />
          </Suspense>
        )}
        {view === 'profile' && (
          <ProfileForm
            search={editing === 'new' ? null : editing}
            regions={regions}
            onSaved={() => { loadSearches(); setEditing(null); setView('tenders') }}
            onCancel={() => { setEditing(null); setView(searches.length ? 'match' : 'tenders') }}
          />
        )}
      </main>

      {selected && (
        <Suspense fallback={null}>
          <TenderDrawer
            id={selected.id} match={selected.match}
            onOpenDocuments={openDocuments}
            onClose={() => {
              setSelected(null)
              // Bildirishnomadan kelgan ?tender= parametrini olib tashlaymiz
              if (new URLSearchParams(window.location.search).has('tender')) {
                window.history.replaceState({}, '', window.location.pathname)
              }
            }} />
        </Suspense>
      )}
    </div>
  )
}

function Info({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 rounded-lg border border-primary/30 bg-secondary px-3.5 py-2.5 text-[13px] text-primary">
      {children}
    </div>
  )
}
