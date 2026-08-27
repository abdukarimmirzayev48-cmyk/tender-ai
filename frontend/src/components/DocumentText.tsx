import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { useT } from '@/i18n'
import { useFormat } from '@/format'
import type { TKey } from '@/i18n'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { DocumentTextResult } from '@/types'

// HUJJAT MATNI HOLATI (TZ P0-2)
//
// NIMA QILADI: tenderga biriktirilgan har bir fayl uchun "matni o'qildimi"
// degan savolga javob beradi va o'qilganini shu yerda ko'rsatadi.
//
// TZ QABUL QILISH MEZONI: "o'qib bo'lmaydigan fayllar 'qo'lda tekshirish
// talab etiladi' deb belgilanadi" — shuning uchun 'ok' dan boshqa HAR QANDAY
// status sariq ogohlantirish bo'lib chiqadi va SABABI ham ko'rsatiladi.
//
// AI/model chaqiruvi YO'Q — ma'lumot deterministik parserlardan keladi.
const MANUAL: { dot: string; label: TKey } = { dot: 'bg-soon', label: 'doctext.manual' }
const STATUS: Record<string, { dot: string; label: TKey }> = {
  ok: { dot: 'bg-ok', label: 'doctext.read' },
  unreadable: MANUAL,
  unsupported: MANUAL,
  too_large: MANUAL,
  download_failed: MANUAL,
  pending: { dot: 'bg-border', label: 'doctext.pending' },
}

export default function DocumentText({ tenderId }: { tenderId: number }) {
  const t = useT()
  const f = useFormat()
  const [data, setData] = useState<DocumentTextResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)   // ochilgan hujjatning file_ref i

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null); setData(null); setOpen(null)
    api.documentsText(tenderId)
      .then((d) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [tenderId])

  if (loading) return <Skeleton className="mb-4 h-20 w-full rounded-lg" />
  if (error) {
    return (
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-body text-urgent-strong">
        {error}
      </div>
    )
  }

  const docs = data?.documents || []
  if (!docs.length) return null   // hujjatsiz tenderda bo'sh blok ko'rsatmaymiz

  const s = data!.summary

  return (
    <Card className="mb-4 overflow-hidden">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <div className="text-body font-semibold">{t('doctext.title')}</div>
        <div className="ml-auto flex gap-1.5">
          {s.ok > 0 && (
            <span className="rounded bg-ok-soft px-1.5 py-0.5 text-micro font-semibold text-ok-strong">
              {t('doctext.okCount', { n: s.ok })}
            </span>
          )}
          {s.manual_review > 0 && (
            <span className="rounded bg-soon-soft px-1.5 py-0.5 text-micro font-semibold text-soon-strong">
              {t('doctext.manualCount', { n: s.manual_review })}
            </span>
          )}
        </div>
      </div>

      <ul className="divide-y divide-border-soft">
        {docs.map((d) => {
          const st = STATUS[d.status] || STATUS.pending
          const isOpen = open === d.file_ref
          return (
            <li className="flex gap-2.5 px-3 py-2" key={d.file_ref}>
              <span className={cn('mt-1.5 size-2 shrink-0 rounded-full', st.dot)} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-body font-medium" title={d.name || d.file_ref}>
                  {d.name || d.file_ref}
                </div>
                <div className="flex flex-wrap items-center gap-x-1.5 text-caption text-muted-foreground">
                  <span>{t(st.label)}</span>
                  {d.status === 'ok' && d.char_count != null && (
                    <span>· {t('doctext.chars', { n: f.num(d.char_count) })}</span>
                  )}
                  {d.status === 'ok' && d.page_count != null && (
                    <span>· {t('doctext.pages', { n: d.page_count })}</span>
                  )}
                  {/* Sabab — nega o'qilmadi. Foydalanuvchi keyingi qadamini
                      shundan tanlaydi (arxivni ochish / skanni ko'z bilan o'qish). */}
                  {d.status !== 'ok' && d.reason && <span className="text-soon-strong">· {d.reason}</span>}
                  {d.status === 'ok' && d.preview && (
                    <button
                      className="ml-1 text-primary underline-offset-2 hover:underline"
                      onClick={() => setOpen(isOpen ? null : d.file_ref)}
                    >
                      {t(isOpen ? 'common.close' : 'doctext.showText')}
                    </button>
                  )}
                </div>
                {isOpen && (
                  <div className="mt-1.5 max-h-[240px] overflow-y-auto whitespace-pre-wrap rounded-md bg-muted p-2.5 text-caption leading-relaxed">
                    {d.preview}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {s.manual_review > 0 && (
        <div className="flex items-center gap-1.5 border-t bg-soon-soft px-3 py-2 text-caption text-soon-strong">
          <Icon name="clip" size={12} />
          {t('doctext.footer', { n: s.manual_review })}
        </div>
      )}
    </Card>
  )
}
