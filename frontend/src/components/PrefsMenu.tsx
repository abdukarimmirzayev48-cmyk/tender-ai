import { useState } from 'react'
import Icon from './Icon'
import { LANGS, useI18n } from '@/i18n'
import { useTheme } from '@/theme'
import type { ThemeChoice } from '@/theme'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

// TIL VA MAVZU SOZLAMALARI — yon panelning pastida, akkaunt yonida.
//
// NEGA BITTA MENYUDA: ikkalasi ham "ilova qanday ko'rinadi" degan sozlama va
// ikkalasi ham kamdan-kam o'zgartiriladi. Alohida ikki tugma yuqori qatorni
// egallab, kundalik ishdan (qidiruv, filtr) diqqatni tortardi.
export default function PrefsMenu() {
  const { lang, setLang, t } = useI18n()
  const { choice, resolved, setChoice } = useTheme()
  const [open, setOpen] = useState(false)

  const THEMES: { value: ThemeChoice; icon: string; label: string }[] = [
    { value: 'light', icon: 'sun', label: t('prefs.themeLight') },
    { value: 'dark', icon: 'moon', label: t('prefs.themeDark') },
    { value: 'system', icon: 'monitor', label: t('prefs.themeSystem') },
  ]

  const row = 'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-body transition-colors hover:bg-accent'
  const sel = 'bg-secondary font-semibold text-primary'

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn('flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left',
            'text-body text-foreground transition-colors hover:bg-accent',
            open && 'bg-accent')}
          title={t('prefs.title')}
        >
          <Icon name={resolved === 'dark' ? 'moon' : 'sun'} size={17} />
          <span className="flex-1 truncate">{t('prefs.title')}</span>
          <span className="rounded bg-muted px-1.5 py-px text-micro font-semibold text-muted-foreground">
            {LANGS.find((l) => l.code === lang)?.short}
          </span>
        </button>
      </PopoverTrigger>

      <PopoverContent side="top" align="start" className="w-[14rem] p-1.5">
        {/* `radiogroup` — ikkala ro'yxat ham "bittasini tanlang" turida.
            Ekran o'quvchi shu tufayli "3 tadan 2-si tanlangan" deb aytadi;
            oddiy tugmalar ro'yxatida bu ma'lumot umuman yo'q edi. */}
        <div role="radiogroup" aria-labelledby="prefs-lang">
          <div id="prefs-lang" className="px-2.5 py-1 text-micro font-semibold uppercase text-muted-foreground">
            {t('prefs.language')}
          </div>
          {LANGS.map((l) => (
            <button
              key={l.code} role="radio" aria-checked={lang === l.code}
              className={cn(row, lang === l.code && sel)}
              onClick={() => { setLang(l.code); setOpen(false) }}
            >
              <span aria-hidden="true" className="w-6 text-micro font-semibold text-muted-foreground">{l.short}</span>
              <span className="flex-1">{l.label}</span>
              {lang === l.code && <Icon name="check" size={13} />}
            </button>
          ))}
        </div>

        <div role="radiogroup" aria-labelledby="prefs-theme" className="mt-1 border-t pt-2">
          <div id="prefs-theme" className="px-2.5 pb-1 text-micro font-semibold uppercase text-muted-foreground">
            {t('prefs.theme')}
          </div>
          {THEMES.map((th) => (
            <button
              key={th.value} role="radio" aria-checked={choice === th.value}
              className={cn(row, choice === th.value && sel)}
              onClick={() => setChoice(th.value)}
            >
              <Icon name={th.icon} size={14} className="w-6" />
              <span className="flex-1">{th.label}</span>
              {choice === th.value && <Icon name="check" size={13} />}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
