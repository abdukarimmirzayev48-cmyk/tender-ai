import Icon from './Icon'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'
import type { ToolEvent } from '@/hooks/useChatStream'

// TOOL INDIKATORI — "AI o'ylab topdimi yoki hujjatdan o'qidimi?"
//
// NEGA KERAK: bu loyihaning "qora quti bo'lmasin" tamoyilining chatdagi
// ko'rinishi. Foydalanuvchi javobning QAYSI MANBAGA tayanganini ekranda
// ko'rishi kerak — modelning so'ziga ishonib emas.
//
// Tool nomlari TARJIMA QILINADI: `search_documents` foydalanuvchiga hech
// nima demaydi, "Hujjatlarni o'qiyapman" esa deydi.

/** Tool -> (i18n kaliti, ikon). Noma'lum tool nomi bilan ko'rsatiladi. */
const TOOLS: Record<string, { key: string; icon: string }> = {
  search_tenders: { key: 'chat.tool.searchTenders', icon: 'search' },
  get_tender: { key: 'chat.tool.getTender', icon: 'tenders' },
  search_documents: { key: 'chat.tool.searchDocuments', icon: 'clip' },
  compare_tenders: { key: 'chat.tool.compareTenders', icon: 'grid' },
  check_stock: { key: 'chat.tool.checkStock', icon: 'box' },
  calc_price: { key: 'chat.tool.calcPrice', icon: 'briefcase' },
  check_compliance: { key: 'chat.tool.checkCompliance', icon: 'checklist' },
  run_gonogo: { key: 'chat.tool.runGonogo', icon: 'sparkle' },
  get_my_catalog: { key: 'chat.tool.getMyCatalog', icon: 'grid' },
}

export default function ToolBadge({ tool }: { tool: ToolEvent }) {
  const t = useT()
  const meta = TOOLS[tool.name]
  const label = meta ? t(meta.key as never) : tool.name
  const ishlayapti = tool.status === 'start'
  const xato = tool.status === 'error'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs',
        xato
          ? 'border-urgent/40 bg-urgent-soft text-urgent'
          : ishlayapti
            ? 'border-accent/40 bg-accent-soft text-accent'
            : 'border-border bg-muted text-muted-foreground',
      )}
      // Xato bo'lsa sabab ko'rinsin — jimgina "tugadi" deb ko'rsatmaymiz.
      title={xato ? t('chat.tool.failed') : label}
    >
      <Icon
        name={(meta?.icon ?? 'sparkle') as never}
        size={12}
        // Ishlayotgan tool AYLANADI — statik ro'yxatdan farqlanadi.
        className={ishlayapti ? 'animate-spin' : undefined}
      />
      {label}
      {xato && <span aria-hidden>!</span>}
    </span>
  )
}
