import { useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import CatalogImport from './CatalogImport'
import { money } from '@/format'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { cn } from '@/lib/utils'
import type { Category, Product } from '@/types'

// Mahsulot katalogi: mijoz sotadigan mahsulot/xizmatlar. Har biriga kategoriya
// biriktiriladi -> "Sizga mos" shu katalogga qarab tenderlarni topadi.
interface CatalogViewProps {
  items: Product[]
  categories: Category[]
  onChanged: () => void
  onOpenMatch: (p: Product) => void
}

export default function CatalogView({ items, categories, onChanged, onOpenMatch }: CatalogViewProps) {
  const [editing, setEditing] = useState<Product | 'new' | null>(null)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // O'chirish xatosi KO'RINISHI kerak. Ilgari `await api.deleteProduct(...)`
  // to'g'ridan-to'g'ri onClick ichida edi: rad etilgan promise jimgina yo'qolar,
  // foydalanuvchi esa "tugma ishlamayapti" deb ko'rardi.
  async function remove(p: Product) {
    if (!window.confirm(`"${p.name}" o‘chirilsinmi?`)) return
    setError(null)
    try {
      await api.deleteProduct(p.id)
      onChanged()
    } catch (e) {
      setError(`"${p.name}" o‘chirilmadi: ${(e as Error).message}`)
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-muted-foreground">
          Nima sotasiz? Kiritganingizga qarab “Sizga mos” tenderlarni topadi.
        </p>
        <div className="flex gap-2">
          {/* P0-4 — Excel/CSV/Google Sheets dan ommaviy import */}
          <Button variant="outline" onClick={() => setImporting((v) => !v)}>
            <Icon name="download" size={14} /> Import
          </Button>
          <Button onClick={() => setEditing('new')}>
            <Icon name="plus" size={14} /> Mahsulot qo‘shish
          </Button>
        </div>
      </div>

      {importing && <CatalogImport onImported={onChanged} onClose={() => setImporting(false)} />}

      {error && (
        <div className="mb-3 rounded-lg border border-urgent/40 bg-urgent-soft px-3 py-2 text-[13px] text-urgent">
          {error}
        </div>
      )}

      {editing && (
        <ProductForm
          product={editing === 'new' ? null : editing}
          categories={categories}
          onSaved={() => { setEditing(null); onChanged() }}
          onCancel={() => setEditing(null)}
        />
      )}

      {items.length === 0 && !editing && (
        <Empty className="rounded-xl border border-dashed bg-card">
          <EmptyHeader>
            <EmptyTitle>Katalog bo‘sh</EmptyTitle>
            <EmptyDescription>Birinchi mahsulotni qo‘shing.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Mahsulot / xizmat</TableHead>
                <TableHead className="w-[180px]">Kategoriya</TableHead>
                <TableHead className="w-[140px] text-right">Narx</TableHead>
                <TableHead className="w-[110px] text-right">Qoldiq</TableHead>
                <TableHead className="w-[110px] text-right">Mos tender</TableHead>
                <TableHead className="w-[86px] text-right">Amallar</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((p) => (
                <TableRow key={p.id} className="hover:bg-transparent">
                  <TableCell>
                    <div className="font-medium">{p.name}</div>
                    {p.keywords.length > 0 && (
                      <div className="text-[12px] text-muted-foreground">
                        {p.keywords.join(' · ')}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {catName(categories, p.category_code)}
                  </TableCell>
                  <TableCell className="tabular text-right">
                    {p.price != null ? money(p.price, p.currency) : '—'}
                    {p.unit ? <span className="text-muted-foreground"> /{p.unit}</span> : null}
                  </TableCell>
                  <TableCell className="tabular text-right">
                    {p.stock_qty != null
                      ? <>{p.stock_qty}<span className="text-muted-foreground"> {p.stock_unit || ''}</span></>
                      : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="tabular text-right">
                    {p.match_count > 0 ? (
                      <button
                        className="font-semibold text-primary underline-offset-2 hover:underline"
                        onClick={() => onOpenMatch(p)}
                      >{p.match_count}</button>
                    ) : <span className="text-muted-foreground">0</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      title="Tahrirlash" aria-label={`${p.name} — tahrirlash`}
                      onClick={() => setEditing(p)}
                    >
                      <Icon name="edit" size={14} />
                    </button>
                    <button
                      className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-urgent-soft hover:text-urgent"
                      title="O‘chirish" aria-label={`${p.name} — o‘chirish`}
                      onClick={() => remove(p)}
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
    </div>
  )
}

function catName(tree: Category[], code: string | null) {
  if (!code) return '— kategoriyasiz —'
  for (const p of tree) {
    if (p.code === code) return p.name
    for (const c of p.children) if (c.code === code) return c.name
  }
  return code
}

// Mahsulot qo'shish/tahrirlash formasi
function ProductForm({ product, categories, onSaved, onCancel }: {
  product: Product | null
  categories: Category[]
  onSaved: () => void
  onCancel: () => void
}) {
  const editing = !!product?.id
  const [name, setName] = useState(product?.name || '')
  const [cat, setCat] = useState(product?.category_code || '')
  const [price, setPrice] = useState(product?.price != null ? String(product.price) : '')
  const [unit, setUnit] = useState(product?.unit || '')
  const [currency, setCurrency] = useState(product?.currency || 'UZS')
  const [keywords, setKeywords] = useState<string[]>(product?.keywords || [])
  const [kwInput, setKwInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  function addKw() {
    const v = kwInput.trim()
    if (v && !keywords.includes(v)) setKeywords([...keywords, v])
    setKwInput('')
  }

  async function save() {
    if (!name.trim()) { setMsg({ ok: false, text: 'Mahsulot nomini kiriting.' }); return }
    setSaving(true); setMsg(null)
    const body = {
      name: name.trim(), category_code: cat || null, keywords,
      unit: unit || null, price: price === '' ? null : Number(price),
      currency: currency || null, notify: true,
    }
    try {
      if (editing) await api.updateProduct(product!.id, body)
      else await api.createProduct(body)
      onSaved()
    } catch (e) { setMsg({ ok: false, text: 'Xatolik: ' + (e as Error).message }) }
    finally { setSaving(false) }
  }

  return (
    <Card className="mb-4 max-w-[760px] p-5">
      <h3 className="mb-4 text-[17px] font-bold">
        {editing ? 'Mahsulotni tahrirlash' : 'Yangi mahsulot / xizmat'}
      </h3>

      <div className="mb-4 grid gap-3 sm:grid-cols-[2fr_1fr]">
        <Label text="Nomi *">
          <Input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="masalan: Ofis mebeli, Yo‘l qurilishi xizmati" />
        </Label>
        <Label text="Kategoriya">
          <Select value={cat || 'none'} onValueChange={(v) => setCat(v === 'none' ? '' : v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— tanlang —</SelectItem>
              {categories.map((p) => (
                <SelectGroup key={p.code}>
                  <SelectLabel>{p.name}</SelectLabel>
                  <SelectItem value={p.code}>{p.name} (hammasi)</SelectItem>
                  {p.children.map((c) => (
                    <SelectItem key={c.code} value={c.code}>— {c.name}</SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
        </Label>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Label text="Narx">
          <Input className="tabular" type="number" value={price}
            onChange={(e) => setPrice(e.target.value)} placeholder="0" />
        </Label>
        <Label text="Valyuta">
          <Select value={currency} onValueChange={setCurrency}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="UZS">UZS</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
            </SelectContent>
          </Select>
        </Label>
        <Label text="Birlik">
          <Input value={unit} onChange={(e) => setUnit(e.target.value)}
            placeholder="dona, m², xizmat" />
        </Label>
      </div>

      <Label text="Kalit so‘zlar" note="Aniq nom bo‘yicha ham moslashtiradi.">
        <TagField value={keywords} input={kwInput} setInput={setKwInput} add={addKw}
          onRemove={(k) => setKeywords(keywords.filter((x) => x !== k))}
          placeholder="монитор, стол… (Enter)" />
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

export function Label({ text, note, children }: {
  text: string
  note?: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-semibold">{text}</span>
      {children}
      {note && <span className="mt-1 block text-[11px] text-muted-foreground">{note}</span>}
    </label>
  )
}

export function TagField({ value, input, setInput, add, onRemove, placeholder }: {
  value: string[]
  input: string
  setInput: (v: string) => void
  add: () => void
  onRemove: (k: string) => void
  placeholder?: string
}) {
  return (
    <div className="flex flex-wrap gap-1.5 rounded-md border border-input bg-card p-1.5">
      {value.map((k) => (
        <span key={k}
          className="inline-flex items-center gap-1 rounded-full bg-secondary py-0.5 pl-2.5 pr-1 text-[12px] text-primary">
          {k}
          <button className="px-0.5 text-[15px] leading-none" onClick={() => onRemove(k)}>×</button>
        </span>
      ))}
      <input
        className="min-w-[160px] flex-1 bg-transparent p-1 text-[13px] outline-none placeholder:text-muted-foreground"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
        placeholder={placeholder}
      />
    </div>
  )
}
