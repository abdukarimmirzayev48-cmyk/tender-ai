import Icon from './Icon'
import { Button } from '@/components/ui/button'

interface PaginationProps {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
}

// Oddiy sahifalash — X-Total-Count'dan hisoblangan sahifalar soni.
export default function Pagination({ page, totalPages, onPrev, onNext }: PaginationProps) {
  if (totalPages <= 1) return null
  return (
    <div className="mt-[18px] flex items-center justify-center gap-4">
      <Button variant="outline" size="sm" onClick={onPrev} disabled={page <= 1}>
        <Icon name="left" size={14} /> Oldingi
      </Button>
      <span className="tabular text-[13px] text-muted-foreground">
        {page} / {totalPages}
      </span>
      <Button variant="outline" size="sm" onClick={onNext} disabled={page >= totalPages}>
        Keyingi <Icon name="right" size={14} />
      </Button>
    </div>
  )
}
