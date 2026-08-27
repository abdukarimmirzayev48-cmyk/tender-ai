import Icon from './Icon'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'
import type { AiDocsMeta } from '@/types'

// AI TAHLILI QAYSI HUJJATLARGA TAYANGANI
//
// TZ NFR: "foydalanuvchi natija qanday ma'lumotlarga asoslanganini ko'rishi
// kerak — qora quti bo'lmasligi kerak". AI endi biriktirilgan hujjat matnini
// o'qiydi, lekin hujjatlar 400 000 belgigacha bo'ladi va promptga faqat
// TALAB O'ZAKLARI atrofidagi bo'laklar sig'adi. Ya'ni tahlil deyarli
// har doim QISMAN ma'lumotga asoslanadi.
//
// Buni yashirish xato bo'lardi: broker "AI hujjatni to'liq o'qidi" deb
// o'ylab, o'zi tekshirishni tashlab qo'yardi. Shuning uchun bu qator
// har tahlil ostida turadi va qanchasi o'qilganini ochiq aytadi.
export default function AiDocsNote({ meta }: { meta?: AiDocsMeta | null }) {
  const t = useT()
  if (!meta) return null

  const used = meta.used?.length || 0
  const unreadable = meta.unreadable?.length || 0

  // Hujjat umuman yo'q — bu ham ma'lumot: tahlil faqat kartochkaga tayangan
  if (!used && !unreadable) {
    return (
      <div className="text-micro text-muted-foreground">{t('aidocs.none')}</div>
    )
  }

  const problem = !used || meta.truncated || unreadable > 0

  return (
    <details className="text-micro">
      <summary className={cn('cursor-pointer', problem ? 'text-soon-strong' : 'text-muted-foreground')}>
        <Icon name="clip" size={10} className="mr-1" />
        {used > 0 ? t('aidocs.used', { n: used }) : t('aidocs.noneReadable')}
        {meta.truncated && ` · ${t('aidocs.truncated')}`}
        {unreadable > 0 && ` · ${t('aidocs.unreadable', { n: unreadable })}`}
      </summary>

      <div className="mt-1 space-y-0.5 rounded-md bg-muted p-2">
        {(meta.used || []).map((u) => (
          <div key={u.name} className="flex flex-wrap items-baseline gap-1.5">
            <Icon name="check" size={9} className="text-ok-strong" />
            <span className="min-w-0 flex-1 truncate" title={u.name}>{u.name}</span>
            <span className="tabular shrink-0 text-muted-foreground">
              {u.partial
                ? t('aidocs.partial', {
                    pct: Math.max(1, Math.round((u.chars_used / u.chars_total) * 100)),
                  })
                : t('aidocs.full')}
            </span>
          </div>
        ))}
        {(meta.unreadable || []).map((u) => (
          <div key={u.name} className="flex flex-wrap items-baseline gap-1.5 text-soon-strong">
            <Icon name="alert" size={9} />
            <span className="min-w-0 flex-1 truncate" title={u.name}>{u.name}</span>
            <span className="shrink-0">{t('aidocs.notRead')}</span>
          </div>
        ))}
        {meta.truncated && (
          <p className="pt-1 text-muted-foreground">{t('aidocs.truncatedHint')}</p>
        )}
      </div>
    </details>
  )
}
