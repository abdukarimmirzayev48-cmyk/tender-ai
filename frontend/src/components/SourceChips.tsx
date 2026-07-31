import Icon from './Icon'
import { cn } from '@/lib/utils'

// Manba-platforma chiplari.
const PLATFORMS = [
  { id: 'xt-xarid', label: 'xt-xarid.uz', ready: true },
  { id: 'uzex', label: 'etender.uzex.uz', ready: true },
  { id: 'e-auksion', label: 'e-auksion.uz', ready: false },
]

interface SourceChipsProps {
  selected: string[]
  onToggle: (id: string) => void
}

export default function SourceChips({ selected, onToggle }: SourceChipsProps) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-semibold text-muted-foreground">
        Manbalar:
      </span>
      {PLATFORMS.map((p) => {
        const on = p.ready && selected.includes(p.id)
        return (
          <button
            key={p.id}
            type="button"
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px]',
              'transition-colors',
              p.ready && 'cursor-pointer hover:bg-accent',
              on
                ? 'border-primary bg-secondary font-semibold text-primary'
                : 'border-border bg-card text-foreground',
              !p.ready && 'cursor-not-allowed opacity-55',
            )}
            disabled={!p.ready}
            onClick={() => p.ready && onToggle(p.id)}
            title={p.ready ? 'Manbani yoqish/o‘chirish' : 'Tez orada qo‘shiladi'}
          >
            {on
              ? <Icon name="check" size={13} />
              : <span className="size-[7px] rounded-full bg-border" />}
            {p.label}
            {!p.ready && (
              <span className="rounded bg-muted px-1.5 py-px text-[10px] text-muted-foreground">
                tez orada
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
