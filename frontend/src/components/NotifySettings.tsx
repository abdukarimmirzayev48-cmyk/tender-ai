import { useEffect, useRef, useState } from 'react'
import { api } from '@/api'
import Icon from './Icon'
import { Label } from './CatalogView'
import { LANGS, useI18n, useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { ConfirmDialog, useConfirm } from '@/components/ui/confirm-dialog'
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

// BOSHLANG'ICH holat. `base_url` BO'SH — `http://localhost:5173`
// qotirilgan edi va u ikki yo'l bilan ISHLAB CHIQARISHGA o'tardi:
// qurilmaga singib qolardi (o'lchangan: `dist/assets/index-*.js` da
// uch marta) va foydalanuvchi shaklni saqlaganda BAZAGA yozilardi.
// Haqiqiy qiymatni SERVER beradi (`api/ommaviy_url.py` — yagona
// manba); u kelgunicha maydon bo'sh turadi.
const empty: FormState = {
  enabled: false, email: '', min_score: 70,
  base_url: '', telegram_enabled: false,
}

interface Meta {
  smtp_ready: boolean
  smtp_from: string | null
  telegram_token_set: boolean
  telegram_ready: boolean
  subscribers_ready: boolean
  effective_email: string | null
  /** `notify_settings.lang` ustuni bazadami — yo'q bo'lsa til saqlanmaydi */
  lang_ready: boolean
}

// Havola bosilgach ulanishni shu oraliqda so'rab turamiz. Telegram tomonda
// bir necha soniya ketishi mumkin, shuning uchun so'rov qisqa emas.
const POLL_MS = 2500
const POLL_LIMIT = 24        // ~60 soniya

export default function NotifySettings() {
  const { t, lang } = useI18n()
  const [s, setS] = useState<FormState | null>(null)
  const [meta, setMeta] = useState<Meta>({
    smtp_ready: false, smtp_from: null, telegram_token_set: false,
    telegram_ready: true, subscribers_ready: true, effective_email: null,
    lang_ready: true,
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
  // MUHIM: hook quyidagi `if (!s) return null` dan YUQORIDA turishi shart.
  // Pastda bo'lsa birinchi render (s=null) uni o'tkazib yuboradi, ma'lumot
  // kelgach esa chaqiriladi -> "Rendered more hooks than during the previous
  // render" -> ErrorBoundary yo'qligi uchun butun ilova o'chib, panel
  // BO'SH ko'rinardi.
  const confirmUnlink = useConfirm<{ chat_id: string; title: string }>()

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
      lang_ready: r?.lang_ready !== false,
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
      setMsg({ ok: true, text: t('cp.saved') })
    } catch (e) {
      setMsg({ ok: false, text: t('common.errorWith', { msg: (e as Error).message }) })
    }
    finally { setSaving(false) }
  }

  async function sendTest() {
    setTesting(true); setMsg(null)
    try {
      const r = await api.notifyTest()
      setMsg({ ok: true, text: t('ntf.testSent', { to: r?.to || '' }) })
    } catch (e) {
      setMsg({ ok: false, text: t('ntf.testFailed', { msg: (e as Error).message }) })
    }
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
          setTgMsg({ ok: true, text: t('ntf.connected') })
          return
        }
      } catch { /* tarmoq uzilishi — keyingi urinishда qayta so'raladi */ }
      if (tries >= POLL_LIMIT) {
        stopPolling()
        setTgMsg({ ok: false, text: t('ntf.linkTimeout') })
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

  async function removeSub(chatId: string) {
    setTgMsg(null)
    try { setSubs((await api.telegramDeleteSubscriber(chatId)).subscribers) }
    catch (e) { setTgMsg({ ok: false, text: (e as Error).message }) }
  }

  async function sendTgTest(chatId?: string) {
    setTgTesting(chatId || 'all'); setTgMsg(null)
    try {
      const r = await api.telegramTest(chatId)
      const n = r?.chats?.length || 0
      // Xabar platforma tilida ketdi — qaysi tilda ekani tasdiq uchun
      // aytiladi (foydalanuvchi "nega ruscha keldi?" deb o'ylamasin).
      const sentLang = LANGS.find((l) => l.code === r?.lang)?.label || r?.lang || ''
      setTgMsg({
        ok: !r?.errors?.length,
        text: r?.errors?.length
          ? t('ntf.tgTestPartial', { n, e: r.errors.length, err: r.errors[0].error })
          : t('ntf.tgTestSent', { n, lang: sentLang }),
      })
    } catch (e) {
      setTgMsg({ ok: false, text: t('ntf.testFailed', { msg: (e as Error).message }) })
    }
    finally { setTgTesting(null) }
  }

  const active = subs.filter((x) => x.enabled)
  const legacy = subs.filter((x) => x.source === 'legacy')

  return (
    <div className="space-y-4">
      {/* --- IKKALA KANALGA UMUMIY --- */}
      <div>
        <SectionHead>{t('ntf.general')}</SectionHead>
        <div className="space-y-4">
          <div>
            <span className="mb-2 block text-body font-semibold">{t('ntf.threshold')}</span>
            <div className="flex items-center gap-4">
              <Slider className="flex-1" min={0} max={100} step={5}
                value={[s.min_score]}
                onValueChange={([v]) => setS({ ...cur, min_score: v })} />
              <span className="tabular min-w-[70px] rounded-md bg-secondary px-2 py-1 text-center text-body font-semibold text-primary">
                {t('ntf.score', { n: s.min_score })}
              </span>
            </div>
            <div className="mt-1 flex justify-between text-micro text-muted-foreground">
              <span>{t('ntf.scale0')}</span>
              <span>{t('ntf.scale70')}</span>
              <span>{t('ntf.scale100')}</span>
            </div>
          </div>

          <Label text={t('ntf.baseUrl')}>
            {/* `placeholder` YO'Q: u ham qurilmaga tushadigan qotirilgan
                mahalliy manzil edi va foydalanuvchiga "shuni yozing"
                deb ko'rsatardi. Server bergan qiymat maydonda turadi. */}
            <Input value={s.base_url} onChange={set('base_url')}
              title={t('ntf.baseUrlTitle')} />
          </Label>

          {/* XABAR TILI — bu yerда TANLANMAYDI, faqat ko'rsatiladi.
              Til bitta joyда (yon paneldagi sozlamalar menyusi) tanlanadi va
              interfeys ham, xabar ham o'shanga bo'ysunadi. Ikkinchi tanlagich
              qo'ysak, ikkovi bir-biridan uzoqlashib, "interfeys ruscha, xat
              o'zbekcha" holati kelib chiqardi. */}
          <div>
            <span className="mb-1 block text-body font-semibold">
              {t('ntf.language')}
            </span>
            <p className="text-caption leading-relaxed text-muted-foreground">
              {t('ntf.langNote', {
                lang: LANGS.find((l) => l.code === lang)?.label || lang,
              })}
            </p>
          </div>

          {!meta.lang_ready && (
            <Secret ok={false}>
              <span><b>{t('ntf.langPatch')}</b>{' '}
                <Code>schema_patch_notify_lang.sql</Code></span>
            </Secret>
          )}
        </div>
      </div>

      {/* --- KANAL 1: EMAIL --- */}
      <Card className="space-y-3 p-4">
        <ChannelHead icon="mail" title={t('ntf.email')}
          checked={s.enabled} onChange={(v) => setS({ ...cur, enabled: v })} />

        <Label text={t('ntf.yourEmail')}
          note={meta.smtp_from ? t('ntf.fromNote', { from: meta.smtp_from }) : undefined}>
          <Input type="email" value={s.email} onChange={set('email')}
            placeholder={meta.effective_email
              ? t('ntf.emailPhProfile', { email: meta.effective_email })
              : t('ntf.emailPh')} />
        </Label>

        {/* Pochta serveri — OPERATOR sozlamasi. Foydalanuvchi uni tuzata
            olmaydi, shuning uchun faqat holat ko'rsatiladi. */}
        {!meta.smtp_ready && (
          <Secret ok={false}>
            <span><b>{t('ntf.smtpMissingTitle')}</b> {t('ntf.smtpMissingBody')}</span>
          </Secret>
        )}

        <div>
          <Button variant="outline" size="sm" onClick={sendTest}
            disabled={testing || !meta.smtp_ready}>
            <Icon name="mail" size={14} />
            {testing ? t('ntf.sending') : t('ntf.testMsg')}
          </Button>
        </div>
      </Card>

      {/* --- KANAL 2: TELEGRAM --- */}
      <Card className="space-y-3 p-4">
        <ChannelHead icon="send" title={t('ntf.telegram')}
          checked={s.telegram_enabled}
          onChange={(v) => setS({ ...cur, telegram_enabled: v })} />

        {(!meta.telegram_ready || !meta.subscribers_ready) && (
          <Secret ok={false}>
            <span><b>{t('ntf.patchNeeded')}</b>{' '}
              <Code>schema_patch_notify_telegram.sql</Code>,{' '}
              <Code>schema_patch_notify_subscribers.sql</Code>,{' '}
              <Code>schema_patch_notify_link.sql</Code></span>
          </Secret>
        )}
        {!meta.telegram_token_set && (
          <Secret ok={false}>
            <span><b>{t('ntf.tokenMissingTitle')}</b> {t('ntf.tokenMissingBody')}</span>
          </Secret>
        )}

        {/* --- ULANGAN AKKAUNTLAR --- */}
        {active.length === 0 && legacy.length === 0 ? (
          <p className="text-body text-muted-foreground">{t('ntf.tgNotConnected')}</p>
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
                  <span className="block truncate text-body font-semibold">
                    {c.title || c.chat_id}
                  </span>
                  <span className="block truncate text-micro text-muted-foreground">
                    {c.username ? `@${c.username}` : c.chat_type}
                    {c.source === 'legacy' && ` ${t('ntf.unverified')}`}
                  </span>
                </span>
                <button
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-card hover:text-foreground disabled:opacity-40"
                  aria-label={t('ntf.testThis')} title={t('ntf.testThis')}
                  disabled={tgTesting !== null || !c.enabled}
                  onClick={() => sendTgTest(c.chat_id)}
                >
                  <Icon name="send" size={14} />
                </button>
                <button
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-card hover:text-urgent-strong"
                  title={t('ntf.disconnect')}
                  aria-label={t('ntf.disconnectAria', { name: c.title || c.chat_id })}
                  onClick={() => confirmUnlink.ask({ chat_id: c.chat_id, title: c.title || c.chat_id })}
                >
                  <Icon name="trash" size={14} />
                </button>
                <Switch checked={c.enabled}
                  onCheckedChange={(v) => toggleSub(c.chat_id, v)}
                  aria-label={t('ntf.subAria', { name: c.title || c.chat_id })} />
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={connectTelegram}
            disabled={linking || !meta.telegram_token_set}>
            <Icon name="send" size={14} />
            {linking ? t('ntf.waiting')
              : t(active.length ? 'ntf.connectMore' : 'ntf.connect')}
          </Button>
          {active.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => sendTgTest()}
              disabled={tgTesting !== null}>
              {tgTesting === 'all' ? t('ntf.sending') : t('ntf.testMsg')}
            </Button>
          )}
          {linking && (
            <Button variant="ghost" size="sm" onClick={stopPolling}>{t('common.cancel')}</Button>
          )}
        </div>

        {/* Havola ochilmagan bo'lsa (brauzer bloklashi mumkin) — qo'lda ochish */}
        {link && (
          <div className="rounded-lg border border-primary/40 bg-secondary px-3 py-2.5 text-caption leading-relaxed">
            {t('ntf.linkFallback')}{' '}
            <a className="font-semibold text-primary underline underline-offset-2"
              href={link.url} target="_blank" rel="noopener noreferrer">{link.url}</a>
            <div className="mt-1 text-muted-foreground">
              {t('ntf.linkTtl', { n: link.ttl_minutes })}
            </div>
          </div>
        )}

        {tgMsg && (
          <div className={cn('text-body', tgMsg.ok ? 'text-ok-strong' : 'text-urgent-strong')}>
            {tgMsg.text}
          </div>
        )}
      </Card>

      <div className="flex items-center gap-3 border-t pt-4">
        <Button onClick={save} disabled={saving}>
          {saving ? t('common.saving') : t('common.save')}
        </Button>
        {msg && (
          <span className={cn('text-body', msg.ok ? 'text-ok-strong' : 'text-urgent-strong')}>{msg.text}</span>
        )}
      </div>

      <ConfirmDialog
        {...confirmUnlink.props}
        title={t('ntf.confirmDisconnect', { name: confirmUnlink.target?.title ?? '' })}
        confirmLabel={t('ntf.disconnect')}
        onConfirm={() => confirmUnlink.target && removeSub(confirmUnlink.target.chat_id)}
      />
    </div>
  )
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-micro font-semibold text-muted-foreground">{children}</div>
  )
}

function ChannelHead({ icon, title, checked, onChange }: {
  icon: string
  title: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  const t = useT()
  return (
    <div className="flex items-center gap-2.5 border-b pb-2.5">
      <Icon name={icon} size={15} className="text-primary" />
      <span className="text-body font-semibold">{title}</span>
      <span className="ml-auto flex items-center gap-2">
        <span className="text-caption text-muted-foreground">
          {t(checked ? 'ntf.on' : 'ntf.off')}
        </span>
        <Switch checked={checked} onCheckedChange={onChange}
          aria-label={t('ntf.toggleAria', { title })} />
      </span>
    </div>
  )
}

function Secret({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className={cn(
      'flex items-start gap-2 rounded-lg border px-3 py-2.5 text-caption leading-relaxed',
      ok ? 'border-ok/40 bg-ok-soft text-ok-strong' : 'border-urgent/40 bg-urgent-soft text-urgent-strong',
    )}>
      <Icon name={ok ? 'check' : 'alert'} size={14} className="mt-0.5" />
      {children}
    </div>
  )
}

// Bot buyrug'i / token kabi "aynan shunday yoziladigan" qiymat.
// `<code>` elementi — semantikasi uchun; ko'rinishi esa ilovaning o'z
// shriftida qoladi (brauzerning standart monoshirin shrifti bekor
// qilinadi). Qiymat ekanini ramka va fon bildiradi, shrift emas.
function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-current/25 bg-card/60 px-1 font-sans text-micro text-foreground">
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
    base_url: o?.base_url ?? '',
    telegram_enabled: !!o?.telegram_enabled,
  }
}
