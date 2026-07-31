import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
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
const MANUAL = { dot: 'bg-soon', label: 'Qo‘lda tekshiring' }
const STATUS: Record<string, { dot: string; label: string }> = {
  ok: { dot: 'bg-ok', label: 'O‘qildi' },
  unreadable: MANUAL,
  unsupported: MANUAL,
  too_large: MANUAL,
  download_failed: MANUAL,
  pending: { dot: 'bg-border', label: 'Ishlanmagan' },
}

const fmt = (n: number | null | undefined) =>
  (typeof n === 'number' ? n.toLocaleString('ru-RU') : null)

export default function DocumentText({ tenderId }: { tenderId: number }) {
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
      <div className="mb-4 rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
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
        <div className="text-[13px] font-semibold">Hujjat matni</div>
        <div className="ml-auto flex gap-1.5">
          {s.ok > 0 && (
            <span className="rounded bg-ok-soft px-1.5 py-0.5 text-[11px] font-semibold text-ok">
              {s.ok} o‘qildi
            </span>
          )}
          {s.manual_review > 0 && (
            <span className="rounded bg-soon-soft px-1.5 py-0.5 text-[11px] font-semibold text-soon">
              {s.manual_review} qo‘lda
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
                <div className="truncate text-[13px] font-medium" title={d.name || d.file_ref}>
                  {d.name || d.file_ref}
                </div>
                <div className="flex flex-wrap items-center gap-x-1.5 text-[12px] text-muted-foreground">
                  <span>{st.label}</span>
                  {d.status === 'ok' && d.char_count != null && <span>· {fmt(d.char_count)} belgi</span>}
                  {d.status === 'ok' && d.page_count != null && <span>· {d.page_count} sahifa</span>}
                  {/* Sabab — nega o'qilmadi. Foydalanuvchi keyingi qadamini
                      shundan tanlaydi (arxivni ochish / skanni ko'z bilan o'qish). */}
                  {d.status !== 'ok' && d.reason && <span className="text-soon">· {d.reason}</span>}
                  {d.status === 'ok' && d.preview && (
                    <button
                      className="ml-1 text-primary underline-offset-2 hover:underline"
                      onClick={() => setOpen(isOpen ? null : d.file_ref)}
                    >
                      {isOpen ? 'Yopish' : 'Matnni ko‘rish'}
                    </button>
                  )}
                </div>
                {isOpen && (
                  <div className="mt-1.5 max-h-[240px] overflow-y-auto whitespace-pre-wrap rounded-md bg-muted p-2.5 text-[12px] leading-relaxed">
                    {d.preview}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {s.manual_review > 0 && (
        <div className="flex items-center gap-1.5 border-t bg-soon-soft px-3 py-2 text-[12px] text-soon">
          <Icon name="clip" size={12} />
          {s.manual_review} ta fayl avtomatik o‘qilmadi — yuklab olib ko‘ring.
        </div>
      )}
    </Card>
  )
}
