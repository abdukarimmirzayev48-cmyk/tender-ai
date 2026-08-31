/**
 * SINOV: XATO KODI -> FOYDALANUVCHI TILI
 * ══════════════════════════════════════
 * Nega alohida sinov: server endi TILGA BOG'LIQ BO'LMAGAN kod
 * qaytaradi (`api/xatolar.py`), matnni esa interfeys yig'adi.
 * Kalit yozilishida bitta harf xato bo'lsa, ekranda
 * `TENDER_NOT_FOUND` ko'rinadi va bu JIMGINA o'tib ketadi — hech
 * qayerda istisno ko'tarilmaydi.
 *
 * NIMANI QAMRAB OLADI (va nimani YO'Q):
 *
 *   `tsc`      uchala lug'atning TO'LIQLIGI (`ru`/`en` —
 *              `Record<TKey, string>`); bu sinov uni takrorlamaydi.
 *   BU SINOV   server ro'yxati bilan MOSLIK, o'rniga qo'yish
 *              belgilarining uchala tilda bir xilligi va
 *              `api.ts` / `i18n.tsx` ulanishi.
 *
 * `translate()` va `xatoMatni()` HAQIQATAN CHAQIRILADI: ular
 * `i18n-core.ts` da (JSX'siz), shuning uchun sinov yurgizuvchi
 * ularni yuklay oladi. React qismi `i18n.tsx` da qoladi.
 *
 * Ishga tushirish (loyiha ildizidan):
 *     cd frontend && npm run test:xato
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { uz } from './locales/uz.ts'
import { ru } from './locales/ru.ts'
import { en } from './locales/en.ts'
import { translate, xatoMatni, type Lang, type TKey } from './i18n-core.ts'

const SRC = fileURLToPath(new URL('.', import.meta.url))
const ILDIZ = join(SRC, '..', '..')

let pass = 0
let fail = 0

function check(nom: string, ok: boolean, tafsilot = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${nom}`
              + (tafsilot ? ` -- ${tafsilot}` : ''))
}

/** `api/xatolar.py:KODLAR` — YAGONA manba, shu yerdan o'qiladi. */
function serverKodlari(): string[] {
  const s = readFileSync(join(ILDIZ, 'api', 'xatolar.py'), 'utf8')
  const boshi = s.indexOf('KODLAR: Dict[str, int] = {')
  const oxiri = s.indexOf('\n}', boshi)
  return [...s.slice(boshi, oxiri).matchAll(/^\s*"([A-Z][A-Z0-9_]*)":\s*\d+,/gm)]
    .map((m) => m[1])
}

const belgilar = (v: string) =>
  [...v.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')

function main() {
  console.log('='.repeat(62))
  console.log('SINOV: XATO KODI -> FOYDALANUVCHI TILI')
  console.log('='.repeat(62))

  const kodlar = serverKodlari()
  check('server kod ro`yxati o`qildi', kodlar.length > 50,
        `${kodlar.length} ta`)

  const lug: Record<string, Record<string, string>> = { uz, ru, en }

  for (const til of ['uz', 'ru', 'en']) {
    const d = lug[til]
    const yoq = kodlar.filter((k) => !(`err.${k}` in d))
    check(`${til}: har kodning kaliti bor`, yoq.length === 0,
          yoq.slice(0, 5).join(', '))

    // Lug'atda ORTIQCHA `err.*` bo'lsa — server kodi o'chirilgan,
    // tarjima esa qolgan. U hech qachon ko'rinmaydi va eskiradi.
    const ortiq = Object.keys(d)
      .filter((k) => k.startsWith('err.'))
      .map((k) => k.slice(4))
      .filter((k) => !kodlar.includes(k))
    check(`${til}: ortiqcha \`err.*\` kaliti yo'q`, ortiq.length === 0,
          ortiq.slice(0, 5).join(', '))

    const bosh = kodlar.filter((k) => !(d[`err.${k}`] || '').trim())
    check(`${til}: bo'sh tarjima yo'q`, bosh.length === 0,
          bosh.slice(0, 5).join(', '))

    // Tarjima o'rnida KOD qolib ketmasin (nusxa-joylashtirish izi).
    const xom = kodlar.filter((k) => d[`err.${k}`] === k)
    check(`${til}: tarjima o'rnida KOD qolmagan`, xom.length === 0,
          xom.slice(0, 5).join(', '))
  }

  // Uchala til HAR XIL matn bersin: bir xil bo'lsa tarjima
  // qilinmagan, faqat ko'chirilgan.
  const bir_xil = kodlar.filter((k) => lug.uz[`err.${k}`] === lug.ru[`err.${k}`])
  check('uz va ru matnlari HAR XIL', bir_xil.length === 0,
        bir_xil.slice(0, 5).join(', '))

  // O'RNIGA QO'YISH BELGILARI uchala tilda BIR XIL. Bir tilda
  // `{id}` bor, ikkinchisida yo'q bo'lsa — o'sha tilda ma'lumot
  // JIMGINA yo'qoladi.
  const farq = kodlar.filter((k) => {
    const u = belgilar(lug.uz[`err.${k}`] || '')
    return u !== belgilar(lug.ru[`err.${k}`] || '')
      || u !== belgilar(lug.en[`err.${k}`] || '')
  })
  check('belgilar to`plami uchala tilda BIR XIL', farq.length === 0,
        farq.slice(0, 5).join(', '))

  // Belgi nomi SERVER beradigan `params` kalitiga mos bo'lsin.
  // Server `{daqiqa}` yubormasa, foydalanuvchi qavsli kalitni
  // ko'radi — bu jimgina buziladigan bog'lanish.
  const notanish = new Set<string>()
  const MANBALAR = ['api/main.py', 'api/auth.py', 'api/notify.py',
                    'api/telegram.py', 'api/importer.py', 'api/aktor.py',
                    'api/ai.py', 'api/ai_chat.py', 'api/kodlash.py',
                    'api/requirement.py', 'api/routing.py',
                    'api/qualification.py']
  const serverMatni = MANBALAR
    .map((f) => readFileSync(join(ILDIZ, ...f.split('/')), 'utf8')).join('\n')
  for (const k of kodlar) {
    for (const b of (belgilar(lug.uz[`err.${k}`] || '') || '').split(',')) {
      if (b && !serverMatni.includes(`"${b}"`)) notanish.add(`${k}:{${b}}`)
    }
  }
  check('har `{belgi}` server `params` ida uchraydi', notanish.size === 0,
        [...notanish].slice(0, 5).join(', '))

  // HAQIQIY CHAQIRUV. Yuqoridagilar lug'at MAZMUNINI tekshiradi;
  // bu yerda `translate()` va `xatoMatni()` ning O'ZI yuriladi.
  const kalit = 'err.TENDER_NOT_FOUND' as TKey
  check('uz tarjimasi qaytadi',
        translate('uz', kalit) === 'Tender topilmadi.',
        translate('uz', kalit))
  check('ru tarjimasi qaytadi',
        translate('ru', kalit) === 'Тендер не найден.',
        translate('ru', kalit))
  check('en tarjimasi qaytadi',
        translate('en', kalit) === 'Tender not found.',
        translate('en', kalit))

  // BITTA KOD, UCH TIL — aynan shu vazifaning maqsadi.
  const uchta = new Set((['uz', 'ru', 'en'] as Lang[])
    .map((l) => translate(l, kalit)))
  check('bitta kod uchta HAR XIL matn beradi', uchta.size === 3,
        [...uchta].join(' | '))

  // O'RNIGA QO'YISH ishlaydi (belgi matnda QOLMAYDI).
  const bilan = translate('ru', 'err.FILE_TOO_LARGE' as TKey, { max_mb: 25 })
  check("o'rniga qo'yish ishlaydi",
        bilan.includes('25') && !/\{\w+\}/.test(bilan), bilan)

  // NOTANISH KOD: `xatoMatni()` KODNI qaytaradi, bo'sh matn EMAS.
  // (`node` da `localStorage` yo'q — `xatoMatni()` uni ushlab
  //  o'zbekchaga tushadi; aynan shu zaxira yo'li tekshiriladi.)
  check('notanish kod uchun KOD qaytadi',
        xatoMatni('BUNDAY_KOD_YOQ') === 'BUNDAY_KOD_YOQ',
        xatoMatni('BUNDAY_KOD_YOQ'))
  check('tanish kod uchun MATN qaytadi',
        xatoMatni('TENDER_NOT_FOUND') === 'Tender topilmadi.',
        xatoMatni('TENDER_NOT_FOUND'))

  // ULANISH: `api.ts` kodni o'qiydi, `i18n-core.ts` uni matnga aylantiradi.
  const apiSrc = readFileSync(join(SRC, 'api.ts'), 'utf8')
  check('`api.ts` `error.code` ni o`qiydi', /xato\.code/.test(apiSrc))
  check('`api.ts` `xatoMatni()` ni chaqiradi', /xatoMatni\(kod/.test(apiSrc))
  check('`ApiError` kodni saqlaydi', /code\?: string/.test(apiSrc))
  check('`ApiError` tashxis identifikatorini saqlaydi',
        /diagnosticId\?: string/.test(apiSrc))

  const i18nSrc = readFileSync(join(SRC, 'i18n-core.ts'), 'utf8')
  check('`xatoMatni()` mavjud', /export function xatoMatni/.test(i18nSrc))
  check('`xatoMatni()` notanish kodda KODNI qaytaradi',
        /return s === key \? code : s/.test(i18nSrc))

  console.log('\n' + '='.repeat(62))
  console.log(`NATIJA: ${pass}/${pass + fail} o'tdi`)
  console.log('='.repeat(62))
  process.exit(fail ? 1 : 0)
}

main()
