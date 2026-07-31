import { useRef, useState } from 'react'
import { apiUrl, errMatn } from '@/api'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { ImportResult } from '@/types'

// KATALOG VA OMBOR QOLDIQLARINI IMPORT QILISH (TZ P0-4)
//
// Oqim: fayl tanlash -> AVTOMATIK DRY-RUN (bazaga yozilmaydi) -> natijani
// ko'rish -> "Tasdiqlash". Foydalanuvchi nima yozilishini OLDINDAN ko'radi.
//
// Xato hisoboti TZ talabiga muvofiq QATOR BO'YICHA: har bir xatoda fayldagi
// haqiqiy qator raqami, ustun nomi va o'zbekcha tushuntirish bor.
//
// Yuklash `fetch` bilan to'g'ridan-to'g'ri bajariladi: api.ts dagi `request()`
// JSON uchun mo'ljallangan, multipart (FormData) ni yubora olmaydi.
const MAX_MB = 5

interface CatalogImportProps {
  onImported?: () => void
  onClose?: () => void
}

export default function CatalogImport({ onImported, onClose }: CatalogImportProps) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)   // dry-run natijasi
  const [done, setDone] = useState<ImportResult | null>(null)       // yakuniy import natijasi
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function send(f: File, dryRun: boolean): Promise<ImportResult> {
    const fd = new FormData()
    fd.append('file', f)
    const res = await fetch(apiUrl(`/catalog/import?dry_run=${dryRun}`), {
      method: 'POST', body: fd,
    })
    const text = await res.text()
    const body = text ? JSON.parse(text) : null
    // `errMatn` — 422 dagi `detail` MASSIVini o'qiladigan matnga aylantiradi.
    if (!res.ok) throw new Error(errMatn(body?.detail) || `${res.status}: ${res.statusText}`)
    return body as ImportResult
  }

  async function pick(f?: File | null) {
    if (!f) return
    setError(null); setResult(null); setDone(null); setFile(f)
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`Fayl ${MAX_MB} MB dan katta (${(f.size / 1048576).toFixed(1)} MB).`)
      return
    }
    setBusy(true)
    try {
      setResult(await send(f, true))          // DRY-RUN — bazaga tegmaydi
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  async function confirm() {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const r = await send(file, false)
      setDone(r)
      setResult(null)
      onImported?.()
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  function reset() {
    setFile(null); setResult(null); setDone(null); setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="mb-4 space-y-3">
      {/* --- Yuklash zonasi --- */}
      <div
        className={cn(
          'rounded-xl border-2 border-dashed px-5 py-6 text-center transition-colors',
          over ? 'border-primary bg-secondary' : 'border-border bg-card',
        )}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]) }}
      >
        <p className="text-sm font-semibold">Katalog va qoldiqlarni import qilish</p>
        <p className="mt-1 text-[12px] text-muted-foreground">
          .xlsx / .csv — nomi, xususiyatlari, birlik, qoldiq, tannarx
        </p>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          <Button disabled={busy} onClick={() => inputRef.current?.click()}>
            <Icon name="plus" size={14} /> Fayl tanlash
          </Button>
          <Button variant="outline" asChild>
            <a href={apiUrl('/catalog/import/template')}>
              <Icon name="download" size={14} /> Shablon (.xlsx)
            </a>
          </Button>
          <Button variant="outline" asChild>
            <a href={apiUrl('/catalog/import/template?fmt=csv')}>
              <Icon name="download" size={14} /> Shablon (.csv)
            </a>
          </Button>
        </div>
        <input ref={inputRef} type="file" accept=".xlsx,.csv,.txt,.tsv" className="hidden"
          onChange={(e) => pick(e.target.files?.[0])} />
        {file && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-muted px-2.5 py-1.5 text-[12.5px]">
            <Icon name="box" size={13} /> <b>{file.name}</b>
            <span className="text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span>
            <button className="rounded p-0.5 hover:bg-card" title="Bekor qilish" onClick={reset}>
              <Icon name="close" size={13} />
            </button>
          </div>
        )}
      </div>

      {busy && <Note>Fayl tekshirilmoqda…</Note>}
      {error && <Note tone="err">{error}</Note>}

      {/* --- Yakuniy natija --- */}
      {done && (
        <>
          <Note tone="ok">
            Import yakunlandi: <b>{done.inserted}</b> ta qo‘shildi,{' '}
            <b>{done.updated}</b> tasi yangilandi
            {done.rows_error > 0 && <>, {done.rows_error} ta qator o‘tkazib yuborildi</>}.
          </Note>
          <div className="flex gap-2">
            <Button variant="outline" onClick={reset}>Yana yuklash</Button>
            {onClose && <Button variant="ghost" onClick={onClose}>Yopish</Button>}
          </div>
        </>
      )}

      {/* --- Dry-run natijasi --- */}
      {result && <DryRun result={result} busy={busy} onConfirm={confirm}
        onCancel={reset} onClose={onClose} />}
    </div>
  )
}

function Note({ children, tone }: { children: React.ReactNode; tone?: 'ok' | 'err' | 'warn' }) {
  return (
    <div className={cn(
      'rounded-lg border px-3 py-2 text-[13px]',
      tone === 'ok' && 'border-ok/40 bg-ok-soft text-ok',
      tone === 'err' && 'border-urgent/40 bg-urgent-soft text-urgent',
      tone === 'warn' && 'border-soon/40 bg-soon-soft text-soon',
      !tone && 'bg-muted text-muted-foreground',
    )}>{children}</div>
  )
}

// =============================================================================
// Dry-run hisoboti
// =============================================================================
function DryRun({ result, busy, onConfirm, onCancel, onClose }: {
  result: ImportResult
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
  onClose?: () => void
}) {
  const errors = result.errors || []
  const warnings = result.warnings || []
  const detected = Object.entries(result.columns?.detected || {})
  const unknown = result.columns?.unknown || []

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat n={result.rows_total} label="Jami qator" />
        <Stat n={result.rows_ok} label="Qabul qilindi" tone="ok" />
        <Stat n={result.rows_error} label="Xato qator" tone="bad" />
        <Stat n={result.inserted} label="Qo‘shiladi" />
        <Stat n={result.updated} label="Yangilanadi" />
      </div>

      <Note>
        <b>Dastlabki tekshiruv</b> — bazaga hali yozilmadi.
        Sarlavha: {result.header_row}-qator · {(result.format || '').toLowerCase()}
      </Note>

      {/* Qaysi sarlavha qaysi maydonga tushdi */}
      {(detected.length > 0 || unknown.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {detected.map(([field, header]) => (
            <span key={field}
              className="rounded bg-secondary px-2 py-0.5 text-[11.5px] text-primary">
              <b>{field}</b> ← “{String(header)}”
            </span>
          ))}
          {unknown.map((h) => (
            <span key={h} title="Bu ustun tanilmadi va e’tiborga olinmaydi"
              className="rounded bg-muted px-2 py-0.5 text-[11.5px] text-muted-foreground">
              “{h}” — tanilmadi
            </span>
          ))}
        </div>
      )}

      {/* --- XATOLAR: qator bo'yicha (TZ P0-4 mezoni) --- */}
      {errors.length > 0 && (
        <Card className="overflow-hidden border-urgent/40">
          <div className="flex flex-wrap items-baseline gap-2 bg-urgent-soft px-3 py-2">
            <p className="text-[13px] font-semibold text-urgent">
              Xatolar — {result.rows_error} ta qator o‘tmaydi
            </p>
            <span className="text-[12px] text-urgent/80">tuzatib, qayta yuklang</span>
          </div>
          <IssueTable issues={errors} tone="err" />
        </Card>
      )}

      {/* --- OGOHLANTIRISHLAR: qator qabul qilinadi --- */}
      {warnings.length > 0 && (
        <Card className="overflow-hidden border-soon/40">
          <p className="bg-soon-soft px-3 py-2 text-[13px] font-semibold text-soon"
            title="Bu qatorlar baribir qabul qilinadi">
            Ogohlantirishlar — {warnings.length} ta
          </p>
          <IssueTable issues={warnings} tone="warn" />
        </Card>
      )}

      {/* --- QABUL QILINGAN QATORLAR --- */}
      {!!result.preview?.length && (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-baseline gap-2 border-b px-3 py-2">
            <p className="text-[13px] font-semibold">Qabul qilingan qatorlar</p>
            {result.rows_ok > result.preview.length && (
              <span className="text-[12px] text-muted-foreground">
                birinchi {result.preview.length} tasi
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b text-[11px] text-muted-foreground">
                  <th className="w-16 p-2 text-left font-semibold">Qator</th>
                  <th className="p-2 text-left font-semibold">Nomi</th>
                  <th className="p-2 text-left font-semibold">Xususiyatlari</th>
                  <th className="w-20 p-2 text-left font-semibold">Birlik</th>
                  <th className="w-24 p-2 text-right font-semibold">Qoldiq</th>
                  <th className="w-28 p-2 text-right font-semibold">Tannarx</th>
                </tr>
              </thead>
              <tbody>
                {result.preview.map((r) => (
                  <tr key={r.row} className="border-b border-border-soft">
                    <td className="tabular p-2 text-muted-foreground">{r.row}</td>
                    <td className="p-2">{r.name}</td>
                    <td className="p-2 text-muted-foreground">
                      {(r.keywords || []).join(' · ') || '—'}
                    </td>
                    <td className="p-2 text-muted-foreground">{r.unit || '—'}</td>
                    <td className="tabular p-2 text-right">
                      {r.stock_qty ?? <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="tabular p-2 text-right">
                      {r.cost_price != null ? r.cost_price.toLocaleString('ru-RU')
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={onConfirm} disabled={busy || result.rows_ok === 0}>
          <Icon name="check" size={14} />
          {busy ? 'Yuklanmoqda…' : `Tasdiqlash — ${result.rows_ok} ta qator`}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={busy}>Bekor qilish</Button>
        {onClose && <Button variant="ghost" onClick={onClose} disabled={busy}>Yopish</Button>}
        {result.rows_ok === 0 && (
          <span className="text-[12.5px] text-urgent">To‘g‘ri qator yo‘q — xatolarni tuzating.</span>
        )}
      </div>
    </div>
  )
}

function IssueTable({ issues, tone }: {
  issues: ImportResult['errors'] & object
  tone: 'err' | 'warn'
}) {
  return (
    <div className="max-h-[300px] overflow-auto">
      <table className="w-full text-[12.5px]">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b text-[11px] text-muted-foreground">
            <th className="w-16 p-2 text-left font-semibold">Qator</th>
            <th className="w-32 p-2 text-left font-semibold">Ustun</th>
            {tone === 'err' && <th className="w-36 p-2 text-left font-semibold">Qiymat</th>}
            <th className="p-2 text-left font-semibold">{tone === 'err' ? 'Xato' : 'Izoh'}</th>
          </tr>
        </thead>
        <tbody>
          {(issues || []).map((e, i) => (
            <tr key={`${e.row}-${e.field}-${i}`} className="border-b border-border-soft">
              <td className="p-2">
                <span className={cn(
                  'tabular rounded px-1.5 py-0.5 font-semibold',
                  tone === 'err' ? 'bg-urgent-soft text-urgent' : 'bg-soon-soft text-soon',
                )}>{e.row}</span>
              </td>
              <td className="p-2 text-muted-foreground">{e.column}</td>
              {tone === 'err' && (
                <td className="p-2">
                  {e.value
                    ? <span className="rounded bg-muted px-1.5 py-0.5">{e.value}</span>
                    : <span className="text-muted-foreground">— bo‘sh —</span>}
                </td>
              )}
              <td className="p-2">{e.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: 'ok' | 'bad' }) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'bad' ? 'text-urgent' : 'text-foreground'
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-center">
      <div className={cn('tabular text-[19px] font-bold leading-tight', color)}>{n}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  )
}
