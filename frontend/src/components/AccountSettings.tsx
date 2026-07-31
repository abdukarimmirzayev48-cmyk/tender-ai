import { useCallback, useState } from 'react'
import Icon from './Icon'
import CompanyProfile from './CompanyProfile'
import type { Section, SectionProgress } from './CompanyProfile'
import NotifySettings from './NotifySettings'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { CompanyProfileData } from '@/types'

// AKKAUNT SOZLAMALARI — kategoriyalarga bo'lingan menyu.
//
// NEGA MENYU: ilgari butun akkaunt bitta uzun sahifada edi (aloqa, kompaniya,
// salohiyat, tender mezonlari, email va Telegram — hammasi ketma-ket).
// "Minimal foyda"ni topish uchun ekranni to'liq aylantirish kerak edi.
//
// KATTA QAROR: profil paneli DOIM mount holida qoladi (`hidden` bilan
// yashiriladi), chunki bo'lim almashtirish SAQLANMAGAN o'zgarishlarni yo'q
// qilmasligi kerak. Bildirishnoma paneli esa birinchi ochilgunicha umuman
// mount qilinmaydi — u ochilishida Telegram Bot API ga so'rov yuboradi.
const SECTIONS: { key: Section | 'notify'; icon: string; label: string; hint: string }[] = [
  { key: 'profile', icon: 'user', label: 'Profil', hint: 'Ism, aloqa' },
  { key: 'company', icon: 'briefcase', label: 'Kompaniya', hint: 'Faoliyat, sertifikat' },
  { key: 'capacity', icon: 'stats', label: 'Salohiyat', hint: 'Tajriba, resurs, hudud' },
  { key: 'criteria', icon: 'match', label: 'Tender mezonlari', hint: 'Summa, foyda, cheklov' },
  { key: 'notify', icon: 'bell', label: 'Bildirishnoma', hint: 'Email, Telegram' },
]

interface AccountSettingsProps {
  onSaved?: (p: CompanyProfileData) => void
}

export default function AccountSettings({ onSaved }: AccountSettingsProps) {
  const [section, setSection] = useState<Section | 'notify'>('profile')
  const [notifySeen, setNotifySeen] = useState(false)
  // Bo'lim bo'yicha to'ldirilgan Go/No-Go mezonlari — menyudagi rozetka.
  const [prog, setProg] = useState<Record<string, SectionProgress>>({})

  // `useCallback` SHART: `CompanyProfile` buni `useEffect` bog'liqligida
  // ishlatadi. Har renderda yangi funksiya bo'lsa effekt cheksiz aylanardi.
  const onProgress = useCallback((m: Record<string, SectionProgress>) => setProg(m), [])

  const done = Object.values(prog).reduce((s, x) => s + x.done, 0)
  const total = Object.values(prog).reduce((s, x) => s + x.total, 0)
  const isNotify = section === 'notify'
  const current = SECTIONS.find((s) => s.key === section)

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[236px_minmax(0,1fr)]">
      {/* `Card` — oddiy `div` (Vengeance UI'da `asChild` yo'q), shuning uchun
          semantik teg ustiga uning sinflari qo'lda qo'yiladi. */}
      <nav
        aria-label="Akkaunt sozlamalari"
        className="sticky top-4 rounded-xl border bg-card p-2 text-card-foreground shadow-sm max-lg:static max-lg:flex max-lg:overflow-x-auto"
      >
          {SECTIONS.map((s) => {
            const pr = prog[s.key]
            const on = section === s.key
            return (
              <button key={s.key} type="button"
                className={cn(
                  'flex w-full shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors',
                  on ? 'bg-secondary text-primary' : 'hover:bg-accent',
                )}
                aria-current={on ? 'page' : undefined}
                onClick={() => {
                  setSection(s.key)
                  if (s.key === 'notify') setNotifySeen(true)
                }}>
                <Icon name={s.icon} size={16} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-semibold leading-tight">{s.label}</span>
                  <span className={cn('truncate text-[11px] leading-tight max-lg:hidden',
                    on ? 'text-primary/75' : 'text-muted-foreground')}>{s.hint}</span>
                </span>
                {/* Rozetka faqat mezon yopadigan bo'limlarda. To'liq bo'lsa yashil. */}
                {pr && (
                  <span className={cn(
                    'tabular shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold',
                    pr.done === pr.total ? 'bg-ok-soft text-ok' : 'bg-muted text-muted-foreground',
                  )} title="To‘ldirilgan Go/No-Go mezonlari">
                    {pr.done}/{pr.total}
                  </span>
                )}
              </button>
            )
          })}

          {total > 0 && (
            <div className="mt-1.5 border-t px-2.5 pb-1 pt-2.5 max-lg:hidden"
              title="Go/No-Go qarori uchun to‘ldirilgan mezonlar">
              <div className="mb-1.5 flex items-baseline justify-between text-[11px] text-muted-foreground">
                <span>Profil to‘liqligi</span>
                <b className="tabular text-foreground">{done}/{total}</b>
              </div>
              <Progress value={(done / total) * 100} className="h-1.5" />
            </div>
          )}
      </nav>

      <section
        aria-label={current?.label}
        className="min-w-0 rounded-xl border bg-card p-5 text-card-foreground shadow-sm"
      >
        <h2 className="mb-3 text-[17px] font-bold">{current?.label}</h2>

        <div hidden={isNotify}>
          <CompanyProfile section={section as Section} onSaved={onSaved} onProgress={onProgress} />
        </div>
        {notifySeen && (
          <div hidden={!isNotify}>
            <NotifySettings />
          </div>
        )}
      </section>
    </div>
  )
}
