import { useEffect, useRef, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Label } from './CatalogView'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { cn } from '@/lib/utils'
import type { NotifySettingsData, TelegramLink, TelegramSubscriber } from '@/types'

// BILDIRISHNOMA sozlamalari (TZ P0-10)
// ====================================
// Xabarni `notify_new.py` ETL dan keyin yuboradi; bu forma faqat KIMGA va
// QAYSI CHEGARADAN yuqorida ketishini boshqaradi.
//
// FOYDALANUVCHI NIMA KIRITADI: email manzili va moslik chegarasi. TAMOM.
//   * Pochta SERVERI (host/port/login/parol) — PLATFORMA sozlamasi, `.env` da.
//     Foydalanuvchi unga javob bera olmaydi va bermasligi ham kerak.
//   * Telegram CHAT ID — qo'lda kiritilmaydi. "Telegramni ulash" tugmasi bir
//     martalik havola beradi, foydalanuvchi bosadi, bot uni tanib oladi.
//
// NEGA HAVOLA: ilgari botga /start bosgan HAR QANDAY suhbat obunachi bo'lardi —
// begona odam ham, tasodifiy guruh ham. Token esa "bu suhbat platformadagi
// foydalanuvchiga tegishli" degan yagona dalil.

interface FormState {
  enabled: boolean
  email: string
  min_score: number
  base_url: string
  telegram_enabled: boolean
}

const empty: FormState = {
  enabled: false, email: '', min_score: 70,
  base_url: 'http://localhost:5173', telegram_enabled: false,
}

interface Meta {
  smtp_ready: boolean
  smtp_from: string | null
  telegram_token_set: boolean
  telegram_ready: boolean
  subscribers_ready: boolean
  effective_email: string | null
}

// Havola bosilgach ulanishni shu oraliqda so'rab turamiz. Telegram tomonda
// bir necha soniya ketishi mumkin, shuning uchun so'rov qisqa emas.
const POLL_MS = 2500
const POLL_LIMIT = 24        // ~60 soniya

export default function NotifySettings() {
  const [s, setS] = useState<FormState | null>(null)
  const [meta, setMeta] = useState<Meta>({
    smtp_ready: false, smtp_from: null, telegram_token_set: false,
    telegram_ready: true, subscribers_ready: true, effective_email: null,
  })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // Telegram holati sozlamaning bir qismi EMAS (o'z endpointlari bor)
  const [subs, setSubs] = useState<TelegramSubscriber[]>([])
  const [link, setLink] = useState<TelegramLink | null>(null)
  const [linking, setLinking] = useState(false)
  const [tgTesting, setTgTesting] = useState<string | null>(null)
  const [tgMsg, setTgMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => { load() }, [])
  // Komponent yopilganда so'rov tsikli TO'XTAShI shart, aks holda u fon rejimda
  // aylanaverib, server bilan behuda gaplashardi.
  useEffect(() => () => { if (pollRef.current) window.clearInterval(pollRef.current) }, [])

  function apply(r: NotifySettingsData) {
    setS({ ...empty, ...blanks(r) })
    setMeta({
      smtp_ready: !!r?.smtp_ready,
      smtp_from: r?.smtp_from || null,
      telegram_token_set: !!r?.telegram_token_set,
      // Server aniq `false` qaytarsagina "patch kerak" deymiz.
      telegram_ready: r?.telegram_ready !== false,
      subscribers_ready: r?.subscribers_ready !== false,
      effective_email: r?.effective_email || null,
    })
  }

  function load() {
    api.notifySettings().then(apply).catch(() => setS({ ...empty }))
    api.telegramSubscribers().then((r) => setSubs(r.subscribers)).catch(() => {})
  }

  if (!s) return null
  const cur = s
  const set = (k: keyof FormState) => (e: { target: { value: string } }) =>
    setS({ ...cur, [k]: e.target.value })

  async function save() {
    setSaving(true); setMsg(null)
    try {
      apply(await api.saveNotifySettings({
        ...cur,
        email: cur.email || null,
        min_score: Number(cur.min_score),
      }))
      setMsg({ ok: true, text: 'Saqlandi' })
    } catch (e) { setMsg({ ok: false, text: 'Xatolik: ' + (e as Error).message }) }
    finally { setSaving(false) }
  }

  async function sendTest() {
    setTesting(true); setMsg(null)
    try {
      const r = await api.notifyTest()
      setMsg({ ok: true, text: `Sinov xabari yuborildi: ${r?.to || ''}` })
    } catch (e) { setMsg({ ok: false, text: 'Yuborilmadi: ' + (e as Error).message }) }
    finally { setTesting(false) }
  }

  // --- TELEGRAMNI ULASH ----------------------------------------------------
  // Havola YANGI OYNADA ochiladi va shu zahoti holat so'raladi. Foydalanuvchi
  // Telegramда "Start" bosgach ro'yxat o'zi yangilanadi — u qaytib kelib
  // hech narsa bosishi shart emas.
  async function connectTelegram() {
    setLinking(true); setTgMsg(null)
    try {
      const l = await api.telegramCreateLink()
      setLink(l)
      window.open(l.url, '_blank', 'noopener,noreferrer')
      startPolling(l.token)
    } catch (e) {
      setTgMsg({ ok: false, text: (e as Error).message })
      setLinking(false)
    }
  }

  function startPolling(token: string) {
    if (pollRef.current) window.clearInterval(pollRef.current)
    let tries = 0
    pollRef.current = window.setInterval(async () => {
      tries += 1
      try {
        const r = await api.telegramLinkStatus(token)
        setSubs(r.subscribers)
        if (r.connected) {
          stopPolling()
          setLink(null)
          setTgMsg({ ok: true, text: 'Telegram ulandi — bildirishnoma keladi.' })
          return
        }
      } catch { /* tarmoq uzilishi — keyingi urinishда qayta so'raladi */ }
      if (tries >= POLL_LIMIT) {
        stopPolling()
        setTgMsg({
          ok: false,
          text: 'Ulanish tasdiqlanmadi. Havolani qayta oching va Telegramда '
            + '"Start" tugmasini bosing.',
        })
      }
    }, POLL_MS)
  }

  function stopPolling() {
    if (pollRef.current) window.clearInterval(pollRef.current)
    pollRef.current = null
    setLinking(false)
  }

  async function toggleSub(chatId: string, enabled: boolean) {
    setTgMsg(null)
    try { setSubs((await api.telegramSetSubscriber(chatId, enabled)).subscribers) }
    catch (e) { setTgMsg({ ok: false, text: (e as Error).message }) }
  }

  async function removeSub(chatId: string, title: string) {
    if (!window.confirm(`"${title}" uzilsinmi? Qayta ulash uchun havola kerak bo‘ladi.`)) return
    setTgMsg(null)
    try { setSubs((await api.telegramDeleteSubscriber(chatId)).subscribers) }
    catch (e) { setTgMsg({ ok: false, text: (e as Error).message }) }
  }

  async function sendTgTest(chatId?: string) {
    setTgTesting(chatId || 'all'); setTgMsg(null)
    try {
      const r = await api.telegramTest(chatId)
      const n = r?.chats?.length || 0
      setTgMsg({
        ok: !r?.errors?.length,
        text: r?.errors?.length
          ? `${n} ta ulanmaga yuborildi, ${r.errors.length} tasida xato: ${r.errors[0].error}`
          : `Sinov xabari ${n} ta ulanmaga yuborildi`,
      })
    } catch (e) { setTgMsg({ ok: false, text: 'Yuborilmadi: ' + (e as Error).message }) }
    finally { setTgTesting(null) }
  }

  const active = subs.filter((x) => x.enabled)
  const legacy = subs.filter((x) => x.source === 'legacy')

  return (
    <div className="space-y-4">
      {/* --- IKKALA KANALGA UMUMIY --- */}
      <div>
        <SectionHead>Umumiy</SectionHead>
        <div className="space-y-4">
          <div>
            <span className="mb-2 block text-[13px] font-semibold">Moslik chegarasi</span>
            <div className="flex items-center gap-4">
              <Slider className="flex-1" min={0} max={100} step={5}
                value={[s.min_score]}
                onValueChange={([v]) => setS({ ...cur, min_score: v })} />
              <span className="tabular min-w-[70px] rounded-md bg-secondary px-2 py-1 text-center text-sm font-bold text-primary">
                {s.min_score} ball
              </span>
            </div>
            <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
              <span>0 — hammasi</span>
              <span>70 — nom</span>
              <span>100 — kategoriya</span>
            </div>
          </div>

          <Label text="Tizim manzili">
            <Input value={s.base_url} onChange={set('base_url')}
              placeholder="http://localhost:5173"
              title="Xabardagi kartochka havolasi shu manzildan quriladi" />
          </Label>
        </div>
      </div>

      {/* --- KANAL 1: EMAIL --- */}
      <Card className="space-y-3 p-4">
        <ChannelHead icon="mail" title="Email"
          checked={s.enabled} onChange={(v) => setS({ ...cur, enabled: v })} />

        <Label text="Sizning emailingiz"
          note={meta.smtp_from
            ? `Xabar ${meta.smtp_from} manzilidan keladi.`
            : undefined}>
          <Input type="email" value={s.email} onChange={set('email')}
            placeholder={meta.effective_email
              ? `${meta.effective_email} (kompaniya profilidan)`
              : 'siz@kompaniya.uz'} />
        </Label>

        {/* Pochta serveri — OPERATOR sozlamasi. Foydalanuvchi uni tuzata
            olmaydi, shuning uchun faqat holat ko'rsatiladi. */}
        {!meta.smtp_ready && (
          <Secret ok={false}>
            <span><b>Platformaning pochta serveri sozlanmagan.</b> Serverdagi{' '}
              <Code>.env</Code> ga <Code>SMTP_HOST</Code>, <Code>SMTP_FROM</Code>{' '}
              (va kerak bo‘lsa <Code>SMTP_USER</Code> / <Code>SMTP_PASSWORD</Code>)
              qo‘shing.</span>
          </Secret>
        )}

        <div>
          <Button variant="outline" size="sm" onClick={sendTest}
            disabled={testing || !meta.smtp_ready}>
            <Icon name="mail" size={14} />
            {testing ? 'Yuborilmoqda…' : 'Sinov xabari'}
          </Button>
        </div>
      </Card>

      {/* --- KANAL 2: TELEGRAM --- */}
      <Card className="space-y-3 p-4">
        <ChannelHead icon="send" title="Telegram"
          checked={s.telegram_enabled}
          onChange={(v) => setS({ ...cur, telegram_enabled: v })} />

        {(!meta.telegram_ready || !meta.subscribers_ready) && (
          <Secret ok={false}>
            <span><b>Baza patchlari kerak:</b>{' '}
              <Code>schema_patch_notify_telegram.sql</Code>,{' '}
              <Code>schema_patch_notify_subscribers.sql</Code>,{' '}
              <Code>schema_patch_notify_link.sql</Code></span>
          </Secret>
        )}
        {!meta.telegram_token_set && (
          <Secret ok={false}>
            <span><b>Bot tokeni yo‘q.</b> @BotFather dan oling va serverdagi{' '}
              <Code>.env</Code> ga <Code>TELEGRAM_BOT_TOKEN=…</Code> qo‘shing.</span>
          </Secret>
        )}

        {/* --- ULANGAN AKKAUNTLAR --- */}
        {active.length === 0 && legacy.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            Telegram ulanmagan. Tugmani bosing — Telegram ochiladi va{' '}
            <b>Start</b> bosishingiz bilan bildirishnoma kela boshlaydi.
          </p>
        ) : (
          <div className="space-y-1.5">
            {subs.map((c) => (
              <div key={c.chat_id}
                className={cn(
                  'flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors',
                  c.enabled ? 'border-primary/40 bg-secondary' : 'opacity-60',
                )}>
                <Icon name={c.chat_type === 'private' ? 'user' : 'box'} size={15}
                  className="shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold">
                    {c.title || c.chat_id}
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground">
                    {c.username ? `@${c.username}` : c.chat_type}
                    {c.source === 'legacy' && ' · tasdiqlanmagan — qayta ulang'}
                  </span>
                </span>
                <button
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-card hover:text-foreground disabled:opacity-40"
                  title="Shu ulanmaga sinov xabari"
                  disabled={tgTesting !== null || !c.enabled}
                  onClick={() => sendTgTest(c.chat_id)}
                >
                  <Icon name="send" size={14} />
                </button>
                <button
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-card hover:text-urgent"
                  title="Uzish"
                  onClick={() => removeSub(c.chat_id, c.title || c.chat_id)}
                >
                  <Icon name="trash" size={14} />
                </button>
                <Switch checked={c.enabled}
                  onCheckedChange={(v) => toggleSub(c.chat_id, v)}
                  aria-label={`${c.title || c.chat_id} — xabar yuborish`} />
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={connectTelegram}
            disabled={linking || !meta.telegram_token_set}>
            <Icon name="send" size={14} />
            {linking ? 'Kutilmoqda…'
              : active.length ? 'Yana bitta ulash' : 'Telegramni ulash'}
          </Button>
          {active.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => sendTgTest()}
              disabled={tgTesting !== null}>
              {tgTesting === 'all' ? 'Yuborilmoqda…' : 'Sinov xabari'}
            </Button>
          )}
          {linking && (
            <Button variant="ghost" size="sm" onClick={stopPolling}>Bekor qilish</Button>
          )}
        </div>

        {/* Havola ochilmagan bo'lsa (brauzer bloklashi mumkin) — qo'lda ochish */}
        {link && (
          <div className="rounded-lg border border-primary/40 bg-secondary px-3 py-2.5 text-[12px] leading-relaxed">
            Telegram ochilmadimi? Havolani qo‘lда oching:{' '}
            <a className="font-semibold text-primary underline underline-offset-2"
              href={link.url} target="_blank" rel="noopener noreferrer">{link.url}</a>
            <div className="mt-1 text-muted-foreground">
              Havola {link.ttl_minutes} daqiqa amal qiladi va bir marta ishlaydi.
            </div>
          </div>
        )}

        {tgMsg && (
          <div className={cn('text-[13px]', tgMsg.ok ? 'text-ok' : 'text-urgent')}>
            {tgMsg.text}
          </div>
        )}
      </Card>

      <div className="flex items-center gap-3 border-t pt-4">
        <Button onClick={save} disabled={saving}>
          {saving ? 'Saqlanmoqda…' : 'Saqlash'}
        </Button>
        {msg && (
          <span className={cn('text-[13px]', msg.ok ? 'text-ok' : 'text-urgent')}>{msg.text}</span>
        )}
      </div>
    </div>
  )
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[11px] font-bold text-muted-foreground">{children}</div>
  )
}

function ChannelHead({ icon, title, checked, onChange }: {
  icon: string
  title: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center gap-2.5 border-b pb-2.5">
      <Icon name={icon} size={15} className="text-primary" />
      <span className="text-[13px] font-semibold">{title}</span>
      <span className="ml-auto flex items-center gap-2">
        <span className="text-[12px] text-muted-foreground">
          {checked ? 'Yoqilgan' : 'O‘chirilgan'}
        </span>
        <Switch checked={checked} onCheckedChange={onChange} aria-label={`${title} yoqish`} />
      </span>
    </div>
  )
}

function Secret({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className={cn(
      'flex items-start gap-2 rounded-lg border px-3 py-2.5 text-[12px] leading-relaxed',
      ok ? 'border-ok/40 bg-ok-soft text-ok' : 'border-urgent/40 bg-urgent-soft text-urgent',
    )}>
      <Icon name={ok ? 'check' : 'alert'} size={14} className="mt-0.5" />
      {children}
    </div>
  )
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-current/25 bg-card/60 px-1 text-[11px] text-foreground">
      {children}
    </code>
  )
}

// null -> '' (React nazorat qilinadigan inputlar uchun)
function blanks(o: NotifySettingsData): Partial<FormState> {
  return {
    enabled: !!o?.enabled,
    email: o?.email ?? '',
    min_score: o?.min_score ?? 70,
    base_url: o?.base_url ?? 'http://localhost:5173',
    telegram_enabled: !!o?.telegram_enabled,
  }
}
