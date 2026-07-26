import { useState, useEffect, useRef, useMemo } from 'react'
import Icon from './Icon.jsx'

// Ikki darajali kategoriya filtri (raqobatchidagidek — qidiruv + son bilan).
// tree: [{code, name, count, children:[{code,name,count}]}]
export default function CategoryFilter({ tree, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)

  // Tashqariga bosilsa yopiladi
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // Tanlangan kategoriya nomi (tugma yorlig'i uchun)
  const label = useMemo(() => {
    if (!value) return 'Barcha kategoriyalar'
    for (const p of tree) {
      if (p.code === value) return p.name
      for (const c of p.children) if (c.code === value) return c.name
    }
    return value
  }, [value, tree])

  // Qidiruv bo'yicha filtrlash (nom ichidan)
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return tree
    return tree
      .map((p) => {
        const kids = p.children.filter((c) => c.name.toLowerCase().includes(needle))
        if (p.name.toLowerCase().includes(needle)) return p          // parent mos — hammasi
        if (kids.length) return { ...p, children: kids }             // faqat mos ichkilar
        return null
      })
      .filter(Boolean)
  }, [q, tree])

  function pick(code) { onChange(code); setOpen(false); setQ('') }

  return (
    <div className="catfilter" ref={ref}>
      <button className={`catfilter__btn ${value ? 'catfilter__btn--on' : ''}`}
              onClick={() => setOpen((o) => !o)}>
        <Icon name="grid" size={14} />
        <span className="catfilter__label">{label}</span>
        <Icon name="chevron" size={14} className="catfilter__caret" />
      </button>

      {open && (
        <div className="catfilter__pop">
          <div className="catfilter__search">
            <Icon name="search" size={14} className="searchbox__icon" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Kategoriya qidirish…" />
          </div>
          <div className="catfilter__list">
            <button className={`catrow catrow--all ${!value ? 'catrow--sel' : ''}`}
                    onClick={() => pick('')}>Barcha kategoriyalar</button>
            {filtered.map((p) => (
              <div key={p.code}>
                <button className={`catrow catrow--parent ${value === p.code ? 'catrow--sel' : ''}`}
                        onClick={() => pick(p.code)}>
                  <span className="catrow__name">{p.name}</span>
                  {p.count > 0 && <span className="catrow__count">{p.count}</span>}
                </button>
                {p.children.filter((c) => c.count > 0 || value === c.code).map((c) => (
                  <button key={c.code}
                          className={`catrow catrow--child ${value === c.code ? 'catrow--sel' : ''}`}
                          onClick={() => pick(c.code)}>
                    <span className="catrow__name">{c.name}</span>
                    {c.count > 0 && <span className="catrow__count">{c.count}</span>}
                  </button>
                ))}
              </div>
            ))}
            {filtered.length === 0 && <div className="catfilter__empty">Topilmadi</div>}
          </div>
        </div>
      )}
    </div>
  )
}
