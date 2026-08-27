import { useEffect, useState } from 'react'
import { api } from '@/api'
import { Label, TagField } from './CatalogView'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { CompanyProfileData, Region } from '@/types'

// AKKAUNT — foydalanuvchi ma'lumotlari + kompaniya profili.
//
// Sozlamalar KATEGORIYALARGA bo'lingan (menyu — `AccountSettings.tsx`), lekin
// HOLAT VA SAQLASH BITTA bo'lib qoladi: profil serverda bitta yozuv. Komponent
// butun `p` ni ushlab turadi va faqat KO'RSATILADIGAN guruhlarni almashtiradi.
// Shu sabab bo'limlar orasida yurganda saqlanmagan o'zgarishlar YO'QOLMAYDI.
//
// Kompaniya qismi Go/No-Go 11 mezoni tartibida qurilgan: har guruh qaysi
// mezonni yopishini raqam bilan ko'rsatadi.
export type Section = 'profile' | 'company' | 'capacity' | 'criteria'

/** Formadagi holat — inputlar boshqariladigan bo'lishi uchun `null` o'rniga `''` */
type FormState = Omit<CompanyProfileData,
  'experience_years' | 'max_contract_value' | 'employees' | 'lead_time_days' |
  'min_margin_percent' | 'min_cost' | 'max_cost' | 'contact_name' | 'email' |
  'phone' | 'position' | 'name' | 'about' | 'capacity_note' | 'constraints_note'
> & Record<
  'contact_name' | 'email' | 'phone' | 'position' | 'name' | 'about' |
  'capacity_note' | 'constraints_note' | 'experience_years' | 'max_contract_value' |
  'employees' | 'lead_time_days' | 'min_margin_percent' | 'min_cost' | 'max_cost',
  string
>

const empty: FormState = {
  contact_name: '', email: '', phone: '', position: '',
  name: '', about: '', constraints_note: '',
  certificates: [], clearances: [],
  experience_years: '', max_contract_value: '', max_contract_currency: 'UZS',
  employees: '', capacity_note: '', lead_time_days: '',
  min_margin_percent: '', regions: [], min_cost: '', max_cost: '',
  keywords: [], currency: null,
}

// Har bo'lim qaysi Go/No-Go mezonlarini yopadi. Menyudagi "N/M" rozetkasi
// SHU jadvaldan quriladi — mezonlar ro'yxati bitta joyda tursin, aks holda
// menyu bilan forma bir-biridan uzoqlashadi.
// ("Profil" bo'limi — aloqa ma'lumotlari, u mezon yopmaydi.)
const CRITERIA: Record<string, ((p: FormState) => boolean)[]> = {
  company: [
    (p) => !!p.about,                               //  2  faoliyat
    (p) => p.certificates.length > 0,               //  3  sertifikat
    (p) => p.clearances.length > 0,                 //  9  xavfsizlik ruxsati
  ],
  capacity: [
    (p) => has(p.max_contract_value),               //  4  moliyaviy salohiyat
    (p) => has(p.experience_years),                 //  5  tajriba
    (p) => has(p.lead_time_days),                   //  6  muddat
    (p) => p.regions.length > 0,                    //  7  hudud
    (p) => has(p.employees) || !!p.capacity_note,   //  8  resurs
  ],
  criteria: [
    (p) => has(p.min_cost) || has(p.max_cost),      // 10  summa
    (p) => has(p.min_margin_percent),               // 11  foyda
  ],
}

export interface SectionProgress { done: number; total: number }

// Bo'lim -> {done, total}. Jami 10 ta mezon (1-mezon asosan tenderdan o'qiladi).
export function progress(p: FormState): Record<string, SectionProgress> {
  const out: Record<string, SectionProgress> = {}
  for (const [key, checks] of Object.entries(CRITERIA)) {
    out[key] = { done: checks.filter((f) => f(p)).length, total: checks.length }
  }
  return out
}

interface CompanyProfileProps {
  section?: Section
  onSaved?: (p: CompanyProfileData) => void
  onProgress?: (m: Record<string, SectionProgress>) => void
}

export default function CompanyProfile({
  section = 'profile', onSaved, onProgress,
}: CompanyProfileProps) {
  const t = useT()
  const [p, setP] = useState<FormState | null>(null)
  const [regions, setRegions] = useState<Region[]>([])
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    api.getProfile()
      .then((r) => setP(r ? { ...empty, ...blanks(r) } : { ...empty }))
      .catch(() => setP({ ...empty }))
    api.regions().then((rs) => setRegions(rs.filter((r) => r.level === 1))).catch(() => {})
  }, [])

  // Menyu rozetkalari HAR TUGMACHADAN keyin yangilansin — foydalanuvchi
  // maydonni to'ldirishi bilan "N/M" o'sganini ko'radi (saqlashni kutmasdan).
  useEffect(() => { if (p) onProgress?.(progress(p)) }, [p, onProgress])

  if (!p) return null
  const cur = p
  const set = (k: keyof FormState) => (e: { target: { value: string } }) =>
    setP({ ...cur, [k]: e.target.value })

  async function save() {
    setSaving(true); setMsg(null)
    try {
      const saved = await api.saveProfile({
        ...cur,
        contact_name: cur.contact_name || null,
        email: cur.email || null,
        phone: cur.phone || null,
        position: cur.position || null,
        name: cur.name || null,
        about: cur.about || null,
        capacity_note: cur.capacity_note || null,
        constraints_note: cur.constraints_note || null,
        experience_years: num(cur.experience_years),
        max_contract_value: num(cur.max_contract_value),
        employees: num(cur.employees),
        lead_time_days: num(cur.lead_time_days),
        min_margin_percent: num(cur.min_margin_percent),
        min_cost: num(cur.min_cost),
        max_cost: num(cur.max_cost),
      })
      setMsg({ ok: true, text: t('cp.saved') })
      onSaved?.(saved)
    } catch (e) {
      setMsg({ ok: false, text: t('common.errorWith', { msg: (e as Error).message }) })
    }
    finally { setSaving(false) }
  }

  return (
    <div>
      {/* ---------- PROFIL: aloqa ma'lumotlari ---------- */}
      {section === 'profile' && (
        <>
          <Group title={t('cp.gUser')}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Label text={t('cp.fName')}>
                <Input value={p.contact_name} onChange={set('contact_name')}
                  placeholder={t('cp.fNamePh')} />
              </Label>
              <Label text={t('cp.fPosition')}>
                <Input value={p.position} onChange={set('position')}
                  placeholder={t('cp.fPositionPh')} />
              </Label>
              <Label text={t('cp.fEmail')}>
                <Input type="email" value={p.email} onChange={set('email')}
                  placeholder={t('cp.fEmailPh')} />
              </Label>
              <Label text={t('cp.fPhone')}>
                <Input type="tel" value={p.phone} onChange={set('phone')}
                  placeholder="+998 90 123 45 67" />
              </Label>
            </div>
          </Group>
          <p className="mt-3 text-caption text-muted-foreground">
            {t('cp.emailNote')}
          </p>
        </>
      )}

      {/* ---------- KOMPANIYA: kim siz va nima qila olasiz ---------- */}
      {section === 'company' && (
        <>
          <Group title={t('cp.gActivity')}>
            <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
              <Label text={t('cp.fCompany')}>
                <Input value={p.name} onChange={set('name')} placeholder={t('cp.fCompanyPh')} />
              </Label>
              <Label text={t('cp.fAbout')}>
                <Input value={p.about} onChange={set('about')}
                  placeholder={t('cp.fAboutPh')} />
              </Label>
            </div>
          </Group>

          <Group n="3" title={t('cp.gCerts')}>
            <Tags value={p.certificates} onChange={(v) => setP({ ...cur, certificates: v })}
              placeholder={t('cp.gCertsPh')} />
          </Group>

          <Group n="9" title={t('cp.gClear')}>
            <Tags value={p.clearances} onChange={(v) => setP({ ...cur, clearances: v })}
              placeholder={t('cp.gClearPh')} />
          </Group>
        </>
      )}

      {/* ---------- SALOHIYAT: qanchani va qayerda uddalaysiz ---------- */}
      {section === 'capacity' && (
        <>
          <Group n="4" title={t('cp.gFinance')}>
            <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
              <Label text={t('cp.fMaxContract')} note={t('cp.fMaxContractNote')}>
                <Input className="tabular" type="number" min="0" value={p.max_contract_value}
                  onChange={set('max_contract_value')} placeholder="500000000" />
              </Label>
              <Label text={t('cp.fCurrency')}>
                <Select value={p.max_contract_currency || 'UZS'}
                  onValueChange={(v) => setP({ ...cur, max_contract_currency: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="UZS">UZS</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                  </SelectContent>
                </Select>
              </Label>
            </div>
          </Group>

          <Group n="5,6" title={t('cp.gExp')}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Label text={t('cp.fExpYears')}>
                <Input className="tabular" type="number" min="0" value={p.experience_years}
                  onChange={set('experience_years')} placeholder="5" />
              </Label>
              <Label text={t('cp.fLeadTime')}>
                <Input className="tabular" type="number" min="0" value={p.lead_time_days}
                  onChange={set('lead_time_days')} placeholder="30" />
              </Label>
            </div>
          </Group>

          <Group n="8" title={t('cp.gResource')}>
            <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
              <Label text={t('cp.fEmployees')}>
                <Input className="tabular" type="number" min="0" value={p.employees}
                  onChange={set('employees')} placeholder="25" />
              </Label>
              <Label text={t('cp.fCapacityNote')}>
                <Input value={p.capacity_note} onChange={set('capacity_note')}
                  placeholder={t('cp.fCapacityNotePh')} />
              </Label>
            </div>
          </Group>

          <Group n="7" title={t('cp.gRegions')}>
            <div className="flex flex-wrap gap-1.5">
              {regions.map((r) => {
                const on = p.regions.includes(r.area_id)
                return (
                  <button key={r.area_id} type="button"
                    className={cn(
                      'rounded-full border px-3 py-1 text-caption transition-colors',
                      on
                        ? 'border-primary bg-secondary font-semibold text-primary'
                        : 'border-border bg-card hover:bg-accent',
                    )}
                    onClick={() => setP({
                      ...cur,
                      regions: on ? cur.regions.filter((x) => x !== r.area_id)
                        : [...cur.regions, r.area_id],
                    })}>
                    {r.name || r.area_id}
                  </button>
                )
              })}
            </div>
            <span className="mt-1.5 block text-micro text-muted-foreground">{t('cp.regionsHint')}</span>
          </Group>
        </>
      )}

      {/* ---------- TENDER MEZONLARI: qaysi tenderni olasiz ---------- */}
      {section === 'criteria' && (
        <>
          <Group n="10,11" title={t('cp.gAmount')}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Label text={t('cp.fMinCost')}>
                <Input className="tabular" type="number" min="0" value={p.min_cost}
                  onChange={set('min_cost')} placeholder="10000000" />
              </Label>
              <Label text={t('cp.fMaxCost')}>
                <Input className="tabular" type="number" min="0" value={p.max_cost}
                  onChange={set('max_cost')} placeholder="800000000" />
              </Label>
              <Label text={t('cp.fMinMargin')}>
                <Input className="tabular" type="number" min="0" max="100" step="0.5"
                  value={p.min_margin_percent} onChange={set('min_margin_percent')}
                  placeholder="15" />
              </Label>
            </div>
          </Group>

          <Group n="1" title={t('cp.gConstraints')}>
            <Input value={p.constraints_note} onChange={set('constraints_note')}
              placeholder={t('cp.gConstraintsPh')} />
          </Group>
        </>
      )}

      <div className="mt-5 flex items-center gap-3 border-t pt-4">
        <Button onClick={save} disabled={saving}>
          {saving ? t('common.saving') : t('common.save')}
        </Button>
        {msg && (
          <span className={cn('text-body', msg.ok ? 'text-ok-strong' : 'text-urgent-strong')}>{msg.text}</span>
        )}
      </div>
    </div>
  )
}

function Group({ n, title, children }: {
  n?: string
  title: string
  children: React.ReactNode
}) {
  const t = useT()
  return (
    <div className="border-b border-border-soft py-3 last:border-0">
      <div className="mb-2 flex items-center gap-2 text-micro font-semibold text-muted-foreground">
        {n && (
          <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-secondary px-1.5 text-micro text-primary"
            title={t('cp.criterionTitle')}>{n}</span>
        )}
        {title}
      </div>
      {children}
    </div>
  )
}

function Tags({ value, onChange, placeholder }: {
  value: string[]
  onChange: (v: string[]) => void
  placeholder?: string
}) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !value.includes(v)) onChange([...value, v])
    setInput('')
  }
  return (
    <TagField value={value} input={input} setInput={setInput} add={add}
      onRemove={(k) => onChange(value.filter((x) => x !== k))} placeholder={placeholder} />
  )
}

// null -> '' (React nazorat qilinadigan inputlar uchun)
function blanks(o: CompanyProfileData): Partial<FormState> {
  const out: Record<string, unknown> = { ...o }
  for (const k of ['contact_name', 'email', 'phone', 'position', 'name', 'about',
    'capacity_note', 'constraints_note', 'experience_years',
    'max_contract_value', 'employees', 'lead_time_days',
    'min_margin_percent', 'min_cost', 'max_cost']) {
    if (out[k] == null) out[k] = ''
    else out[k] = String(out[k])
  }
  if (!Array.isArray(out.regions)) out.regions = []
  if (!Array.isArray(out.certificates)) out.certificates = []
  if (!Array.isArray(out.clearances)) out.clearances = []
  return out as Partial<FormState>
}
const num = (v: string) => (v === '' || v == null ? null : Number(v))
const has = (v: string) => v !== '' && v != null
