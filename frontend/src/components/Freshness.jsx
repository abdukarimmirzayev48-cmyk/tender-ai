import { useState, useRef, useEffect } from 'react'
import { agoSec } from '../format.js'

const SRC_LABEL = { 'xt-xarid': 'xt-xarid', 'uzex': 'etender.uzex' }

// Ma'lumot yangiligi ko'rsatkichi (H bosqich). Yashil = yangi + xatосиз,
// sariq = eskirgan (>2 soat), qizil = biror manbaда xato.
export default function Freshness({ data }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  if (!data) return null
  const age = data.overall_age_sec
  const level = data.any_error ? 'urgent' : (age != null && age > 7200 ? 'soon' : 'ok')

  return (
    <div className="fresh" ref={ref}>
      <button className="fresh__btn" onClick={() => setOpen((o) => !o)}>
        <span className={`fresh__dot fresh__dot--${level}`} />
        <span className="fresh__text">
          {data.any_error ? 'ETL xatosi' : `Yangilangan: ${agoSec(age)}`}
        </span>
      </button>

      {open && (
        <div className="fresh__pop">
          <div className="fresh__row fresh__row--head">Manbalar holati</div>
          {data.platforms.map((p) => (
            <div className="fresh__row" key={p.source_platform}>
              <span className={`fresh__dot fresh__dot--${p.status === 'error' ? 'urgent' : 'ok'}`} />
              <span className="fresh__name">{SRC_LABEL[p.source_platform] || p.source_platform}</span>
              <span className="fresh__age">
                {p.status === 'error' ? 'xato' : agoSec(p.age_sec)}
                {p.new > 0 && <span className="fresh__new">+{p.new} yangi</span>}
              </span>
            </div>
          ))}
          {data.detection?.sample > 0 && (
            <div className="fresh__det">
              Aniqlash-kechikishi (median): <b>{data.detection.median_hours} soat</b>
              {data.detection.within_1h_pct != null &&
                <> · 1 soatда: {data.detection.within_1h_pct}%</>}
              <div className="fresh__hint">
                Avtomatik soatlik yangilash yoqilgach aniqlashadi.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
