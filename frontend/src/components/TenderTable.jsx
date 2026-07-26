import { useState } from 'react'
import { shortMoney, deadline } from '../format.js'
import Icon from './Icon.jsx'

// Ball rozetkasi rangi (Sizga mos ko'rinishi uchun)
function scoreClass(s) {
  if (s >= 70) return 'score--high'
  if (s >= 40) return 'score--mid'
  return 'score--low'
}

// Manba qisqa yorlig'i — qaysi platformadan kelganini bir qarashда bilish uchun.
const SRC = {
  'xt-xarid': { label: 'xt-xarid', cls: 'src--xt' },
  'uzex': { label: 'etender', cls: 'src--uz' },
}

function Th({ label, col, sort, onSort, num, cls }) {
  if (!col) return <th className={`${num ? 'num' : ''} ${cls || ''}`}>{label}</th>
  const arrow = sort === col ? '▲' : sort === `-${col}` ? '▼' : ''
  return (
    <th className={`th-sort ${num ? 'num' : ''} ${cls || ''}`} onClick={() => onSort(col)}>
      {label} <span className="th-arrow">{arrow}</span>
    </th>
  )
}

export default function TenderTable({ items, mode, onSelect, sort, onSort, loading, showStatus }) {
  const isMatch = mode === 'match'
  const [open, setOpen] = useState(() => new Set())

  function toggle(e, id) {
    e.stopPropagation()
    setOpen((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  if (!loading && items.length === 0) {
    return <div className="empty">Hech narsa topilmadi. Filtrlarni o‘zgartirib ko‘ring.</div>
  }

  return (
    <div className="tablewrap">
      <table className="dtable dtable--dense">
        <thead>
          <tr>
            {isMatch && <th className="num">Ball</th>}
            <th className="col-exp"></th>
            <th>Nima sotib olinadi</th>
            <th className="col-src">Manba</th>
            <th>Buyurtmachi</th>
            <th className="col-reg">Hudud</th>
            <th className="num col-dlv">Yetkazish</th>
            <Th label="Summa" col="totalcost" sort={sort} onSort={onSort} num />
            <Th label="Muddat" col="close_at" sort={sort} onSort={onSort} cls="col-dl" />
          </tr>
        </thead>
        <tbody className={loading ? 'dtable--dim' : ''}>
          {items.map((t) => {
            const d = deadline(t.close_at)
            const m = t.match
            const lots = t.lots_summary || []
            const titled = lots.filter((l) => l.title)
            const isOpen = open.has(t.id)
            const cols = 8 + (isMatch ? 1 : 0)
            const src = SRC[t.source_platform] || { label: t.source_platform, cls: '' }

            // Sarlavha: lot nomlari (eng aniq), bo'lmasa tender nomi
            const title = titled.length > 0
              ? titled.map((l) => l.title).join('  ·  ')
              : (t.name || `#${t.id}`)

            // Ikkinchi qator FAQAT yangi ma'lumot qo'shsa ko'rsatiladi:
            // sarlavhada allaqachon bor mahsulotlarni takrorlamaymiz.
            // (Ilgari bu yerda umumiy kategoriya turardi — foydasiz edi.)
            const extra = (t.goods_preview || [])
              .filter((g) => g && !title.includes(g))
              .slice(0, 3)

            // Yetkazish muddati — lotlar bo'yicha eng uzuni
            const dlv = lots.reduce(
              (mx, l) => (l.delivery_period != null && l.delivery_period > mx ? l.delivery_period : mx), 0)

            return [
              <tr key={t.id} onClick={() => onSelect(t.id)}>
                {isMatch && (
                  <td className="num">
                    <span className={`score ${scoreClass(m?.score ?? 0)}`}>{m?.score ?? 0}</span>
                  </td>
                )}
                <td className="col-exp">
                  {lots.length > 0 && (
                    <button className={`expbtn ${isOpen ? 'expbtn--open' : ''}`}
                            onClick={(e) => toggle(e, t.id)} title={`${lots.length} lot`}>
                      <Icon name="right" size={12} />
                    </button>
                  )}
                </td>

                <td className="cell-name">
                  <div className="cell-name__title" title={title}>
                    {title}
                    {lots.length > 1 && <span className="lotcount">{lots.length} lot</span>}
                    {t.doc_count > 0 && (
                      <span className="docchip" title={`${t.doc_count} ta hujjat`}>
                        <Icon name="clip" size={10} />{t.doc_count}
                      </span>
                    )}
                    {showStatus && (
                      <span className={`badge badge--${t.status} badge--sm`}>
                        {t.status_name || t.status}
                      </span>
                    )}
                  </div>
                  {extra.length > 0 && (
                    <div className="cell-name__goods" title={(t.goods_preview || []).join(', ')}>
                      {extra.join(' · ')}
                    </div>
                  )}
                  {isMatch && m?.matched_keywords?.length > 0 && (
                    <div className="cell-name__kw">
                      {m.matched_keywords.map((k) => <span className="kw" key={k}>{k}</span>)}
                    </div>
                  )}
                </td>

                <td className="col-src">
                  <span className={`srcbadge ${src.cls}`}>{src.label}</span>
                </td>
                <td className="cell-company" title={t.company?.name}>{t.company?.name || '—'}</td>
                <td className="cell-region col-reg" title={t.region?.name}>{t.region?.name || '—'}</td>
                <td className="num col-dlv muted-cell">{dlv ? `${dlv} kun` : '—'}</td>
                <td className="num cell-cost">{shortMoney(t.totalcost, t.currency)}</td>
                <td className="col-dl">
                  <span className={`deadline deadline--${d.level}`}>{d.short}</span>
                </td>
              </tr>,

              isOpen && (
                <tr key={`${t.id}-lots`} className="lotrow">
                  <td colSpan={cols}>
                    {lots.map((l) => (
                      <div className="lotline" key={l.lot_id}>
                        <span className="lotline__no">Lot {l.lot_id}</span>
                        <span className="lotline__title">{l.title || '— nomsiz —'}</span>
                        <span className="lotline__meta">
                          {l.total_sum_lot != null && <b>{shortMoney(l.total_sum_lot, t.currency)}</b>}
                          {l.item_count != null && <span>{l.item_count} pozitsiya</span>}
                          {l.delivery_period != null && <span>yetkazish {l.delivery_period} kun</span>}
                          {l.guarantee != null && <span>kafolat {l.guarantee} kun</span>}
                        </span>
                      </div>
                    ))}
                    {(t.goods_preview || []).length > 0 && (
                      <div className="lotgoods">
                        <span className="lotline__no">Tovar</span>
                        {t.goods_preview.join(' · ')}
                      </div>
                    )}
                  </td>
                </tr>
              ),
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}
