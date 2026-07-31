import { useEffect, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Label } from './CatalogView'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { cn } from '@/lib/utils'
import type { CompanyDocument, DocumentType } from '@/types'

// KOMPANIYA HUJJATLARI BAZASI (P0-8) — akkaunt sahifasidagi bo'lim.
//
// Tender cheklisti (CompliancePanel) AYNAN shu ro'yxatga qarab "bazada bor /
// yo'q" deb belgilaydi. Shuning uchun eng muhim maydon — AMAL QILISH MUDDATI:
// hujjat bor bo'lsa ham muddati tugagan bo'lsa, ariza to'plami to'liq emas.
//
// MVP CHEKLOVI: fayl YUKLASH yo'q. `file_ref` — tashqi havola yoki yo'l.
// Bu ongli soddalashtirish: cheklistning qiymati faylni saqlashda emas,
// TO'LIQLIKNI kuzatishda.
const STATUS: Record<CompanyDocument['status'], { text: string; cls: string }> = {
  ok: { text: 'Yaroqli', cls: 'bg-ok-soft text-ok' },
  expiring_soon: { text: 'Muddati tugayapti', cls: 'bg-soon-soft text-soon' },
  expired: { text: 'Muddati tugagan', cls: 'bg-urgent-soft text-urgent' },
}

const dateFmt = (iso?: string | null) => (iso ? iso.split('-').reverse().join('.') : '—')

export default function CompanyDocuments({ focusType }: { focusType?: string | null }) {
  const [docs, setDocs] = useState<CompanyDocument[]>([])
  const [types, setTypes] = useState<DocumentType[]>([])
  const [editing, setEditing] = useState<CompanyDocument | 'new' | { doc_type: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    api.companyDocuments().then(setDocs).catch((e: Error) => setError(e.message))
  }

  useEffect(() => {
    load()
    api.documentTypes().then(setTypes).catch(() => setTypes([]))
  }, [])

  // Cheklistdan "hujjatlarim bo'limiga o'tish" bosilganda — darhol shu
  // turdagi hujjat formasi ochiladi (foydalanuvchi qidirib yurmasin).
  useEffect(() => {
    if (focusType) setEditing({ doc_type: focusType })
  }, [focusType])

  async function remove(d: CompanyDocument) {
    if (!window.confirm(`"${d.name}" o‘chirilsinmi?`)) return
    setError(null)
    try {
      await api.deleteCompanyDocument(d.id)
      load()
    } catch (e) {
      setError(`"${d.name}" o‘chirilmadi: ${(e as Error).message}`)
    }
  }

  const problems = docs.filter((d) => d.status === 'expired' || d.status === 'expiring_soon')

  return (
    <div>
      <div className="mb-4">
        <Button onClick={() => setEditing('new')}>
          <Icon name="plus" size={14} /> Hujjat qo‘shish
        </Button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-urgent/40 bg-urgent-soft px-3 py-2 text-[13px] text-urgent">
          {error}
        </div>
      )}

      {/* Muddat ogohlantirishi — biznes-jarayon talabi: "muddati tugagan
          bo'lsa tizim brokerga xabar beradi va yangilashni so'raydi". */}
      {problems.length > 0 && (
        <div className="mb-3 rounded-lg border border-soon/40 bg-soon-soft px-3.5 py-2.5 text-[13px] text-soon">
          <b>{problems.length} ta hujjatni yangilash kerak:</b>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {problems.map((d) => (
              <li key={d.id}>
                {d.name} — {d.status === 'expired'
                  ? `muddati tugagan (${dateFmt(d.valid_until)})`
                  : `${d.days_left} kun qoldi (${dateFmt(d.valid_until)})`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {editing && (
        <DocumentForm
          doc={editing === 'new' ? null : (editing as CompanyDocument)}
          types={types}
          onSaved={() => { setEditing(null); load() }}
          onCancel={() => setEditing(null)}
        />
      )}

      {docs.length === 0 && !editing && (
        <Empty className="rounded-xl border border-dashed bg-card">
          <EmptyHeader>
            <EmptyTitle>Hujjatlar bazasi bo‘sh</EmptyTitle>
            <EmptyDescription>
              Guvohnoma va bank rekvizitlaridan boshlang — ular deyarli
              har tenderda so‘raladi.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {docs.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Hujjat</TableHead>
                <TableHead className="w-[140px]">Raqami</TableHead>
                <TableHead className="w-[130px]">Amal qiladi</TableHead>
                <TableHead className="w-[180px]">Holati</TableHead>
                <TableHead className="w-[86px] text-right">Amallar</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map((d) => (
                <TableRow key={d.id} className="hover:bg-transparent">
                  <TableCell>
                    <div className="font-medium">{d.name}</div>
                    <div className="text-[12px] text-muted-foreground">{d.label || d.doc_type}</div>
                  </TableCell>
                  <TableCell className="tabular">{d.number || '—'}</TableCell>
                  <TableCell className="tabular">
                    {d.valid_until ? dateFmt(d.valid_until) : 'muddatsiz'}
                  </TableCell>
                  <TableCell>
                    <span className={cn('rounded px-2 py-0.5 text-[12px] font-semibold',
                      STATUS[d.status]?.cls)}>
                      {STATUS[d.status]?.text || d.status}
                      {d.status === 'expiring_soon' ? ` (${d.days_left} kun)` : ''}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      title="Tahrirlash" aria-label={`${d.name} — tahrirlash`}
                      onClick={() => setEditing(d)}
                    >
                      <Icon name="edit" size={14} />
                    </button>
                    <button
                      className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-urgent-soft hover:text-urgent"
                      title="O‘chirish" aria-label={`${d.name} — o‘chirish`}
                      onClick={() => remove(d)}
                    >
                      <Icon name="trash" size={14} />
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <p className="mt-3 text-[12px] text-muted-foreground">
        Cheklist borlik va muddatni tekshiradi, mazmunni emas.
      </p>
    </div>
  )
}

// Hujjat qo'shish / tahrirlash formasi
function DocumentForm({ doc, types, onSaved, onCancel }: {
  doc: CompanyDocument | null
  types: DocumentType[]
  onSaved: () => void
  onCancel: () => void
}) {
  const editing = !!doc?.id
  const [docType, setDocType] = useState(doc?.doc_type || '')
  const [name, setName] = useState(doc?.name || '')
  const [number, setNumber] = useState(doc?.number || '')
  const [issuedAt, setIssuedAt] = useState(doc?.issued_at || '')
  const [validUntil, setValidUntil] = useState(doc?.valid_until || '')
  const [perpetual, setPerpetual] = useState(!!doc?.id && !doc?.valid_until)
  const [fileName, setFileName] = useState(doc?.file_name || '')
  const [fileRef, setFileRef] = useState(doc?.file_ref || '')
  const [note, setNote] = useState(doc?.note || '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // Tur tanlanganda nom bo'sh bo'lsa — kanonik nom bilan to'ldiramiz
  function pickType(code: string) {
    setDocType(code)
    const t = types.find((x) => x.code === code)
    if (t && !name.trim()) setName(t.label)
  }

  async function save() {
    if (!docType) { setMsg({ ok: false, text: 'Hujjat turini tanlang.' }); return }
    if (!name.trim()) { setMsg({ ok: false, text: 'Hujjat nomini kiriting.' }); return }
    setSaving(true); setMsg(null)
    const body = {
      doc_type: docType,
      name: name.trim(),
      number: number.trim() || null,
      issued_at: issuedAt || null,
      // "Muddatsiz" belgilansa valid_until = null: cheklist buni "ma'lumot
      // yo'q" emas, "cheklanmagan" deb tushunadi.
      valid_until: perpetual ? null : (validUntil || null),
      file_name: fileName.trim() || null,
      file_ref: fileRef.trim() || null,
      note: note.trim() || null,
    }
    try {
      if (editing) await api.updateCompanyDocument(doc!.id, body)
      else await api.createCompanyDocument(body)
      onSaved()
    } catch (e) { setMsg({ ok: false, text: 'Xatolik: ' + (e as Error).message }) }
    finally { setSaving(false) }
  }

  const hint = types.find((t) => t.code === docType)?.hint

  return (
    <Card className="mb-4 max-w-[760px] p-5">
      <h3 className="mb-4 text-[17px] font-bold">
        {editing ? 'Hujjatni tahrirlash' : 'Yangi hujjat'}
      </h3>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Label text="Hujjat turi *" note={hint || undefined}>
          <Select value={docType || 'none'} onValueChange={(v) => pickType(v === 'none' ? '' : v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— tanlang —</SelectItem>
              {types.map((t) => <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </Label>
        <Label text="Nomi *">
          <Input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Davlat ro‘yxatidan o‘tganlik guvohnomasi" />
        </Label>
        <Label text="Raqami">
          <Input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="AA 1234567" />
        </Label>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Label text="Berilgan sana">
          <Input type="date" value={issuedAt || ''} onChange={(e) => setIssuedAt(e.target.value)} />
        </Label>
        <Label text="Amal qiladi">
          <Input type="date" value={validUntil || ''} disabled={perpetual}
            onChange={(e) => setValidUntil(e.target.value)} />
        </Label>
        <label className="flex items-end gap-2 pb-2.5 text-[13px]">
          <Checkbox checked={perpetual} onCheckedChange={(v) => setPerpetual(v === true)} />
          <span>Muddatsiz</span>
        </label>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_2fr]">
        <Label text="Fayl nomi">
          <Input value={fileName} onChange={(e) => setFileName(e.target.value)}
            placeholder="guvohnoma.pdf" />
        </Label>
        <Label text="Havola / yo‘l">
          <Input value={fileRef} onChange={(e) => setFileRef(e.target.value)}
            placeholder="https://… yoki diskdagi yo‘l" />
        </Label>
      </div>

      <Label text="Izoh">
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </Label>

      <div className="mt-5 flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? 'Saqlanmoqda…' : (editing ? 'Yangilash' : 'Qo‘shish')}
        </Button>
        <Button variant="ghost" onClick={onCancel}>Bekor qilish</Button>
        {msg && (
          <span className={cn('text-[13px]', msg.ok ? 'text-ok' : 'text-urgent')}>{msg.text}</span>
        )}
      </div>
    </Card>
  )
}
