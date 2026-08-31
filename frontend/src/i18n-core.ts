// KO'P TILLILIK — SOF YADRO (JSX YO'Q)
// ═════════════════════════════════════
// NEGA `i18n.tsx` DAN AJRATILDI (o'lchangan): sinov yurgizuvchi
// `node --experimental-strip-types` JSX ni YUKLAY OLMAYDI. Hamma
// narsa `.tsx` da qolganda `translate()` va `xatoMatni()` ni
// SINOVDAN o'tkazib bo'lmasdi va ular faqat MANBA MATNI bo'yicha
// tekshirilardi — ya'ni haqiqiy xulq sinalmagan qolardi.
//
// React qismi (`I18nProvider`, `useT`) `i18n.tsx` da qoladi va bu
// fayldan re-eksport qiladi: mavjud 24 ta chaqiruvchi uchun HECH
// NARSA o'zgarmaydi.

import { uz } from './locales/uz.ts'
import type { Dict, TKey } from './locales/uz.ts'
import { ru } from './locales/ru.ts'
import { en } from './locales/en.ts'

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

/**
 * SERVER XATO KODINI joriy tildagi matnga aylantiradi.
 *
 * REACT'DAN TASHQARIDA ishlaydi (`api.ts` da `fetch` javobi
 * qayta ishlanayotganda `useT()` chaqirib bo'lmaydi) — shuning
 * uchun til `localStorage` dan o'qiladi. `setLang()` avval
 * `localStorage` ga yozadi, ya'ni ikkisi bir-biriga mos.
 *
 * TARJIMA TOPILMASA KOD QAYTADI, bo'sh matn EMAS. Ekranda
 * `TENDER_NOT_FOUND` ko'rinsa muammo darhol ko'zga tashlanadi va
 * yo'qolgan tarjima yashirinmaydi. Bu holat sinovda ham
 * qo'riqlanadi (`_tests/xato_kodlari_test.py`) va `tsc` ham
 * ushlaydi (`ru`/`en` — `Record<TKey, string>`).
 */
export function xatoMatni(code: string, vars?: TVars): string {
  const key = `err.${code}` as TKey
  let lang: Lang = 'uz'
  try { lang = readLang() } catch { /* localStorage yopiq */ }
  const s = translate(lang, key, vars)
  return s === key ? code : s
}
