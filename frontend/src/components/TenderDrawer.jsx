import { useEffect, useState } from 'react'
import { api, apiUrl } from '../api.js'
import { money, dateFmt, deadline, sourceUrl, fileSize, ago } from '../format.js'
import Icon from './Icon.jsx'

// O'ng tomondagi tafsilot paneli: lotlar + tovarlar. match berilsa ball/sabab ham.
export default function TenderDrawer({ id, match, onClose }) {
  const [t, setT] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setT(null); setError(null)
    api.tender(id).then(setT).catch((e) => setError(e.message))
  }, [id])

  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const d = t ? deadline(t.close_at) : null

  return (
    <div className="drawer__overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer__bar">
          <span className="drawer__id">#{id}</span>
          <button className="drawer__close" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>

        {error && <div className="alert alert--error">Xatolik: {error}</div>}
        {!t && !error && <div className="drawer__loading">Yuklanmoqda…</div>}

        {t && (
          <div className="drawer__body">
            <div className="drawer__head">
              <span className={`badge badge--${t.status}`}>{t.status_name || t.status}</span>
              {t.status === 'open' && (
                <span className={`deadline deadline--${d.level}`}>{d.text}</span>
              )}
            </div>
            <h2 className="drawer__title">{t.name || `Tender #${t.id}`}</h2>

            {/* Rasmiy sahifaga havola — hujjatlar (texnik topshiriq, xarid
                hujjatlari) faqat o'sha yerda mavjud, ommaviy API bermaydi. */}
            {sourceUrl(t) && (
              <a className="drawer__source" href={sourceUrl(t)} target="_blank" rel="noopener noreferrer">
                Manbada ochish — hujjatlar, talablar, aloqa
                <Icon name="external" size={13} />
              </a>
            )}

            {/* AI TAHLILI — ruscha/texnik matnni o'zbekcha tushunarli qiladi.
                Tahlil qilinmagan bo'lsa (kesh bo'sh) — umuman ko'rsatilmaydi. */}
            {t.ai && (
              <div className="aibox">
                <div className="aibox__head">
                  <Icon name="sparkle" size={13} />
                  <span>AI xulosa</span>
                  {t.ai.category_tags?.map((c) => (
                    <span className="aitag" key={c}>{c}</span>
                  ))}
                </div>
                <p className="aibox__summary">{t.ai.summary_uz}</p>
                {t.ai.supplier_profile && (
                  <div className="aibox__row">
                    <b>Kimga mos:</b> {t.ai.supplier_profile}
                  </div>
                )}
                {t.ai.key_points?.length > 0 && (
                  <ul className="aibox__points">
                    {t.ai.key_points.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                )}
              </div>
            )}

            {match && (
              <div className="drawer__match">
                <div className="drawer__matchscore">Moslik ball: <b>{match.score}</b>/100</div>
                <ul className="drawer__reasons">
                  {match.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            <div className="drawer__grid">
              <Info label="Buyurtmachi" value={t.company?.name} />
              <Info label="Hudud" value={t.region?.name} />
              <Info label="Umumiy summa" value={money(t.totalcost, t.currency)} />
              <Info label="Valyuta" value={t.currency} />
              <Info label="E'lon qilingan" value={dateFmt(t.publicated_at)} />
              <Info label="Ariza deadline" value={dateFmt(t.close_at)} />
              <Info label="Manba" value={t.source_platform} />
              {t.first_seen_at && <Info label="Bizda topildi" value={ago(t.first_seen_at)} />}
              <Info label="Lot / tovar" value={`${t.lot_count || 0} / ${t.good_count || 0}`} />
              {t.detail?.method_marks && <Info label="Baholash usuli" value={t.detail.method_marks} />}
              {t.detail?.close_time && <Info label="Qabul tugash vaqti" value={t.detail.close_time} />}
              {t.detail?.company_details && (
                <Info label="Bank rekvizitlari" value={t.detail.company_details} />
              )}
            </div>

            {/* HUJJATLAR — mahsulotning eng qimmatli qismi: kompaniya texnik
                topshiriqni o'qimasdan ariza bera olmaydi. */}
            {t.document_sections?.length > 0 && (
              <>
                <h3 className="drawer__section">Hujjatlar ({t.doc_count})</h3>
                {t.document_sections.map((s) => (
                  <div className="docgroup" key={s.section}>
                    <div className="docgroup__title">{s.section}</div>
                    {s.files.map((f) => (
                      <a className="docfile" key={f.file_ref || f.file_id} href={apiUrl(f.download_url)}
                         target="_blank" rel="noopener noreferrer">
                        <span className="docfile__ext">{f.file_type || '?'}</span>
                        <span className="docfile__name">{f.name || f.file_id}</span>
                        <span className="docfile__size">{fileSize(f.size_bytes)}</span>
                        <Icon name="download" size={14} className="docfile__dl" />
                      </a>
                    ))}
                  </div>
                ))}
              </>
            )}

            <h3 className="drawer__section">Lotlar va tovarlar</h3>
            {(t.lots || []).length === 0 && <div className="muted">Lot ma'lumoti yo‘q.</div>}

            {(t.lots || []).map((lot) => (
              <div className="lot" key={lot.lot_id}>
                <div className="lot__head">
                  <strong>Lot {lot.lot_id}{lot.title ? ` — ${lot.title}` : ''}</strong>
                  <span className="muted">
                    {lot.goods?.length ?? 0} tovar · {money(lot.total_sum_lot, t.currency)}
                  </span>
                </div>

                {/* Yetkazib berish shartlari — "bajara olamanmi?" savoliga javob */}
                {lot.items?.length > 0 && (
                  <div className="lotterms">
                    {lot.items.map((it) => (
                      <div className="lotterms__row" key={it.item_id}>
                        <span className="lotterms__name">{it.name || it.product_code}</span>
                        {it.delivery_period != null && (
                          <span className="term">Yetkazish: <b>{it.delivery_period} kun</b></span>
                        )}
                        {it.guarantee != null && (
                          <span className="term">Kafolat: <b>{it.guarantee} kun</b></span>
                        )}
                        {it.prod_year && <span className="term">Yili: <b>{it.prod_year}</b></span>}
                        {it.spec && <span className="term">{it.spec}</span>}
                        {it.properties?.length > 0 && (
                          <div className="props">
                            {it.properties.slice(0, 6).map((p, i) => (
                              <span className="prop" key={i}>
                                {p.prop_name}: <b>{String(p.val_name)}</b>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {lot.goods?.length > 0 && (
                  <table className="goods">
                    <thead>
                      <tr><th>Nomi</th><th>Birlik</th><th className="num">Miqdor</th><th className="num">Narx</th></tr>
                    </thead>
                    <tbody>
                      {lot.goods.map((g, i) => (
                        <tr key={g.good_code + i}>
                          <td>{g.name || g.good_code}</td>
                          <td>{g.unit || '—'}</td>
                          <td className="num">{g.amount ?? '—'}</td>
                          <td className="num">{money(g.price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Info({ label, value }) {
  return (
    <div className="info">
      <div className="info__label">{label}</div>
      <div className="info__value">{value || '—'}</div>
    </div>
  )
}
