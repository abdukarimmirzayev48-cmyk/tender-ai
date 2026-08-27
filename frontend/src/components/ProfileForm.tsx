import { useState } from 'react'
import { api } from '@/api'
import { Label, TagField } from './CatalogView'
import { useT } from '@/i18n'
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
  const t = useT()
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
    if (!name.trim()) { setMsg({ ok: false, text: t('sf.errNoName') }); return }
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
      setMsg({ ok: false, text: t('common.errorWith', { msg: (e as Error).message }) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="max-w-[760px] p-6">
      <h2 className="text-title font-semibold">
        {t(editing ? 'sf.editTitle' : 'sf.newTitle')}
      </h2>
      <p className="mb-5 mt-1 text-body text-muted-foreground">{t('sf.lead')}</p>

      <div className="mb-4">
        <Label text={t('sf.fName')}>
          <Input value={name} onChange={(e) => setName(e.target.value)}
            placeholder={t('sf.fNamePh')} />
        </Label>
      </div>

      <div className="mb-4">
        <Label text={t('sf.fKeywords')} note={t('sf.fKeywordsNote')}>
          <TagField value={keywords} input={kwInput} setInput={setKwInput} add={addKw}
            onRemove={(k) => setKeywords(keywords.filter((x) => x !== k))}
            placeholder={t('sf.fKeywordsPh')} />
        </Label>
      </div>

      <div className="mb-4">
        <span className="mb-1.5 block text-body font-semibold">{t('sf.regions')}</span>
        <span className="mb-2 block text-micro text-muted-foreground">{t('sf.regionsHint')}</span>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {regions.map((r) => (
            <label className="flex cursor-pointer items-center gap-2 text-body" key={r.area_id}>
              <Checkbox checked={selRegions.includes(r.area_id)}
                onCheckedChange={() => toggleRegion(r.area_id)} />
              {r.name}
            </label>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Label text={t('sf.fCurrency')}>
          <Select value={currency || 'any'} onValueChange={(v) => setCurrency(v === 'any' ? '' : v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">{t('sf.anyCurrency')}</SelectItem>
              <SelectItem value="UZS">UZS</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
            </SelectContent>
          </Select>
        </Label>
        <Label text={t('sf.fMinBudget')}>
          <Input className="tabular" type="number" value={minCost}
            onChange={(e) => setMinCost(e.target.value)} placeholder="0" />
        </Label>
        <Label text={t('sf.fMaxBudget')}>
          <Input className="tabular" type="number" value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)} placeholder={t('sf.fMaxBudgetPh')} />
        </Label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? t('common.saving') : t(editing ? 'common.update' : 'common.save')}
        </Button>
        <Button variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        {msg && (
          <span className={cn('text-body', msg.ok ? 'text-ok-strong' : 'text-urgent-strong')}>{msg.text}</span>
        )}
      </div>
    </Card>
  )
}
