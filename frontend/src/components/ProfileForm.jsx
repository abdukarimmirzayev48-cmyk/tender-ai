import { useState } from 'react'
import { api } from '../api.js'

// Saqlangan qidiruv muharriri. `search` berilsa — tahrirlaydi, aks holda yangi.
export default function ProfileForm({ search, regions, onSaved, onCancel }) {
  const editing = !!search?.id
  const [name, setName] = useState(search?.name || '')
  const [keywords, setKeywords] = useState(search?.keywords || [])
  const [kwInput, setKwInput] = useState('')
  const [selRegions, setSelRegions] = useState(search?.regions || [])
  const [currency, setCurrency] = useState(search?.currency || '')
  const [minCost, setMinCost] = useState(search?.min_cost ?? '')
  const [maxCost, setMaxCost] = useState(search?.max_cost ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  function addKw() {
    const v = kwInput.trim()
    if (v && !keywords.includes(v)) setKeywords([...keywords, v])
    setKwInput('')
  }
  function removeKw(k) { setKeywords(keywords.filter((x) => x !== k)) }
  function toggleRegion(id) {
    setSelRegions((r) => r.includes(id) ? r.filter((x) => x !== id) : [...r, id])
  }

  async function save() {
    if (!name.trim()) { setMsg('Qidiruvga nom bering.'); return }
    setSaving(true); setMsg(null)
    const body = {
      name: name.trim(),
      keywords,
      regions: selRegions,
      currency: currency || null,
      min_cost: minCost === '' ? null : Number(minCost),
      max_cost: maxCost === '' ? null : Number(maxCost),
    }
    try {
      if (editing) await api.updateSearch(search.id, body)
      else await api.createSearch(body)
      onSaved?.()
    } catch (e) {
      setMsg('Xatolik: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="panel">
      <h2 className="panel__title">{editing ? 'Qidiruvni tahrirlash' : 'Yangi saqlangan qidiruv'}</h2>
      <p className="panel__hint">
        Nima izlayapsiz? Saqlangach chap panelda paydo bo‘ladi va mos tenderlar
        soni ko‘rsatiladi. Bir bosishда qaytadi.
      </p>

      <label className="field">
        <span className="field__label">Qidiruv nomi *</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)}
          placeholder="masalan: Kompyuter texnikasi" />
      </label>

      <label className="field">
        <span className="field__label">Kalit so‘zlar (nima sotasiz)</span>
        <div className="tagfield">
          {keywords.map((k) => (
            <span className="tag" key={k}>{k}<button onClick={() => removeKw(k)}>×</button></span>
          ))}
          <input
            className="tagfield__input"
            value={kwInput}
            onChange={(e) => setKwInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addKw() } }}
            onBlur={addKw}
            placeholder="мебель, компьютер, услуги… (Enter)"
          />
        </div>
        <span className="field__note">
          Hozircha ruscha yozing (ma'lumot ruscha/kirill). AI ulanganда o‘zbekcha ham ishlaydi.
        </span>
      </label>

      <div className="field">
        <span className="field__label">Hududlar (bo‘sh = butun respublika)</span>
        <div className="regiongrid">
          {regions.map((r) => (
            <label className="regionopt" key={r.area_id}>
              <input type="checkbox" checked={selRegions.includes(r.area_id)}
                onChange={() => toggleRegion(r.area_id)} />
              {r.name}
            </label>
          ))}
        </div>
      </div>

      <div className="field-row">
        <label className="field">
          <span className="field__label">Afzal valyuta</span>
          <select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            <option value="">Farqsiz</option>
            <option value="UZS">UZS</option>
            <option value="USD">USD</option>
          </select>
        </label>
        <label className="field">
          <span className="field__label">Min byudjet</span>
          <input className="input" type="number" value={minCost}
            onChange={(e) => setMinCost(e.target.value)} placeholder="0" />
        </label>
        <label className="field">
          <span className="field__label">Max byudjet</span>
          <input className="input" type="number" value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)} placeholder="cheksiz" />
        </label>
      </div>

      <div className="panel__actions">
        <button className="btn btn--primary" onClick={save} disabled={saving}>
          {saving ? 'Saqlanmoqda…' : (editing ? 'Yangilash' : 'Saqlash')}
        </button>
        <button className="btn btn--ghost" onClick={onCancel}>Bekor qilish</button>
        {msg && <span className="panel__msg">{msg}</span>}
      </div>
    </div>
  )
}
