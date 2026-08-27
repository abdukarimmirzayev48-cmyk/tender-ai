import { useRef, useState } from 'react'
import { apiUrl, authHeaders, errMatn } from '@/api'
import Icon from './Icon'
import { useT } from '@/i18n'
import type { TKey } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { CompanyDocument, DocumentImportResult, DocumentType } from '@/types'

// HUJJATLAR SHABLONI (P0-8 ga qo'shimcha)
// ═══════════════════════════════════════
// Hujjatlar bazasini birinchi marta to'ldirish — 11 ta formani qo'lda
// kiritish demakdir. Shablon buni bitta faylga aylantiradi: server
// TALAB ETILADIGAN HUJJATLAR RO'YXATI bilan OLDINDAN TO'LDIRILGAN
// .xlsx/.csv beradi, broker raqam va sanalarni yozadi, faylni qaytarib
// yuklaydi. Sinov ma'lumotini kiritish ham shu yo'l bilan.
//
// Ro'yxat SERVERDAN keladi (`/company/document-types` — compliance.DOC_TYPES),
// ya'ni shablondagi hujjatlar tender cheklisti tekshiradigan turlar bilan
// AYNAN bir xil. Bu yerda ikkinchi, qo'lda yozilgan ro'yxat YO'Q — bo'lsa
// ular vaqt o'tib bir-biridan ajralib ketardi.
//
// Yuklash oqimi katalog importi (CatalogImport) bilan bir xil:
//     fayl tanlash -> AVTOMATIK DRY-RUN (bazaga yozilmaydi) -> ko'rish ->
//     "Tasdiqlash". Xato BITTA QATORNI to'xtatadi, importni emas.
//
// Yuklash `fetch` bilan to'g'ridan-to'g'ri: api.ts dagi `request()` JSON
// uchun, multipart (FormData) ni yubora olmaydi.
const MAX_MB = 5

const STATUS_LABEL: Record<string, { text: TKey; cls: string }> = {
  ok: { text: 'compliance.status.ok', cls: 'bg-ok-soft text-ok-strong' },
  expiring_soon: { text: 'compliance.status.expiring_soon', cls: 'bg-soon-soft text-soon-strong' },
  expired: { text: 'compliance.status.expired', cls: 'bg-urgent-soft text-urgent-strong' },
  missing: { text: 'compliance.status.missing', cls: 'bg-urgent-soft text-urgent-strong' },
}

const dateFmt = (iso?: string | null) => (iso ? iso.split('-').reverse().join('.') : '—')

interface DocumentTemplateProps {
  types: DocumentType[]
  docs: CompanyDocument[]
  onImported: () => void
  onClose: () => void
}

export default function DocumentTemplate({
  types, docs, onImported, onClose,
}: DocumentTemplateProps) {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<DocumentImportResult | null>(null)  // dry-run
  const [done, setDone] = useState<DocumentImportResult | null>(null)      // yakuniy
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function send(f: File, dryRun: boolean): Promise<DocumentImportResult> {
    const fd = new FormData()
    fd.append('file', f)
    // FormData yuborilyapti, shuning uchun `api.ts` dagi `request()`
    // emas, xom `fetch`. Kimlik sarlavhasini QO'LDA qo'shamiz —
    // aks holda auth-2 darvozasi 401 qaytaradi.
    const res = await fetch(apiUrl(`/company/documents/import?dry_run=${dryRun}`), {
      method: 'POST', body: fd, headers: authHeaders(),
      credentials: 'include',
    })
    const text = await res.text()
    const body = text ? JSON.parse(text) : null
    if (!res.ok) throw new Error(errMatn(body?.detail) || `${res.status}: ${res.statusText}`)
    return body as DocumentImportResult
  }

  async function pick(f?: File | null) {
    if (!f) return
    setError(null); setResult(null); setDone(null); setFile(f)
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(t('tpl.tooBig', { max: MAX_MB, size: (f.size / 1048576).toFixed(1) }))
      return
    }
    setBusy(true)
    try {
      setResult(await send(f, true))            // DRY-RUN — bazaga tegmaydi
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  async function confirm() {
    if (!file) return
    setBusy(true); setError(null)
    try {
      setDone(await send(file, false))
      setResult(null)
      onImported()
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  function reset() {
    setFile(null); setResult(null); setDone(null); setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="mb-4 max-w-[860px] space-y-3">
      {/* --- Shablonni yuklab olish --- */}
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-title font-semibold">{t('tpl.title')}</h3>
            <p className="mt-1 text-body text-muted-foreground">{t('tpl.lead')}</p>
          </div>
          <button
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title={t('common.close')} aria-label={t('tpl.close')} onClick={onClose}
          >
            <Icon name="close" size={14} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild>
            <a href={apiUrl('/company/documents/template')}>
              <Icon name="download" size={14} /> {t('tpl.xlsx')}
            </a>
          </Button>
          <Button variant="outline" asChild>
            <a href={apiUrl('/company/documents/template?fmt=csv')}>
              <Icon name="download" size={14} /> {t('tpl.csv')}
            </a>
          </Button>
        </div>

        <TemplateContents types={types} docs={docs} />
      </Card>

      {/* --- To'ldirilgan shablonni qaytarib yuklash --- */}
      <div
        className={cn(
          'rounded-xl border-2 border-dashed px-5 py-6 text-center transition-colors',
          over ? 'border-primary bg-secondary' : 'border-border bg-card',
        )}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]) }}
      >
        <p className="text-body font-semibold">{t('tpl.uploadTitle')}</p>
        <p className="mt-1 text-caption text-muted-foreground">{t('tpl.uploadHint')}</p>
        <div className="mt-3">
          <Button disabled={busy} onClick={() => inputRef.current?.click()}>
            <Icon name="clip" size={14} /> {t('tpl.pickFile')}
          </Button>
        </div>
        <input ref={inputRef} type="file" accept=".xlsx,.csv,.txt,.tsv" className="hidden"
          onChange={(e) => pick(e.target.files?.[0])} />
        {file && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-muted px-2.5 py-1.5 text-caption">
            <Icon name="box" size={13} /> <b>{file.name}</b>
            <span className="text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span>
            <button className="rounded p-0.5 hover:bg-card" aria-label={t('common.cancel')} title={t('common.cancel')} onClick={reset}>
              <Icon name="close" size={13} />
            </button>
          </div>
        )}
      </div>

      {busy && <Note>{t('tpl.checking')}</Note>}
      {error && <Note tone="err">{error}</Note>}

      {done && (
        <>
          <Note tone="ok">
            {t('tpl.done', { ins: done.inserted, upd: done.updated })}
            {done.rows_error > 0 && t('tpl.doneSkipped', { n: done.rows_error })}.
          </Note>
          <div className="flex gap-2">
            <Button variant="outline" onClick={reset}>{t('tpl.uploadAgain')}</Button>
            <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
          </div>
        </>
      )}

      {result && <DryRun result={result} busy={busy} onConfirm={confirm} onCancel={reset} />}
    </div>
  )
}

// ============================================================================
// Shablon ichida nima bor — va ulardan qaysi biri bazada allaqachon bor
// ----------------------------------------------------------------------------
// Faylni ochmasdan turib ko'rinsin: qaysi hujjat majburiy, qaysi biri
// tenderga qarab so'raladi va nechtasi allaqachon tayyor. Guruhlash
// SERVERDAGI `base` bayrog'i bo'yicha — ikkalasini bir ro'yxatga qo'ysak,
// foydalanuvchi 11 tasini ham majburiy deb o'ylardi.
// ============================================================================
function TemplateContents({ types, docs }: { types: DocumentType[]; docs: CompanyDocument[] }) {
  const t = useT()
  const [open, setOpen] = useState(true)

  // Tur -> bazadagi eng yaroqli nusxa (eski nusxa tufayli tur "tugagan"
  // bo'lib qolmasin — serverdagi compliance._pick_best() bilan bir xil).
  const rank: Record<string, number> = { ok: 0, expiring_soon: 1, expired: 2 }
  const best = new Map<string, CompanyDocument>()
  for (const d of docs) {
    const cur = best.get(d.doc_type)
    if (!cur || rank[d.status] < rank[cur.status]) best.set(d.doc_type, d)
  }

  const baseTypes = types.filter((x) => x.base)
  const extraTypes = types.filter((x) => !x.base)
  const baseReady = baseTypes.filter((x) => best.get(x.code)?.status === 'ok').length

  if (types.length === 0) {
    return (
      <p className="mt-4 border-t pt-3 text-body text-muted-foreground">
        {t('tpl.contentsFailed')}
      </p>
    )
  }

  const Row = ({ type }: { type: DocumentType }) => {
    const have = best.get(type.code)
    return (
      <div className="flex items-start gap-2.5 py-1.5">
        <span className={cn(
          'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full',
          have ? (have.status === 'ok' ? 'bg-ok-soft text-ok-strong' : 'bg-soon-soft text-soon-strong')
            : 'bg-muted text-muted-foreground')}>
          <Icon name={have ? 'check' : 'plus'} size={10} />
        </span>
        <div className="min-w-0 flex-1">
          <span className="text-body">{type.label}</span>
          {type.hint && (
            <span className="ml-1.5 text-caption text-muted-foreground">— {type.hint}</span>
          )}
        </div>
        {have ? (
          <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-caption font-semibold',
            STATUS_LABEL[have.status]?.cls)}>
            {t(STATUS_LABEL[have.status].text)}
          </span>
        ) : (
          <span className="shrink-0 text-caption text-muted-foreground">{t('tpl.notInBase')}</span>
        )}
      </div>
    )
  }

  return (
    <div className="mt-4 border-t pt-3">
      <button
        className="flex w-full items-center gap-2 text-left text-body font-semibold"
        onClick={() => setOpen((v) => !v)} aria-expanded={open}
      >
        <Icon name="chevron" size={14}
          className={cn('transition-transform', !open && '-rotate-90')} />
        {t('tpl.contents', { n: types.length })}
        <span className="font-normal text-muted-foreground">
          {t('tpl.contentsReady', { n: baseReady, total: baseTypes.length })}
        </span>
      </button>

      {open && (
        <div className="mt-2">
          <p className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted-foreground">
            {t('tpl.groupBase')}
          </p>
          {baseTypes.map((x) => <Row key={x.code} type={x} />)}

          <p className="mb-1 mt-3 text-caption font-semibold uppercase tracking-wide text-muted-foreground">
            {t('tpl.groupExtra')}
          </p>
          {extraTypes.map((x) => <Row key={x.code} type={x} />)}

          <p className="mt-3 text-caption text-muted-foreground">
            {t('tpl.fillHint')}
          </p>
        </div>
      )}
    </div>
  )
}

function Note({ children, tone }: { children: React.ReactNode; tone?: 'ok' | 'err' | 'warn' }) {
  return (
    <div className={cn(
      'rounded-lg border px-3 py-2 text-body',
      tone === 'ok' && 'border-ok/40 bg-ok-soft text-ok-strong',
      tone === 'err' && 'border-urgent/40 bg-urgent-soft text-urgent-strong',
      tone === 'warn' && 'border-soon/40 bg-soon-soft text-soon-strong',
      !tone && 'bg-muted text-muted-foreground',
    )}>{children}</div>
  )
}

// ============================================================================
// Dry-run hisoboti — bazaga yozilishidan OLDIN nima bo'lishini ko'rsatadi
// ============================================================================
function DryRun({ result, busy, onConfirm, onCancel }: {
  result: DocumentImportResult
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const t = useT()
  const errors = result.errors || []
  const warnings = result.warnings || []

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat n={result.rows_total} label={t('imp.totalRows')} />
        <Stat n={result.rows_ok} label={t('imp.acceptedRows')} tone="ok" />
        <Stat n={result.rows_error} label={t('imp.errorRows')} tone="bad" />
        <Stat n={result.inserted} label={t('imp.willInsert')} />
        <Stat n={result.updated} label={t('imp.willUpdate')} />
      </div>

      <Note>
        <b>{t('imp.dryRun')}</b> {t('imp.notWritten')}{' '}
        {t('imp.headerRow', { n: result.header_row })} · {(result.format || '').toLowerCase()}
      </Note>

      {errors.length > 0 && (
        <Card className="overflow-hidden border-urgent/40">
          <div className="flex flex-wrap items-baseline gap-2 bg-urgent-soft px-3 py-2">
            <p className="text-body font-semibold text-urgent-strong">
              {t('imp.errorsTitle', { n: result.rows_error })}
            </p>
            <span className="text-caption text-urgent-strong/80">{t('imp.errorsHint')}</span>
          </div>
          <IssueTable issues={errors} tone="err" />
        </Card>
      )}

      {warnings.length > 0 && (
        <Card className="overflow-hidden border-soon/40">
          <p className="bg-soon-soft px-3 py-2 text-body font-semibold text-soon-strong"
            title={t('imp.warningsHint')}>
            {t('imp.warningsTitle', { n: warnings.length })}
          </p>
          <IssueTable issues={warnings} tone="warn" />
        </Card>
      )}

      {!!result.preview?.length && (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-baseline gap-2 border-b px-3 py-2">
            <p className="text-body font-semibold">{t('tpl.previewTitle')}</p>
            {result.rows_ok > result.preview.length && (
              <span className="text-caption text-muted-foreground">
                {t('imp.firstN', { n: result.preview.length })}
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-caption">
              <thead>
                <tr className="border-b text-micro text-muted-foreground">
                  <th className="w-14 p-2 text-left font-semibold">{t('imp.thRow')}</th>
                  <th className="p-2 text-left font-semibold">{t('tpl.thDoc')}</th>
                  <th className="w-32 p-2 text-left font-semibold">{t('docs.fNumber')}</th>
                  <th className="w-28 p-2 text-left font-semibold">{t('docs.fValid')}</th>
                  <th className="w-36 p-2 text-left font-semibold">{t('stock.thStatus')}</th>
                </tr>
              </thead>
              <tbody>
                {result.preview.map((r) => (
                  <tr key={r.row} className="border-b border-border-soft">
                    <td className="tabular p-2 text-muted-foreground">{r.row}</td>
                    <td className="p-2">
                      <div className="font-medium">{r.name}</div>
                      <div className="text-caption text-muted-foreground">{r.label}</div>
                    </td>
                    <td className="tabular p-2">{r.number || '—'}</td>
                    <td className="tabular p-2">
                      {r.valid_until ? dateFmt(r.valid_until)
                        : <span className="text-muted-foreground">{t('compliance.perpetual')}</span>}
                    </td>
                    <td className="p-2">
                      <span className={cn('rounded px-1.5 py-0.5 text-caption font-semibold',
                        STATUS_LABEL[r.status]?.cls)}>
                        {STATUS_LABEL[r.status] ? t(STATUS_LABEL[r.status].text) : r.status}
                      </span>
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
          {busy ? t('common.loading') : t('tpl.confirm', { n: result.rows_ok })}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={busy}>{t('common.cancel')}</Button>
        {result.rows_ok === 0 && (
          <span className="text-caption text-urgent-strong">{t('tpl.noValidRows')}</span>
        )}
      </div>
    </div>
  )
}

function IssueTable({ issues, tone }: {
  issues: NonNullable<DocumentImportResult['errors']>
  tone: 'err' | 'warn'
}) {
  const t = useT()
  return (
    <div className="max-h-[300px] overflow-auto">
      <table className="w-full text-caption">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b text-micro text-muted-foreground">
            <th className="w-14 p-2 text-left font-semibold">{t('imp.thRow')}</th>
            <th className="w-40 p-2 text-left font-semibold">{t('imp.thColumn')}</th>
            {tone === 'err' && (
              <th className="w-36 p-2 text-left font-semibold">{t('imp.thValue')}</th>
            )}
            <th className="p-2 text-left font-semibold">
              {t(tone === 'err' ? 'imp.thError' : 'imp.thNote')}
            </th>
          </tr>
        </thead>
        <tbody>
          {(issues || []).map((e, i) => (
            <tr key={`${e.row}-${e.field}-${i}`} className="border-b border-border-soft">
              <td className="p-2">
                {/* `row: 0` — butun faylga tegishli yig'ma xabar, aniq qator yo'q */}
                {e.row > 0 ? (
                  <span className={cn(
                    'tabular rounded px-1.5 py-0.5 font-semibold',
                    tone === 'err' ? 'bg-urgent-soft text-urgent-strong' : 'bg-soon-soft text-soon-strong',
                  )}>{e.row}</span>
                ) : <span className="text-muted-foreground">—</span>}
              </td>
              <td className="p-2 text-muted-foreground">{e.column}</td>
              {tone === 'err' && (
                <td className="p-2">
                  {e.value
                    ? <span className="rounded bg-muted px-1.5 py-0.5">{e.value}</span>
                    : <span className="text-muted-foreground">{t('imp.emptyValue')}</span>}
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
  const color = tone === 'ok' ? 'text-ok-strong' : tone === 'bad' ? 'text-urgent-strong' : 'text-foreground'
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-center">
      <div className={cn('tabular text-title font-semibold leading-tight', color)}>{n}</div>
      <div className="text-micro text-muted-foreground">{label}</div>
    </div>
  )
}
