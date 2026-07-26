import Icon from './Icon.jsx'

// Manba-platforma chiplari (numeo.ai'dagi broker chiplari analogi).
const PLATFORMS = [
  { id: 'xt-xarid', label: 'xt-xarid.uz', ready: true },
  { id: 'uzex', label: 'etender.uzex.uz', ready: true },
  { id: 'e-auksion', label: 'e-auksion.uz', ready: false },
]

export default function SourceChips({ selected, onToggle }) {
  return (
    <div className="chips">
      <span className="chips__label">Manbalar:</span>
      {PLATFORMS.map((p) => {
        const on = p.ready && selected.includes(p.id)
        return (
          <button
            key={p.id}
            className={`chip-src ${on ? 'chip-src--on' : ''} ${!p.ready ? 'chip-src--soon' : ''}`}
            disabled={!p.ready}
            onClick={() => p.ready && onToggle(p.id)}
            title={p.ready ? 'Manbani yoqish/o‘chirish' : 'Tez orada qo‘shiladi'}
          >
            {on ? <Icon name="check" size={13} className="chip-src__check" /> : <span className="chip-src__dot" />}
            {p.label}
            {!p.ready && <span className="chip-src__soon">tez orada</span>}
          </button>
        )
      })}
    </div>
  )
}
