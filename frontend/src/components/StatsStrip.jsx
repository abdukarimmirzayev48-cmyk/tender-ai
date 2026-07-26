import { shortMoney } from '../format.js'
import Icon from './Icon.jsx'

// Jadval ustidagi ixcham statistika chizig'i (numeo uslubi).
export default function StatsStrip({ stats, total, lastUpdated }) {
  return (
    <div className="strip">
      <span className="strip__item"><b>{total}</b> tender</span>
      {stats && (
        <>
          <span className="strip__sep" />
          <span className="strip__item"><b>{stats.count}</b> ochiq</span>
          {(stats.by_currency || []).map((c) => (
            <span className="strip__item" key={c.currency}>
              {shortMoney(c.total_value, c.currency)} <span className="muted">({c.tender_count})</span>
            </span>
          ))}
        </>
      )}
      {lastUpdated && (
        <span className="strip__updated">
          <Icon name="refresh" size={12} /> {lastUpdated.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
        </span>
      )}
    </div>
  )
}
