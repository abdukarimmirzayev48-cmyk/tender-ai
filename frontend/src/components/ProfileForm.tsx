import { useState } from 'react'
import { api } from '@/api'
import { Label, TagField } from './CatalogView'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { Region, SavedSearch } from '@/types'

// Saqlangan qidiruv muharriri. `search` berilsa — tahrirlaydi, aks holda yangi.
interface ProfileFormProps {
  search: SavedSearch | null
  regions: Region[]
  onSaved?: () => void
  onCancel: () => void
}

export default function ProfileForm({ search, regions, onSaved, onCancel }: ProfileFormProps) {
  const editing = !!search?.id
  const [name, setName] = useState(search?.name || '')
  const [keywords, setKeywords] = useState<string[]>(search?.keywords || [])
  const [kwInput, setKwInput] = useState('')
  const [selRegions, setSelRegions] = useState<string[]>(search?.regions || [])
  const [currency, setCurrency] = useState(search?.currency || '')
  const [minCost, setMinCost] = useState(search?.min_cost != null ? String(search.min_cost) : '')
  const [maxCost, setMaxCost] = useState(search?.max_cost != null ? String(search.max_cost) : '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  function addKw() {
    const v = kwInput.trim()
    if (v && !keywords.includes(v)) setKeywords([...keywords, v])
    setKwInput('')
  }
  function toggleRegion(id: string) {
    setSelRegions((r) => r.includes(id) ? r.filter((x) => x !== id) : [...r, id])
  }

  async function save() {
    if (!name.trim()) { setMsg({ ok: false, text: 'Qidiruvga nom bering.' }); return }
    setSaving(true); setMsg(null)
    const body = {
      name: name.trim(),
      keywords,
      regions: selRegions,
      currency: currency || null,
      min_cost: minCost === '' ? null : Number(minCost),
      max_cost: maxCost === '' ? null : Number(maxCost),
    }
    try {
      if (editing) await api.updateSearch(search!.id, body)
      else await api.createSearch(body)
      onSaved?.()
    } catch (e) {
      setMsg({ ok: false, text: 'Xatolik: ' + (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="max-w-[760px] p-6">
      <h2 className="text-[18px] font-bold">
        {editing ? 'Qidiruvni tahrirlash' : 'Yangi qidiruv'}
      </h2>
      <p className="mb-5 mt-1 text-[13px] text-muted-foreground">
        Saqlangach chap panelda mos tenderlar soni bilan turadi.
      </p>

      <div className="mb-4">
        <Label text="Nomi *">
          <Input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Kompyuter texnikasi" />
        </Label>
      </div>

      <div className="mb-4">
        <Label text="Kalit so‘zlar" note="Ruscha/kirill yozing — manba ma'lumoti shunday.">
          <TagField value={keywords} input={kwInput} setInput={setKwInput} add={addKw}
            onRemove={(k) => setKeywords(keywords.filter((x) => x !== k))}
            placeholder="мебель, компьютер, услуги… (Enter)" />
        </Label>
      </div>

      <div className="mb-4">
        <span className="mb-1.5 block text-[13px] font-semibold">Hududlar</span>
        <span className="mb-2 block text-[11px] text-muted-foreground">
          Bo‘sh — butun respublika.
        </span>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {regions.map((r) => (
            <label className="flex cursor-pointer items-center gap-2 text-[13px]" key={r.area_id}>
              <Checkbox checked={selRegions.includes(r.area_id)}
                onCheckedChange={() => toggleRegion(r.area_id)} />
              {r.name}
            </label>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Label text="Valyuta">
          <Select value={currency || 'any'} onValueChange={(v) => setCurrency(v === 'any' ? '' : v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Farqsiz</SelectItem>
              <SelectItem value="UZS">UZS</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
            </SelectContent>
          </Select>
        </Label>
        <Label text="Min byudjet">
          <Input className="tabular" type="number" value={minCost}
            onChange={(e) => setMinCost(e.target.value)} placeholder="0" />
        </Label>
        <Label text="Max byudjet">
          <Input className="tabular" type="number" value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)} placeholder="cheksiz" />
        </Label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? 'Saqlanmoqda…' : (editing ? 'Yangilash' : 'Saqlash')}
        </Button>
        <Button variant="ghost" onClick={onCancel}>Bekor qilish</Button>
        {msg && (
          <span className={cn('text-[13px]', msg.ok ? 'text-ok' : 'text-urgent')}>{msg.text}</span>
        )}
      </div>
    </Card>
  )
}
