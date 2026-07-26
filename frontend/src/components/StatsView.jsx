import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { money } from '../format.js'

// Statistika sahifasi: valyuta bo'yicha (ALOHIDA) + hudud bo'yicha taqsimot.
export default function StatsView() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.stats({ status: 'open' }).then(setStats).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="alert alert--error">Xatolik: {error}</div>
  if (!stats) return <div className="muted" style={{ padding: 20 }}>Yuklanmoqda…</div>

  const maxRegion = Math.max(1, ...(stats.by_region || []).map((r) => r.tender_count))

  return (
    <div className="statsview">
      <h2 className="panel__title">Statistika — ochiq tenderlar</h2>

      <div className="statcards">
        <div className="statcard">
          <div className="statcard__value">{stats.count}</div>
          <div className="statcard__label">Jami ochiq tender</div>
        </div>
        {(stats.by_currency || []).map((c) => (
          <div className="statcard" key={c.currency}>
            <div className="statcard__value">{money(c.total_value, c.currency)}</div>
            <div className="statcard__label">{c.tender_count} ta · {c.currency} umumiy summa</div>
          </div>
        ))}
      </div>

      <h3 className="panel__subtitle">Hudud bo‘yicha taqsimot</h3>
      <div className="regionbars">
        {(stats.by_region || []).map((r) => (
          <div className="regionbar" key={r.area_id}>
            <span className="regionbar__name">{r.name || '—'}</span>
            <span className="regionbar__track">
              <span className="regionbar__fill" style={{ width: `${(r.tender_count / maxRegion) * 100}%` }} />
            </span>
            <span className="regionbar__count">{r.tender_count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
