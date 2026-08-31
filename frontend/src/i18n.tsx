import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { LANG_KEY, LOCALE, readLang, translate,
         type Lang, type TKey, type TVars } from './i18n-core'

// KO'P TILLILIK — REACT QISMI.
//
// Lug'at, o'rniga qo'yish va xato kodi tarjimasi `i18n-core.ts` da:
// u JSX tutmaydi va SINOVDAN o'tkaziladi (`src/xato.test.ts`).
// Quyidagi re-eksport mavjud chaqiruvchilar uchun: ular
// avvalgidek `./i18n` dan import qiladi.
export { LANGS, LANG_KEY, LOCALE, readLang, translate, xatoMatni } from './i18n-core'
export type { Lang, TKey, TVars } from './i18n-core'

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
