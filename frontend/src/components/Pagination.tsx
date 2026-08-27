import Icon from './Icon'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'

interface PaginationProps {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
}

// Oddiy sahifalash — X-Total-Count'dan hisoblangan sahifalar soni.
export default function Pagination({ page, totalPages, onPrev, onNext }: PaginationProps) {
  const t = useT()
  if (totalPages <= 1) return null
  return (
    <nav className="mt-4 flex items-center justify-center gap-4" aria-label={t('page.label')}>
      <Button variant="outline" size="sm" onClick={onPrev} disabled={page <= 1}>
        <Icon name="left" size={14} /> {t('page.prev')}
      </Button>
      {/* `aria-live` — sahifa almashganda ekran o'quvchi yangi holatni
          o'qiydi. Usiz tugma bosiladi-yu, hech narsa aytilmaydi. */}
      <span className="tabular text-body text-muted-foreground" aria-live="polite">
        {t('page.of', { page, total: totalPages })}
      </span>
      <Button variant="outline" size="sm" onClick={onNext} disabled={page >= totalPages}>
        {t('page.next')} <Icon name="right" size={14} />
      </Button>
    </nav>
  )
}
