/**
 * KODLASH NAVBATI — O'LCHOV ASBOBI
 * ================================
 *
 * Bu ekran oldingi uchta paneldan (Talablar, Broker navbati, malaka)
 * FARQ QILADI: ular o'lchashdan OLDIN qurilgan va hech biri
 * ishlatilmagan. Bu esa O'LCHASH UCHUN quriladi va bugun
 * ishlatiladigan foydalanuvchisi bor.
 *
 * UCH RAQAM AVTOMATIK YOZILADI — qo'lda yozilsa ular xotiradan
 * tiklanib TAXMINGA aylanardi:
 *
 *   vaqt          `ochilgan_at` -> `qaror_at`
 *   manba         taklif | qidiruv | qolda
 *   qidiruv soni  `talabsiz` dan OLDIN qidirilganmi
 *
 * Uchinchisi eng muhimi: qidiruvsiz "talabsiz" — avtomatik o'lchovga
 * ishonish, va u xato bo'lishi o'lchangan (`turniket` avtomatik
 * o'lchovda talabsiz edi, qidiruv 26.30 "Турникет" ni topdi).
 *
 * ATAYLAB YO'Q: tahrirlash, o'chirish, tarix, filtr, sahifalash.
 * 40 qator bir ekranga sig'adi. Xato bo'lsa qator qayta bosiladi va
 * ustidan yoziladi (`UNIQUE(kalit)` yo'q — bir atamaga ikkinchi kod
 * berish O'LCHANADIGAN holat).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { KodAtama, KodNavbat as Navbat, KodOlchov, KodQidiruv } from '../types'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Skeleton } from './ui/skeleton'

type Manba = 'taklif' | 'qidiruv' | 'qolda'

function Dalil({ nomlar }: { nomlar: (string | null)[] }) {
  const bor = nomlar.filter(Boolean) as string[]
  if (!bor.length) return <span className="text-muted-foreground">—</span>
  return <span className="text-muted-foreground">{bor.slice(0, 3).join(' · ')}</span>
}

function Qator({ a, onQaror }: {
  a: KodAtama
  onQaror: (kalit: string, atama: string, qaror: 'kod' | 'talabsiz' | 'otkazildi',
            code: string | null, manba: Manba | null) => Promise<void>
}) {
  const [soz, setSoz] = useState('')
  const [natija, setNatija] = useState<KodQidiruv | null>(null)
  const [band, setBand] = useState(false)
  const [qidirildi, setQidirildi] = useState(false)

  // OCHILISH VAQTI — BIRINCHI HARAKATDA yoziladi, render paytida EMAS.
  //
  // Avval `useEffect` da edi va o'lchandi: ekran ochilganda 40 qator
  // bir vaqtda ochilib, 11 soniya ichida 40 ta qator yaratildi va
  // ularning birortasida qaror bo'lmadi. Ikki xato:
  //   1. `count(*)` "40 qaror" bo'lib ko'rindi — aslida 40 ta RENDER;
  //   2. `qaror_at - ochilgan_at` "sahifa ochilganidan beri" ni
  //      o'lchardi, "shu atamaga sarflangan vaqt" ni emas.
  // Ya'ni asbob boshqa narsani o'lchayotgan edi.
  const ochilganRef = useRef(false)
  const ochish = useCallback(() => {
    if (ochilganRef.current) return
    ochilganRef.current = true
    api.kodQarorOchish(a.kalit, a.atama).catch(() => {})
  }, [a.kalit, a.atama])

  const qidir = useCallback(async () => {
    if (!soz.trim()) return
    ochish()                       // birinchi harakat — vaqt hisobi shundan
    setBand(true)
    try {
      // `kalit` uzatiladi -> server qidiruv SANOG'INI oshiradi.
      setNatija(await api.kodQidir(soz.trim(), a.kalit))
      setQidirildi(true)
    } finally { setBand(false) }
  }, [soz, a.kalit, ochish])

  const yoz = async (q: 'kod' | 'talabsiz' | 'otkazildi',
                     code: string | null, manba: Manba | null) => {
    ochish()                       // to'g'ridan-to'g'ri qaror ham hisoblanadi
    setBand(true)
    try { await onQaror(a.kalit, a.atama, q, code, manba) } finally { setBand(false) }
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
      </div>

      {a.takliflar.map((t) => (
        <div key={t.code} className="flex flex-wrap items-center gap-2 text-sm">
          <Button size="sm" variant="secondary" disabled={band}
                  onClick={() => yoz('kod', t.code, 'taklif')}>
            {t.code}
          </Button>
          <span>{t.name_ru} · {t.n_tender_open} ochiq</span>
          <Dalil nomlar={t.pozitsiyalar.map((p) => p.nom)} />
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <Input value={soz} disabled={band} placeholder="qidiruv: kabel, kamera…"
               className="h-8 max-w-[240px]"
               onChange={(e) => setSoz(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter') void qidir() }} />
        <Button size="sm" variant="outline" disabled={band} onClick={() => void qidir()}>
          Qidirish
        </Button>
        <span className="grow" />
        <Button size="sm" variant="ghost" disabled={band}
                onClick={() => yoz('talabsiz', null, null)}>
          Talabsiz{!qidirildi && ' *'}
        </Button>
        <Button size="sm" variant="ghost" disabled={band}
                onClick={() => yoz('otkazildi', null, null)}>
          O‘tkazish
        </Button>
      </div>

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
  const [nav, setNav] = useState<Navbat | null>(null)
  const [olchov, setOlchov] = useState<KodOlchov | null>(null)
  const [xato, setXato] = useState<string | null>(null)

  const yukla = useCallback(async () => {
    setXato(null)
    try {
      const [n, o] = await Promise.all([api.kodNavbat(40, true), api.kodOlchov()])
      setNav(n); setOlchov(o)
    } catch (e) { setXato((e as Error).message) }
  }, [])

  useEffect(() => { void yukla() }, [yukla])

  const onQaror = useCallback(async (
    kalit: string, atama: string, qaror: 'kod' | 'talabsiz' | 'otkazildi',
    code: string | null, manba: Manba | null,
  ) => {
    await api.kodQaror({ kalit, atama, qaror, code, manba })
    await yukla()
  }, [yukla])

  if (xato) return <div className="text-destructive">{xato}</div>
  if (!nav) return <Skeleton className="h-[420px] w-full rounded-xl" />

  const m = olchov?.olchov
  // TOIFALAR YIG'INDISI JAMIGA TENG bo'lishi shart — teng bo'lmasa
  // element jimgina yo'qolgan. Bu ekranda ham ko'rinadi.
  const butun = nav.jami_mahsulot === nav.toifa_yigindi

  return (
    <div className="space-y-3">
      <div className="rounded-xl border p-3 text-sm">
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          <span>ko‘riladi: <b>{nav.atamalar.length}</b> (+{nav.qolgan})</span>
          <span>talabsiz: <b>{nav.talabsiz_jami}</b></span>
          <span>turi aniqmas: <b>{nav.turi_aniqmas_jami}</b></span>
          <span className={butun ? 'text-muted-foreground' : 'text-destructive'}>
            {nav.jami_mahsulot} = {nav.toifa_yigindi}
            {!butun && ' ← QOLDIQ YO‘QOLGAN'}
          </span>
        </div>
        {m && m.qaror_soni > 0 && (
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-muted-foreground">
            <span>qaror: <b>{m.qaror_soni}</b></span>
            <span>o‘rtacha: <b>{m.ortacha_sek ?? '—'}</b> s</span>
            <span>taklifdan {m.taklifdan} · qidiruvdan {m.qidiruvdan} · qo‘lda {m.qoldan}</span>
            {/* Qidiruvsiz "talabsiz" — avtomatik o'lchovga ishonilgan
                holat. `turniket` shu toifada XATO bo'lgan bo'lardi. */}
            <span className={m.talabsiz_qidiruvsiz ? 'text-amber-600' : ''}>
              talabsiz: {m.talabsiz_qidiruvli} qidiruvli / {m.talabsiz_qidiruvsiz} qidiruvsiz
            </span>
            <span>bir atamaga ko‘p kod: <b>{m.kop_kodli_atama}</b></span>
          </div>
        )}
      </div>

      {nav.atamalar.map((a) => (
        <Qator key={a.kalit} a={a} onQaror={onQaror} />
      ))}

      {nav.atamalar.length === 0 && (
        <div className="text-muted-foreground">Ko‘riladigan atama qolmadi.</div>
      )}
    </div>
  )
}
