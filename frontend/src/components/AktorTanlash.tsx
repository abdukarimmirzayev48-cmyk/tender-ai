// AKTOR TANLASH — qarorni KIM qo'yayotgani (auth-6)
//
// Tender-AI ga KOMPANIYA kiradi, odam emas (hodimlar ERP da). Bu
// tanlov qarorni ijarachi ICHIDA aniq odamga bog'laydi.
//
// BU ISBOT EMAS VA SHUNDAY KO'RSATILADI. Server tanlovni `aktor_elon`
// darajasi bilan yozadi — "e'lon qilingan", "isbotlangan" emas.
// Interfeys buni YASHIRMAYDI: pastda darajaning o'zi yozib turadi.
// Yashirish "biz kim qilganini aniq bilamiz" degan yolg'on ishonch
// berardi.
import { useEffect, useState } from 'react'

import { api, getAktorId, setAktorId } from '../api'
import { useI18n } from '../i18n'
import type { Aktor, AktorHolat } from '../types'

const ISHONCH_KALIT: Record<string, string> = {
  erp_sessiya: 'aktor.trust.proven',
  aktor_elon: 'aktor.trust.declared',
  kompaniya_sessiyasi: 'aktor.trust.companyOnly',
  servis: 'aktor.trust.service',
  kuzatuvdan_oldin: 'aktor.trust.unknown',
}

export default function AktorTanlash() {
  const { t } = useI18n()
  const [aktorlar, setAktorlar] = useState<Aktor[]>([])
  const [holat, setHolat] = useState<AktorHolat | null>(null)
  const [tanlangan, setTanlangan] = useState<number | null>(getAktorId())
  const [yuklandi, setYuklandi] = useState(false)

  useEffect(() => {
    let tirik = true
    Promise.all([api.aktorlar(true).catch(() => null),
                 api.aktorHolat().catch(() => null)])
      .then(([a, h]) => {
        if (!tirik) return
        setAktorlar(a?.aktorlar ?? [])
        setHolat(h)
        setYuklandi(true)
      })
    return () => { tirik = false }
  }, [])

  // Sxema qo'llanmagan yoki aktor umuman yo'q — blok KO'RSATILMAYDI.
  // Bo'sh ro'yxatni ko'rsatish foydalanuvchini chalg'itardi.
  if (!yuklandi || !holat?.tayyor || aktorlar.length === 0) return null

  const majburiy = holat.aktor_majburiy === true
  const ishonch = holat.meniki?.ishonch ?? 'kompaniya_sessiyasi'

  function tanla(v: string) {
    const id = v ? Number(v) : null
    setAktorId(id)
    setTanlangan(id)
    // Sarlavha HAR so'rovga qo'yiladi, shuning uchun sahifani
    // yangilaymiz — ochiq ekrandagi ma'lumot yangi aktor bilan
    // qayta o'qilsin.
    window.location.reload()
  }

  return (
    <div className="mb-3 rounded-md border bg-card px-2.5 py-2">
      <label
        className="mb-1 block text-micro font-semibold uppercase text-muted-foreground"
        htmlFor="aktor-tanlash"
      >
        {t('aktor.label')}
      </label>
      <select
        id="aktor-tanlash"
        className="w-full rounded border bg-background px-2 py-1 text-body"
        value={tanlangan ?? ''}
        onChange={(e) => tanla(e.target.value)}
      >
        {/* MAJBURIY bo'lsa "ko'rsatilmagan" varianti YO'Q — aks holda
            foydalanuvchi qaror qo'ya olmaydigan holatni tanlardi. */}
        {!majburiy && <option value="">{t('aktor.none')}</option>}
        {aktorlar.map((a) => (
          <option key={a.id} value={a.id}>
            {a.ism} — {t(`aktor.role.${a.rol}`)}
          </option>
        ))}
      </select>
      <div className="mt-1 text-micro text-muted-foreground">
        {t(ISHONCH_KALIT[ishonch] ?? 'aktor.trust.companyOnly')}
      </div>
      {majburiy && !tanlangan && (
        <div className="mt-1 text-micro text-destructive">
          {t('aktor.required')}
        </div>
      )}
    </div>
  )
}
