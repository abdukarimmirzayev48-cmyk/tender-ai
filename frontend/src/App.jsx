import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from './api.js'
import Icon from './components/Icon.jsx'
import Sidebar from './components/Sidebar.jsx'
import Filters from './components/Filters.jsx'
import SourceChips from './components/SourceChips.jsx'
import StatsStrip from './components/StatsStrip.jsx'
import StatsView from './components/StatsView.jsx'
import TenderTable from './components/TenderTable.jsx'
import TenderDrawer from './components/TenderDrawer.jsx'
import Pagination from './components/Pagination.jsx'
import ProfileForm from './components/ProfileForm.jsx'
import CatalogView from './components/CatalogView.jsx'
import Freshness from './components/Freshness.jsx'

const PAGE_SIZE = 25
const REFRESH_MS = 180_000
const DEFAULT_FILTERS = { status: 'open', region: '', currency: '', q: '', category: '', sort: 'close_at' }

const VIEW_TITLES = {
  tenders: 'Tenderlar',
  match: 'Sizga mos',
  catalog: 'Mahsulot katalogi',
  stats: 'Statistika',
  profile: 'Saqlangan qidiruv',
}

export default function App() {
  const [view, setView] = useState('tenders')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [offset, setOffset] = useState(0)
  // Ikkala manba ham yoqilgan — foydalanuvchi hammasini bir joyda ko'rsin.
  // (Bittasi tanlansa backend'ga source filtri yuboriladi.)
  const [sources, setSources] = useState(['xt-xarid', 'uzex'])

  const [data, setData] = useState({ items: [], total: 0 })
  const [stats, setStats] = useState(null)
  const [regions, setRegions] = useState([])
  const [statuses, setStatuses] = useState([])
  const [categories, setCategories] = useState([])
  const [fresh, setFresh] = useState(null)
  // profile = joriy QO'LLANGAN qidiruv (moslashtirish shunga qarab ballaydi)
  const [profile, setProfile] = useState(null)
  // Saqlangan qidiruvlar (A bosqich)
  const [searches, setSearches] = useState([])
  const [activeSearchId, setActiveSearchId] = useState(null)
  const [editing, setEditing] = useState(null) // null | 'new' | searchObyekt
  // Mahsulot katalogi (asosiy moslashtirish manbai)
  const [catalog, setCatalog] = useState([])
  const [catalogNew, setCatalogNew] = useState({ new: 0, total: 0 })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null) // {id, match}
  const [lastUpdated, setLastUpdated] = useState(null)

  // Bir martalik ma'lumotlar
  const loadSearches = useCallback(() => api.searches().then(setSearches).catch(() => {}), [])
  const loadCatalog = useCallback(() => {
    api.catalog().then(setCatalog).catch(() => {})
    api.catalogNewCount().then(setCatalogNew).catch(() => {})
  }, [])
  useEffect(() => {
    api.regions().then((rs) => setRegions(rs.filter((r) => r.level === 1))).catch(() => {})
    api.statuses().then(setStatuses).catch(() => {})
    api.categories().then(setCategories).catch(() => {})
    api.freshness().then(setFresh).catch(() => {})
    loadSearches()
    loadCatalog()
  }, [loadSearches, loadCatalog])

  // Saqlangan qidiruvni qo'llash — profilga o'giradi va "Sizga mos" ko'rinishiga o'tadi
  function applySearch(s) {
    setProfile({
      keywords: s.keywords, regions: s.regions, currency: s.currency,
      min_cost: s.min_cost, max_cost: s.max_cost,
    })
    setActiveSearchId(s.id)
    setEditing(null)
    setView('match'); setOffset(0)
  }
  function newSearch() { setEditing('new'); setView('profile'); setOffset(0) }
  function editSearch(s) { setEditing(s); setView('profile'); setOffset(0) }
  async function removeSearch(s) {
    if (!window.confirm(`"${s.name}" qidiruvini o‘chirasizmi?`)) return
    try { await api.deleteSearch(s.id) } catch { /* ignore */ }
    if (activeSearchId === s.id) { setActiveSearchId(null); setProfile(null) }
    loadSearches()
  }

  const source = sources.length === 1 ? sources[0] : ''

  // Asosiy yuklovchi — view'ga qarab /tenders yoki /match
  const load = useCallback(async (opts = {}) => {
    if (view === 'stats' || view === 'profile' || view === 'catalog') return
    if (!opts.silent) setLoading(true)
    setError(null)
    try {
      const common = {
        status: filters.status, region: filters.region,
        currency: filters.currency, q: filters.q, category: filters.category, source,
        limit: PAGE_SIZE, offset,
      }
      let t
      if (view === 'match' && activeSearchId) {
        // Saqlangan qidiruv faol — kalit so'z bo'yicha ballaydi
        t = await api.match({
          profile: profile || { keywords: [], regions: [], currency: null, min_cost: null, max_cost: null },
          status: filters.status, region: filters.region, currency: filters.currency,
          q: filters.q, category: filters.category, limit: PAGE_SIZE, offset,
        })
      } else if (view === 'match') {
        // Standart "Sizga mos" — KATALOG bo'yicha (kategoriya + nom)
        const r = await api.catalogMatch({
          region: filters.region, currency: filters.currency, limit: PAGE_SIZE, offset,
        })
        // catalog -> match shakliga moslaymiz (TenderTable o'zgarmaydi)
        t = { ...r, items: r.items.map((it) => ({
          ...it, match: { score: it.catalog.score, matched_keywords: it.catalog.products },
        })) }
        api.catalogSeen().then(() => setCatalogNew((n) => ({ ...n, new: 0 }))).catch(() => {})
      } else {
        t = await api.tenders({ ...common, sort: filters.sort })
      }
      const s = await api.stats({ status: filters.status || 'open' })
      setData(t)
      setStats(s)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e.message)
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

  function updateFilter(patch) { setFilters((f) => ({ ...f, ...patch })); setOffset(0) }
  function goto(v) {
    // "Sizga mos"ga nav orqali kirilsa — katalog rejimi (qidiruv rejimidan chiqamiz)
    if (v === 'match') { setActiveSearchId(null); setProfile(null) }
    setView(v); setOffset(0)
  }
  // Katalogдa mahsulot "N mos"ini bosish -> shu mahsulotni qidiruvга aylantirib mos ko'rsatadi
  function openProductMatch(p) {
    setActiveSearchId(null)
    updateFilter({ category: p.category_code || '' })
    setView('match'); setOffset(0)
  }
  function toggleSource(id) {
    setSources((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])
    setOffset(0)
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1
  const isList = view === 'tenders' || view === 'match'
  const activeSearch = searches.find((s) => s.id === activeSearchId)
  const emptyCatalog = view === 'match' && !activeSearchId && catalog.length === 0

  return (
    <div className="layout">
      <Sidebar
        active={view} onNavigate={goto}
        newMatchCount={catalogNew.new}
        searches={searches} activeSearchId={activeSearchId}
        onApplySearch={applySearch} onNewSearch={newSearch}
        onEditSearch={editSearch} onDeleteSearch={removeSearch}
      />

      <main className="main">
        <div className="topbar">
          <h1 className="topbar__title">{VIEW_TITLES[view]}</h1>
          <div className="topbar__right">
            <Freshness data={fresh} />
            {isList && (
              <button className="btn btn--ghost btn--icon" onClick={() => load()} disabled={loading}>
                <Icon name="refresh" size={14} className={loading ? 'spin' : ''} />
                {loading ? 'Yangilanmoqda…' : 'Yangilash'}
              </button>
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
              <div className="alert alert--info">
                Saqlangan qidiruv: <b>{activeSearch.name}</b> (kalit so‘z bo‘yicha).
                <button className="link" onClick={() => goto('match')}>Katalog bo‘yicha ko‘rish →</button>
              </div>
            )}
            {emptyCatalog && (
              <div className="alert alert--info">
                Katalogingiz bo‘sh — mahsulot/xizmatlaringizni qo‘shsangiz, mos tenderlar shu yerда chiqadi.
                <button className="link" onClick={() => goto('catalog')}>Katalogga o‘tish →</button>
              </div>
            )}

            <StatsStrip stats={stats} total={data.total} lastUpdated={lastUpdated} />

            {error && (
              <div className="alert alert--error">
                Xatolik: {error}
                <div className="alert__hint">Backend ishlayaptimi? (uvicorn :8000)</div>
              </div>
            )}

            <TenderTable
              items={data.items}
              mode={view}
              loading={loading}
              /* Status ustuni behuda: filtr bitta statusда bo'lsa har qator bir xil
                 bo'ladi. Faqat "barcha statuslar" tanlanganда ko'rsatamiz. */
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
        {view === 'stats' && <StatsView />}
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
        <TenderDrawer id={selected.id} match={selected.match} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
