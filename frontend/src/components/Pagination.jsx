import Icon from './Icon.jsx'

// Oddiy sahifalash — X-Total-Count'dan hisoblangan sahifalar soni.
export default function Pagination({ page, totalPages, onPrev, onNext }) {
  if (totalPages <= 1) return null
  return (
    <div className="pagination">
      <button className="btn btn--icon" onClick={onPrev} disabled={page <= 1}>
        <Icon name="left" size={14} /> Oldingi
      </button>
      <span className="pagination__info">{page} / {totalPages}</span>
      <button className="btn btn--icon" onClick={onNext} disabled={page >= totalPages}>
        Keyingi <Icon name="right" size={14} />
      </button>
    </div>
  )
}
