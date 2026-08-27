import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Button } from '@/components/ui/button'

// ERP BILAN INTEGRATSIYA — tender-ai tomonidagi YAGONA nuqta.
//
// ERP alohida loyiha (o'z backendi :8100, o'z interfeysi :5174). Bu yerda
// undan faqat bitta savol so'raladi: "shu tender ishga olinganmi?" Javob
// bo'lsa nishon va kartaga havola, bo'lmasa "ERP da ishga olish" tugmasi
// ko'rsatiladi — ikkalasi ham ERP interfeysini yangi oynada ochadi.
//
// TENDER-AI ERP HAQIDA BOSHQA HECH NARSA BILMAYDI: na jadval, na status
// ro'yxati, na forma. Shuning uchun ERP o'zgarsa bu fayl o'zgarmaydi.
//
// SO'ROVNI SERVER QILADI (auth-3). Ilgari bu komponent ERP backendiga
// TO'G'RIDAN-TO'G'RI borardi va shuning uchun ERP ning o'sha endpointi
// ochiq qolishga majbur edi. Endi biz o'z backendimizdan so'raymiz, u esa
// `erp.v_tender_status` view ini o'qiydi (`api/erp_status.py`).
//
// ERP o'rnatilmagan bo'lsa (yoki .env da interfeys manzili berilmagan
// bo'lsa) komponent UMUMAN ko'rinmaydi — tender paneli avvalgidek
// ishlaydi. Ishlamaydigan tugma turgani yolg'on va'da bo'lardi.

const ERP_WEB = (import.meta.env.VITE_ERP_WEB || '').replace(/\/$/, '')

interface ErpOpportunity {
  opportunity_id: number
  status: string
  status_label: string | null
  broker_name: string | null
  client_name: string | null
}

export default function ErpLink({ tenderId }: { tenderId: number }) {
  const [taken, setTaken] = useState<ErpOpportunity[] | null>(null)
  const [reachable, setReachable] = useState(true)

  useEffect(() => {
    let alive = true
    setTaken(null); setReachable(true)
    api.erpStatus(tenderId)
      // `ready=false` — ERP sxemasi o'rnatilmagan: blok ko'rsatilmaydi.
      .then((d) => { if (alive) (d.ready ? setTaken(d.opportunities) : setReachable(false)) })
      // Baza yoki view yo'q: xato KO'RSATILMAYDI, blok yashiriladi. Tender
      // paneli ERP tufayli buzilmasligi kerak.
      .catch(() => { if (alive) setReachable(false) })
    return () => { alive = false }
  }, [tenderId])

  if (!ERP_WEB || !reachable || taken === null) return null

  return (
    <div className="mb-4">
      {taken.length > 0 && (
        <div className="mb-2 flex flex-col gap-1.5">
          {taken.map((o) => (
            <div key={o.opportunity_id}
              className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted px-3 py-2">
              <Icon name="briefcase" size={13} className="text-primary" />
              <span className="text-body font-semibold">Ishga olingan</span>
              <span className="rounded bg-secondary px-2 py-0.5 text-caption font-semibold text-primary">
                {o.status_label || o.status}
              </span>
              {o.broker_name && (
                <span className="text-caption text-muted-foreground">{o.broker_name}</span>
              )}
              {o.client_name && (
                <span className="text-caption text-muted-foreground">· {o.client_name}</span>
              )}
              <a className="ml-auto inline-flex items-center gap-1 text-caption font-semibold text-primary hover:underline"
                href={`${ERP_WEB}/?opp=${o.opportunity_id}`} target="_blank" rel="noopener noreferrer">
                ERP kartasi <Icon name="external" size={11} />
              </a>
            </div>
          ))}
        </div>
      )}

      <Button asChild variant={taken.length ? 'outline' : 'default'} size="sm">
        <a href={`${ERP_WEB}/?take=${tenderId}`} target="_blank" rel="noopener noreferrer">
          <Icon name="briefcase" size={13} />
          {taken.length ? 'Yana bir mijoz uchun ishga olish' : 'ERP da ishga olish'}
          <Icon name="external" size={11} />
        </a>
      </Button>
    </div>
  )
}
