/**
 * KODLASH NAVBATI — O'LCHOV ASBOBI.
 *
 * Bu ekran oldingi uchtadan (Talablar, Broker navbati, malaka) FARQ
 * QILADI: ular o'lchashdan OLDIN qurilgan va hech biri ishlatilmagan.
 * Bu esa O'LCHASH UCHUN quriladi.
 *
 * NIMA AVTOMATIK YOZILADI (qo'lda yozilsa xotiradan tiklanib
 * TAXMINGA aylanardi):
 *   vaqt          `ochilgan_at` -> `qaror_at`
 *   manba         taklif | qidiruv | qolda
 *   qidiruv soni  `talabsiz` dan OLDIN qidirilganmi
 *   qidiruv so'zi NIMANI qidirdi
 *   dalil         inson EKRANDA KO'RGAN hamma narsa
 *   taklif        mashina nimani birinchi o'ringa qo'ygan edi
 *
 * DALIL NEGA SAQLANADI: qarorning o'zi ML uchun yetarli emas.
 * "Кабель -> 27.32" degan yorliq, inson NIMA KO'RIB shunday
 * deganini bilmasdan, o'rgatish uchun yaroqsiz.
 *
 * QAROR TURLARI — TO'RTTA, va `talabsiz` bilan `dalilsiz` ATAYLAB
 * ajratilgan:
 *   kod        kod berildi
 *   talabsiz   MEN KO'RDIM, korpusda bunday talab yo'q  (XULOSA)
 *   dalilsiz   MEN QAROR QILA OLMADIM                   (XULOSA YO'Q)
 *   otkazildi  hozir emas
 * Ularni aralashtirish `talabsiz` statistikasini ishonchsiz qilardi,
 * va u aynan quvur aniqligini o'lchaydigan raqam.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { KodAtama, KodNavbat as Navbat, KodOlchov, KodPilot,
  KodQaror, KodQidiruv, Manba } from '../types'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Skeleton } from './ui/skeleton'

function Dalil({ nomlar }: { nomlar: (string | null)[] }) {
  const bor = nomlar.filter(Boolean) as string[]
  if (!bor.length) return <span className="text-muted-foreground">—</span>
  return <span className="text-muted-foreground">{bor.slice(0, 3).join(' · ')}</span>
}

function Qator({ a, onQaror }: {
  a: KodAtama
  onQaror: (kalit: string, atama: string, qaror: KodQaror,
            code: string | null, manba: Manba | null,
            qoshimcha: Record<string, unknown>) => Promise<void>
}) {
  const [soz, setSoz] = useState('')
  const [natija, setNatija] = useState<KodQidiruv | null>(null)
  const [band, setBand] = useState(false)
  const [qidirildi, setQidirildi] = useState(false)
  const [ochXato, setOchXato] = useState<string | null>(null)
  // ANIQ rad etilgan takliflar — MANFIY misollar. Musbat misoldan
  // kam qimmatli emas: "nima emas" ni bilmasdan chegara chizib
  // bo'lmaydi.
  const [rad, setRad] = useState<string[]>([])
  // Bu atamaga ALLAQACHON kod berildimi. Berilgan bo'lsa keyingi
  // kod "QO'SHIMCHA" bo'ladi — fikr o'zgarishi emas.
  const [kodBerildi, setKodBerildi] = useState(false)
  const [izoh, setIzoh] = useState('')

  // OCHILISH VAQTI — BIRINCHI HARAKATDA yoziladi, render paytida EMAS.
  //
  // Avval `useEffect` da edi va o'lchandi: ekran ochilganda 40 qator
  // bir vaqtda ochilib, 11 soniya ichida 40 ta qator yaratildi va
  // ularning birortasida qaror bo'lmadi. Ikki xato:
  //   1. `count(*)` "40 qaror" bo'lib ko'rindi — aslida 40 ta RENDER;
  //   2. `qaror_at - ochilgan_at` "sahifa ochilganidan beri" ni
  //      o'lchardi, "shu atamaga sarflangan vaqt" ni emas.
  // Ya'ni asbob boshqa narsani o'lchayotgan edi.
  //
  // KUTILADI (`await`), yuborilib tashlanmaydi. Avval `ochish()`
  // kutilmasdan chaqirilar, keyin darhol qaror POST i ketardi — ikki
  // mustaqil so'rov. Qaror OLDIN yetib borsa `qaror_yoz()` ochiq qator
  // topmay YANGI yakunlangan qator qo'yadi, `ochish` esa undan keyin
  // QAROR QILINMAGAN qator yaratadi. O'lchandi: aynan shu ketma-ketlik
  // 2 ta qator qoldirdi, biri abadiy ochiq, ikkinchisining o'tgan
  // vaqti 0. Kutilganda tartib aniq bo'ladi.
  const ochilganRef = useRef(false)
  const ochish = useCallback(async () => {
    if (ochilganRef.current) return
    ochilganRef.current = true
    try {
      await api.kodQarorOchish(a.kalit, a.atama)
    } catch (e) {
      // JIMGINA YUTILMAYDI. Ilgari `.catch(() => {})` edi: ochish
      // muvaffaqiyatsiz bo'lsa vaqt hech qachon o'lchanmasdi va
      // ekranda hech narsa ko'rinmasdi — o'lchov asbobi o'lchamay
      // turib "ishlayapti" ko'rinardi.
      ochilganRef.current = false
      setOchXato((e as Error).message || 'ochilmadi')
    }
  }, [a.kalit, a.atama])

  const qidir = useCallback(async () => {
    if (!soz.trim()) return
    await ochish()                 // birinchi harakat — vaqt hisobi shundan
    setBand(true)
    try {
      // `kalit` uzatiladi -> server qidiruv SANOG'INI va SO'ZINI yozadi.
      setNatija(await api.kodQidir(soz.trim(), a.kalit))
      setQidirildi(true)
    } finally { setBand(false) }
  }, [soz, a.kalit, ochish])

  /**
   * Inson EKRANDA KO'RGAN dalilni yig'adi.
   *
   * Server buni QAYTA HISOBLAMAYDI — bizga "haqiqat" emas, "inson
   * nimaga qarab qaror qildi" kerak. Korpus keyin o'zgarsa ham
   * yorliq o'z kirishiga bog'langan qoladi.
   */
  const dalilYig = (): Record<string, unknown> => ({
    atama: a.atama,
    n_mahsulot: a.n_mahsulot,
    korpus: { keng: a.korpus_ochiq, aniq: a.korpus_ochiq_aniq },
    takliflar: a.takliflar.map((t) => ({
      code: t.code,
      nomi: t.name_ru,
      skor: t.skor ?? null,
      ochiq_tender: t.n_tender_open,
      pozitsiyalar: t.pozitsiyalar.map((p) => p.nom).filter(Boolean).slice(0, 6),
    })),
    qidiruv: qidirildi ? {
      soz: soz.trim(),
      natija: (natija?.pozitsiya ?? []).map((p) => ({
        code: p.code, n_poz: p.n_poz, ochiq_tender: p.n_ochiq,
        namunalar: (p.namunalar ?? []).filter(Boolean).slice(0, 6),
      })),
      meniki: natija?.meniki ?? null,
    } : null,
    rad_etilgan: rad,
  })

  const yoz = async (q: KodQaror, code: string | null, manba: Manba | null) => {
    await ochish()                 // to'g'ridan-to'g'ri qaror ham hisoblanadi
    setBand(true)
    try {
      const top = a.takliflar[0]
      await onQaror(a.kalit, a.atama, q, code, manba, {
        dalil: dalilYig(),
        // Mashina BIRINCHI o'ringa nimani qo'ygan edi — kelishuv
        // foizi shundan hisoblanadi.
        taklif_code: top?.code ?? null,
        taklif_skor: top?.skor ?? null,
        rad_takliflar: rad,
        // Bu atamaga allaqachon kod berilgan bo'lsa, keyingisi
        // QO'SHIMCHA: atama haqiqatan ko'p kodli. Fikr o'zgarishi
        // bilan aralashmasin.
        qoshimcha_kod: q === 'kod' && kodBerildi,
        izoh: izoh.trim() || null,
      })
      if (q === 'kod') setKodBerildi(true)
    } finally { setBand(false) }
  }

  /** Taklifni ANIQ rad etish — qaror emas, dalil to'plash. */
  const radEt = async (code: string) => {
    await ochish()                 // bu ham HARAKAT: vaqt hisobi boshlansin
    setRad((s) => (s.includes(code) ? s : [...s, code]))
  }

  // `keng` va `aniq` YONMA-YON. Farq katta bo'lsa o'zak kengligi
  // sabab ekani ko'rinadi va raqamga ishonilmaydi.
  const shubhali = a.korpus_ochiq > 0 && a.korpus_ochiq_aniq * 2 < a.korpus_ochiq

  return (
    <div className="rounded-xl border p-3 space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-medium">{a.atama}</span>
        <span className="text-sm text-muted-foreground">{a.n_mahsulot} mahsulot</span>
        <span className={'text-xs ' + (shubhali ? 'text-amber-600' : 'text-muted-foreground')}>
          korpus: keng={a.korpus_ochiq} aniq={a.korpus_ochiq_aniq}
          {shubhali && ' — keng o‘zak shishirgan bo‘lishi mumkin'}
        </span>
        {kodBerildi && (
          <span className="rounded bg-ok-soft px-1.5 py-0.5 text-xs text-ok">
            kod berildi — keyingisi QO‘SHIMCHA bo‘ladi
          </span>
        )}
      </div>

      {a.takliflar.map((t) => {
        const radmi = rad.includes(t.code)
        return (
          <div key={t.code}
               className={'flex flex-wrap items-center gap-2 text-sm '
                          + (radmi ? 'opacity-50' : '')}>
            <Button size="sm" variant="secondary" disabled={band || radmi}
                    onClick={() => yoz('kod', t.code, 'taklif')}>
              {t.code}
            </Button>
            <span>{t.name_ru} · {t.n_tender_open} ochiq</span>
            <Dalil nomlar={t.pozitsiyalar.map((p) => p.nom)} />
            <span className="grow" />
            {/* TAKLIFNI RAD ETISH — qaror EMAS, manfiy misol.
                Inson qidirishda davom etishi mumkin. */}
            <Button size="sm" variant="ghost" disabled={band || radmi}
                    onClick={() => void radEt(t.code)}
                    title="Bu taklif noto‘g‘ri (manfiy misol sifatida saqlanadi)">
              {radmi ? 'rad etildi' : 'noto‘g‘ri'}
            </Button>
          </div>
        )
      })}

      <div className="flex flex-wrap items-center gap-2">
        <Input value={soz} disabled={band} placeholder="qidiruv: kabel, kamera…"
               className="h-8 max-w-[240px]"
               onChange={(e) => setSoz(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter') void qidir() }} />
        <Button size="sm" variant="outline" disabled={band} onClick={() => void qidir()}>
          Qidirish
        </Button>
        <span className="grow" />
        {/* `talabsiz` — XULOSA: "men ko'rdim, talab yo'q".
            `dalilsiz` — XULOSA YO'QLIGI: "qaror qila olmadim".
            Ikkisi ALOHIDA tugma, chunki ular boshqa-boshqa signal. */}
        <Button size="sm" variant="ghost" disabled={band}
                onClick={() => yoz('talabsiz', null, null)}
                title="Korpusda bunday talab yo‘q">
          Talabsiz{!qidirildi && ' *'}
        </Button>
        <Button size="sm" variant="ghost" disabled={band}
                onClick={() => yoz('dalilsiz', null, null)}
                title="Dalil yetarli emas — qaror qila olmadim">
          Dalilsiz
        </Button>
        <Button size="sm" variant="ghost" disabled={band}
                onClick={() => yoz('otkazildi', null, null)}>
          O‘tkazish
        </Button>
      </div>

      <Input value={izoh} disabled={band} placeholder="izoh (ixtiyoriy): nega shunday qaror?"
             className="h-8 text-xs"
             onChange={(e) => setIzoh(e.target.value)} />

      {ochXato && (
        <div className="text-xs text-destructive">
          o‘lchov ochilmadi: {ochXato} — vaqt yozilmaydi
        </div>
      )}

      {natija && (
        <div className="space-y-1 rounded-lg bg-muted/40 p-2 text-sm">
          {natija.pozitsiya.length === 0 && (
            <div className="text-muted-foreground">Korpusda topilmadi.</div>
          )}
          {natija.pozitsiya.map((p) => (
            <div key={p.code} className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" disabled={band}
                      onClick={() => yoz('kod', p.code, 'qidiruv')}>
                {p.code}
              </Button>
              <span>{p.n_poz} poz · {p.n_ochiq} ochiq</span>
              <Dalil nomlar={p.namunalar} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function KodNavbat() {
  const [navbat, setNavbat] = useState<Navbat | null>(null)
  const [olchov, setOlchov] = useState<KodOlchov | null>(null)
  const [pilot, setPilot] = useState<KodPilot | null>(null)
  const [yuklanmoqda, setYuklanmoqda] = useState(true)
  const [xato, setXato] = useState<string | null>(null)

  const yukla = useCallback(async () => {
    setYuklanmoqda(true)
    setXato(null)
    try {
      const [n, o] = await Promise.all([
        api.kodNavbat(), api.kodQarorOlchov(),
      ])
      setNavbat(n)
      setOlchov(o.olchov)
      setPilot(o.pilot ?? null)
    } catch (e) {
      setXato((e as Error).message || 'yuklanmadi')
    } finally { setYuklanmoqda(false) }
  }, [])

  useEffect(() => { void yukla() }, [yukla])

  const qaror = async (kalit: string, atama: string, q: KodQaror,
                       code: string | null, manba: Manba | null,
                       qoshimcha: Record<string, unknown>) => {
    await api.kodQaror({ kalit, atama, qaror: q, code, manba, ...qoshimcha })
    await yukla()
  }

  if (yuklanmoqda) return <Skeleton className="h-64 w-full" />
  if (xato) return <div className="text-sm text-destructive">{xato}</div>

  return (
    <div className="space-y-3">
      {/* PILOT HOLATI — "40 taga qancha qoldi" EKRANDA ko'rinadi.
          Qo'lda hisoblangan raqam xotiradan tiklanib TAXMINGA
          aylanadi, shuning uchun u serverdan keladi.
          MAQSAD ATAMA BO'YICHA: bir atamaga ikki kod berish qator
          sonini oshiradi va maqsadni SOXTA yaqinlashtirardi. */}
      {pilot && (
        <div className="rounded-xl border bg-muted/30 p-3 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="font-medium">
              Pilot: {pilot.atama_soni}/{pilot.maqsad} atama
            </span>
            <span className="text-muted-foreground">
              qolgan {pilot.qolgan}
            </span>
            <span className="text-muted-foreground">
              o‘lchangan {pilot.olchangan} · dalilli {pilot.dalilli}
            </span>
            {/* NULL = O'LCHANMADI, nol EMAS. Ikkisi aralashmasin. */}
            <span className="text-muted-foreground">
              median {pilot.median_sek == null ? '—' : `${pilot.median_sek}s`}
            </span>
            {pilot.taklif_kelishuv_foiz != null && (
              <span className="text-muted-foreground">
                taklif kelishuvi {pilot.taklif_kelishuv_foiz}%
              </span>
            )}
            {pilot.qidiruv_foiz != null && (
              <span className="text-muted-foreground">
                qidiruv {pilot.qidiruv_foiz}%
              </span>
            )}
          </div>
          {olchov && (olchov.talabsiz_qidiruvsiz ?? 0) > 0 && (
            /* QIDIRUVSIZ "talabsiz" — avtomatik o'lchovga ISHONISH
               demak, va u xato bo'lishi O'LCHANGAN (`turniket`
               avtomatik o'lchovda talabsiz edi, qidiruv 26.30 ni
               topdi). Bu raqam ko'rinib tursin. */
            <div className="mt-1 text-xs text-amber-600">
              {olchov.talabsiz_qidiruvsiz} ta “talabsiz” QIDIRUVSIZ
              qo‘yilgan — bu raqamga tayanib bo‘lmaydi
            </div>
          )}
        </div>
      )}

      {navbat && navbat.atamalar.length === 0 && (
        <div className="rounded-xl border p-4 text-sm text-muted-foreground">
          Navbat bo‘sh.
        </div>
      )}

      {navbat?.atamalar.map((a) => (
        <Qator key={a.kalit} a={a} onQaror={qaror} />
      ))}
    </div>
  )
}
