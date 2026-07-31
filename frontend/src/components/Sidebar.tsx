import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { CompanyProfileData, SavedSearch } from '@/types'

// Chap navigatsiya paneli.
const NAV = [
  { key: 'tenders', icon: 'tenders', label: 'Tenderlar', section: 'Asosiy' },
  { key: 'match', icon: 'match', label: 'Sizga mos' },
  { key: 'catalog', icon: 'box', label: 'Mahsulot katalogi' },
  { key: 'documents', icon: 'clip', label: 'Hujjatlarim' },
  { key: 'stats', icon: 'stats', label: 'Statistika' },
]

interface SidebarProps {
  active: string
  onNavigate: (key: string) => void
  newMatchCount: number
  account: CompanyProfileData | null
  searches: SavedSearch[]
  activeSearchId: number | null
  onApplySearch: (s: SavedSearch) => void
  onNewSearch: () => void
  onEditSearch: (s: SavedSearch) => void
  onDeleteSearch: (s: SavedSearch) => void
}

export default function Sidebar({
  active, onNavigate, newMatchCount, account,
  searches, activeSearchId, onApplySearch, onNewSearch, onEditSearch, onDeleteSearch,
}: SidebarProps) {
  // Ism/email akkaunt profilidan o'qiladi; to'ldirilmagan bo'lsa — taklif.
  const uname = account?.contact_name || account?.name || 'Akkaunt'
  const uinfo = account?.email || account?.position || 'To‘ldirilmagan'
  const initials = (account?.contact_name || account?.name || '?')
    .split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

  const item = 'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors'

  return (
    <aside className="sticky top-0 flex h-screen flex-col border-r bg-sidebar px-3 py-4">
      <div className="mb-4 flex items-center gap-2.5 px-1">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-[15px] font-bold text-primary-foreground">
          B
        </span>
        <div>
          <div className="text-[14px] font-bold leading-tight">Birja</div>
          <div className="text-[11px] text-muted-foreground">Tenderlar agregatori</div>
        </div>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto">
        {NAV.map((nav) => (
          <div key={nav.key}>
            {nav.section && (
              <div className="mb-1 mt-3 px-2.5 text-[10px] font-bold text-muted-foreground">
                {nav.section}
              </div>
            )}
            <button
              className={cn(item, active === nav.key
                ? 'bg-sidebar-accent font-semibold text-sidebar-accent-foreground'
                : 'text-foreground hover:bg-accent')}
              onClick={() => onNavigate(nav.key)}
            >
              <Icon name={nav.icon} size={17} />
              <span className="flex-1 truncate">{nav.label}</span>
              {nav.key === 'match' && newMatchCount > 0 && (
                <span
                  className="tabular rounded-full bg-primary px-1.5 py-px text-[11px] font-bold text-primary-foreground"
                  title="Katalogingizga mos yangi tenderlar"
                >{newMatchCount}</span>
              )}
            </button>
          </div>
        ))}

        {/* Saqlangan qidiruvlar */}
        <div className="mb-1 mt-4 flex items-center gap-1 px-2.5 text-[10px] font-bold text-muted-foreground">
          <span className="flex-1">Saqlangan qidiruvlar</span>
          <button
            className="rounded p-1 transition-colors hover:bg-accent hover:text-foreground"
            title="Yangi qidiruv" onClick={onNewSearch}
          >
            <Icon name="plus" size={14} />
          </button>
        </div>

        {searches.length === 0 && (
          <div className="px-2.5 py-1 text-[12px] text-muted-foreground">
            Hali yo‘q — filtrlab saqlang.
          </div>
        )}
        {searches.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group flex items-center gap-0.5 rounded-lg pr-1 transition-colors',
              active === 'match' && activeSearchId === s.id
                ? 'bg-sidebar-accent' : 'hover:bg-accent',
            )}
          >
            <button
              className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-left text-[13px]"
              onClick={() => onApplySearch(s)} title={s.name}
            >
              <span className="flex-1 truncate">{s.name}</span>
              {!!s.match_count && (
                <span className="tabular rounded bg-muted px-1.5 text-[11px] text-muted-foreground">
                  {s.match_count}
                </span>
              )}
            </button>
            <button
              className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-card hover:text-foreground group-hover:opacity-100"
              title="Tahrirlash" onClick={() => onEditSearch(s)}
            >
              <Icon name="edit" size={13} />
            </button>
            <button
              className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-card hover:text-urgent group-hover:opacity-100"
              title="O‘chirish" onClick={() => onDeleteSearch(s)}
            >
              <Icon name="trash" size={13} />
            </button>
          </div>
        ))}
      </nav>

      {/* AKKAUNT — kompaniya profili shu yerda. Katalog "nima sotasiz",
          profil esa "kim siz" — bular boshqa-boshqa narsa. */}
      <div className="mt-3 border-t pt-3">
        <Button
          variant="ghost"
          className={cn('h-auto w-full justify-start gap-2.5 px-2.5 py-2',
            active === 'account' && 'bg-sidebar-accent text-sidebar-accent-foreground')}
          onClick={() => onNavigate('account')}
          title="Akkaunt va kompaniya profili"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-[12px] font-bold text-primary">
            {initials}
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-[13px] font-semibold">{uname}</span>
            <span className="block truncate text-[11px] font-normal text-muted-foreground">
              {uinfo}
            </span>
          </span>
          <Icon name="right" size={13} className="text-muted-foreground" />
        </Button>
      </div>
    </aside>
  )
}
