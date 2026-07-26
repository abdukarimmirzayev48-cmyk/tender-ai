import { useState } from 'react'
import { api } from '../api.js'
import Icon from './Icon.jsx'
import { money } from '../format.js'

// Mahsulot katalogi: mijoz sotadigan mahsulot/xizmatlar. Har biriga kategoriya
// biriktiriladi -> "Sizga mos" shu katalogга qarab tenderlarni topadi.
export default function CatalogView({ items, categories, onChanged, onOpenMatch }) {
  const [editing, setEditing] = useState(null) // null | 'new' | product

  return (
    <div className="catalogview">
      <div className="catalogview__head">
        <p className="panel__hint" style={{ margin: 0 }}>
          Nima sotasiz? Mahsulot/xizmatlaringizni kategoriyasi bilan kiriting —
          "Sizga mos" ularга mos tenderlarni avtomatik topadi.
        </p>
        <button className="btn btn--primary btn--icon" onClick={() => setEditing('new')}>
          <Icon name="plus" size={14} /> Mahsulot qo‘shish
        </button>
      </div>

      {editing && (
        <ProductForm
          product={editing === 'new' ? null : editing}
          categories={categories}
          onSaved={() => { setEditing(null); onChanged() }}
          onCancel={() => setEditing(null)}
        />
      )}

      {items.length === 0 && !editing && (
        <div className="empty">Katalog bo‘sh. Birinchi mahsulotingizni qo‘shing.</div>
      )}

      {items.length > 0 && (
        <table className="dtable dtable--dense catalogtable">
          <thead>
            <tr>
              <th>Mahsulot / xizmat</th>
              <th className="col-cat">Kategoriya</th>
              <th className="num">Narx</th>
              <th className="num">Mos tender</th>
              <th className="col-act"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td className="cell-name">
                  <div className="cell-name__title">{p.name}</div>
                  {p.keywords.length > 0 && (
                    <div className="cell-name__goods">{p.keywords.join(' · ')}</div>
                  )}
                </td>
                <td className="col-cat muted-cell">{catName(categories, p.category_code)}</td>
                <td className="num">{p.price != null ? money(p.price, p.currency) : '—'}
                  {p.unit ? <span className="muted-cell"> /{p.unit}</span> : null}</td>
                <td className="num">
                  {p.match_count > 0 ? (
                    <button className="linkcount" onClick={() => onOpenMatch(p)}>
                      {p.match_count}
                    </button>
                  ) : <span className="muted-cell">0</span>}
                </td>
                <td className="col-act">
                  <button className="saved__act" title="Tahrirlash" onClick={() => setEditing(p)}>
                    <Icon name="edit" size={13} />
                  </button>
                  <button className="saved__act" title="O‘chirish"
                    onClick={async () => {
                      if (!window.confirm(`"${p.name}" o‘chirilsinmi?`)) return
                      await api.deleteProduct(p.id); onChanged()
                    }}>
                    <Icon name="trash" size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function catName(tree, code) {
  if (!code) return '— kategoriyasiz —'
  for (const p of tree) {
    if (p.code === code) return p.name
    for (const c of p.children) if (c.code === code) return c.name
  }
  return code
}

// Mahsulot qo'shish/tahrirlash formasi
function ProductForm({ product, categories, onSaved, onCancel }) {
  const editing = !!product?.id
  const [name, setName] = useState(product?.name || '')
  const [cat, setCat] = useState(product?.category_code || '')
  const [price, setPrice] = useState(product?.price ?? '')
  const [unit, setUnit] = useState(product?.unit || '')
  const [currency, setCurrency] = useState(product?.currency || 'UZS')
  const [keywords, setKeywords] = useState(product?.keywords || [])
  const [kwInput, setKwInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  function addKw() {
    const v = kwInput.trim()
    if (v && !keywords.includes(v)) setKeywords([...keywords, v])
    setKwInput('')
  }

  async function save() {
    if (!name.trim()) { setMsg('Mahsulot nomini kiriting.'); return }
    setSaving(true); setMsg(null)
    const body = {
      name: name.trim(), category_code: cat || null, keywords,
      unit: unit || null, price: price === '' ? null : Number(price),
      currency: currency || null, notify: true,
    }
    try {
      if (editing) await api.updateProduct(product.id, body)
      else await api.createProduct(body)
      onSaved()
    } catch (e) { setMsg('Xatolik: ' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="panel panel--inline">
      <h3 className="panel__title">{editing ? 'Mahsulotni tahrirlash' : 'Yangi mahsulot / xizmat'}</h3>
      <div className="field-row">
        <label className="field field--grow">
          <span className="field__label">Nomi *</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="masalan: Ofis mebeli, Yo‘l qurilishi xizmati" />
        </label>
        <label className="field">
          <span className="field__label">Kategoriya</span>
          <select className="input" value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">— tanlang —</option>
            {categories.map((p) => (
              <optgroup key={p.code} label={p.name}>
                <option value={p.code}>{p.name} (hammasi)</option>
                {p.children.map((c) => <option key={c.code} value={c.code}>— {c.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
      </div>

      <div className="field-row">
        <label className="field">
          <span className="field__label">Narx (ixtiyoriy)</span>
          <input className="input" type="number" value={price}
            onChange={(e) => setPrice(e.target.value)} placeholder="0" />
        </label>
        <label className="field">
          <span className="field__label">Valyuta</span>
          <select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            <option value="UZS">UZS</option><option value="USD">USD</option>
          </select>
        </label>
        <label className="field">
          <span className="field__label">Birlik</span>
          <input className="input" value={unit} onChange={(e) => setUnit(e.target.value)}
            placeholder="dona, m², xizmat" />
        </label>
      </div>

      <label className="field">
        <span className="field__label">Qo‘shimcha kalit so‘zlar (ixtiyoriy)</span>
        <div className="tagfield">
          {keywords.map((k) => (
            <span className="tag" key={k}>{k}
              <button onClick={() => setKeywords(keywords.filter((x) => x !== k))}>×</button></span>
          ))}
          <input className="tagfield__input" value={kwInput}
            onChange={(e) => setKwInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addKw() } }}
            onBlur={addKw} placeholder="монитор, стол… (Enter)" />
        </div>
        <span className="field__note">Kategoriyaga qo‘shimcha — aniq nom bo‘yicha ham moslashtiradi.</span>
      </label>

      <div className="panel__actions">
        <button className="btn btn--primary" onClick={save} disabled={saving}>
          {saving ? 'Saqlanmoqda…' : (editing ? 'Yangilash' : 'Qo‘shish')}
        </button>
        <button className="btn btn--ghost" onClick={onCancel}>Bekor qilish</button>
        {msg && <span className="panel__msg">{msg}</span>}
      </div>
    </div>
  )
}
