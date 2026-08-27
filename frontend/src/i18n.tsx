import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { uz } from './locales/uz'
import type { Dict, TKey } from './locales/uz'
import { ru } from './locales/ru'
import { en } from './locales/en'

export type { TKey }

// KO'P TILLILIK (uz / ru / en)
// ═══════════════════════════
// KUTUBXONASIZ. `react-i18next` bu hajm uchun ortiqcha: bizga kerak bo'lgani
// — lug'at, o'rniga qo'yish (interpolatsiya) va rus tilining ko'plik shakli.
// Uchalasi ham 60 qator kod va bitta brauzer API'si (`Intl.PluralRules`).
// Evaziga: yangi bog'liqlik yo'q, paket hajmi o'smaydi.
//
// KALITLAR YASSI VA NUQTALI: `t('docs.title')`. Guruh nomi prefiks bo'lgani
// uchun kalitni kodda ham, lug'atda ham `grep` bilan topish oson.
//
// TO'LIQLIK KAFOLATI TUR TIZIMIDA: `uz` — MANBA lug'at, `ru` va `en` esa
// `Record<TKey, string>` deb e'lon qilingan. Ya'ni o'zbekchaga kalit
// qo'shilsa-yu ruschaga qo'shilmasa — `tsc` XATO beradi. Ish paytida
// "tarjima yo'q" holati umuman yuzaga kelmaydi.
export type Lang = 'uz' | 'ru' | 'en'

export const LANGS: { code: Lang; label: string; short: string }[] = [
  { code: 'uz', label: "O'zbekcha", short: 'UZ' },
  { code: 'ru', label: 'Русский', short: 'RU' },
  { code: 'en', label: 'English', short: 'EN' },
]

const DICTS: Record<Lang, Dict> = { uz, ru, en }

export const LANG_KEY = 'tender-ai:lang'

//: `Intl` uchun to'liq lokal kodlari — sana/son formatlari ham shundan.
export const LOCALE: Record<Lang, string> = {
  uz: 'uz-UZ', ru: 'ru-RU', en: 'en-US',
}

export function readLang(): Lang {
  const v = localStorage.getItem(LANG_KEY)
  return v === 'uz' || v === 'ru' || v === 'en' ? v : 'uz'
}

export type TVars = Record<string, string | number>

/**
 * Kalitni matnga aylantiradi.
 *
 * O'rniga qo'yish:  t('docs.ready', { n: 3, total: 6 })  <- "{n} / {total}"
 *
 * KO'PLIK: rus tilida son shakli uchta (1 документ / 2 документа /
 * 5 документов), ingliz va o'zbekda bittadan. `vars.n` berilsa avval
 * `<kalit>_<toifa>` qidiriladi (`_one` / `_few` / `_many` / `_other`),
 * topilmasa oddiy kalit ishlatiladi. Ya'ni ko'plik kerak bo'lmagan
 * kalitga qo'shimcha yozish SHART EMAS.
 */
export function translate(lang: Lang, key: TKey, vars?: TVars): string {
  const dict = DICTS[lang]
  let raw: string | undefined

  if (vars && typeof vars.n === 'number') {
    const cat = new Intl.PluralRules(LOCALE[lang]).select(vars.n)
    raw = dict[`${key}_${cat}`] ?? dict[`${key}_other`]
  }
  raw ??= dict[key]

  // Kalit topilmasa kalitning O'ZI qaytadi — bo'sh joy emas. Ekranda
  // `docs.title` ko'rinsa muammo darhol ko'zga tashlanadi.
  if (raw === undefined) return key

  return vars
    ? raw.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m))
    : raw
}

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: TKey, vars?: TVars) => string
  /** `Intl` uchun lokal kodi — sana/son formatlashda ishlatiladi. */
  locale: string
}

const Ctx = createContext<I18nCtx | null>(null)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang)

  // Ekran o'quvchi va brauzerning imlo tekshiruvi `<html lang>` ga qaraydi
  useEffect(() => { document.documentElement.lang = lang }, [lang])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    localStorage.setItem(LANG_KEY, l)
  }, [])

  const value = useMemo<I18nCtx>(() => ({
    lang,
    setLang,
    t: (key, vars) => translate(lang, key, vars),
    locale: LOCALE[lang],
  }), [lang, setLang])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18nCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useI18n faqat <I18nProvider> ichida ishlaydi.')
  return c
}

/** Qisqartma — komponentlarda eng ko'p ishlatiladigani. */
export function useT() {
  return useI18n().t
}
