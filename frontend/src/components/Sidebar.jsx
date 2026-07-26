import Icon from './Icon.jsx'

// Chap navigatsiya paneli (numeo.ai uslubi).
const NAV = [
  { key: 'tenders', icon: 'tenders', label: 'Tenderlar', section: 'ASOSIY' },
  { key: 'match', icon: 'match', label: 'Sizga mos' },
  { key: 'catalog', icon: 'box', label: 'Mahsulot katalogi' },
  { key: 'stats', icon: 'stats', label: 'Statistika' },
]

export default function Sidebar({
  active, onNavigate, newMatchCount,
  searches, activeSearchId, onApplySearch, onNewSearch, onEditSearch, onDeleteSearch,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__logo">B</span>
        <div>
          <div className="sidebar__name">Birja</div>
          <div className="sidebar__tag">Tenderlar agregatori</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        {NAV.map((item) => (
          <div key={item.key}>
            {item.section && <div className="sidebar__section">{item.section}</div>}
            <button
              className={`navitem ${active === item.key ? 'navitem--active' : ''}`}
              onClick={() => onNavigate(item.key)}
            >
              <span className="navitem__icon"><Icon name={item.icon} size={17} /></span>
              <span>{item.label}</span>
              {item.key === 'match' && newMatchCount > 0 && (
                <span className="navitem__badge" title="Katalogingizga mos yangi tenderlar">
                  {newMatchCount}
                </span>
              )}
            </button>
          </div>
        ))}

        {/* Saqlangan qidiruvlar (A bosqich) */}
        <div className="sidebar__section sidebar__section--row">
          <span>SAQLANGAN QIDIRUVLAR</span>
          <button className="iconbtn" title="Yangi qidiruv" onClick={onNewSearch}>
            <Icon name="plus" size={14} />
          </button>
        </div>

        {searches.length === 0 && (
          <div className="saved__empty">Hali yo‘q. Filtrlab, saqlang.</div>
        )}
        {searches.map((s) => (
          <div key={s.id}
            className={`saved ${active === 'match' && activeSearchId === s.id ? 'saved--active' : ''}`}>
            <button className="saved__main" onClick={() => onApplySearch(s)} title={s.name}>
              <span className="saved__name">{s.name}</span>
              {s.match_count > 0 && <span className="saved__count">{s.match_count}</span>}
            </button>
            <button className="saved__act" title="Tahrirlash" onClick={() => onEditSearch(s)}>
              <Icon name="edit" size={13} />
            </button>
            <button className="saved__act" title="O‘chirish" onClick={() => onDeleteSearch(s)}>
              <Icon name="trash" size={13} />
            </button>
          </div>
        ))}
      </nav>

      <div className="sidebar__foot">
        <div className="sidebar__user">
          <span className="sidebar__avatar">px</span>
          <div>
            <div className="sidebar__uname">px pc</div>
            <div className="sidebar__uemail">pcpx743@gmail.com</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
