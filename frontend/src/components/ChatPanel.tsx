import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from './Icon'
import ToolBadge from './ToolBadge'
import CitationChip from './CitationChip'
import { Button } from '@/components/ui/button'
import { useI18n, useT } from '@/i18n'
import { useChatStream } from '@/hooks/useChatStream'
import type { Citation } from '@/hooks/useChatStream'
import { renderMarkdown } from '@/markdown'
import { cn } from '@/lib/utils'
import { AIAssistantInterface } from '@/components/ui/ai-assistant-interface'
import { api, type ChatSession, type ChatStoredMessage } from '@/api'

// AI-CHAT PANELI
// ══════════════
// LAZY CHUNK: bu fayl `marked` + `DOMPurify` ni tortadi (~13 KB gzip).
// `App.tsx` uni `lazy()` bilan yuklaydi — chat ochilmaguncha bu kod
// umuman yuklab olinmaydi (`StatsView`/`TenderDrawer` bilan bir xil naqsh).
//
// QAMROV: panel `tenderId` bilan ochilsa — suhbat SHU TENDER kontekstida
// (server `ChatContext.tender_id` ni promptga qo'yadi va "bu tender"
// iborasi shunga bog'lanadi). Kontekstsiz ochilsa — umumiy suhbat.

interface Msg {
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
}

interface ChatPanelProps {
  /** Tender konteksti. `null` — umumiy suhbat. */
  tenderId?: number | null
  onClose: () => void
  /** Iqtibos bosilganda hujjat matnini ochish. */
  onOpenCitation?: (c: Citation) => void
}

export default function ChatPanel({ tenderId, onClose, onOpenCitation }: ChatPanelProps) {
  const t = useT()
  const { lang } = useI18n()
  const { state, send, stop, reset } = useChatStream()
  const [savol, setSavol] = useState('')
  const [tarix, setTarix] = useState<Msg[]>([])
  const oxiriRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // --- SUHBATLAR TARIXI ---------------------------------------------
  // Backend `GET /chat/sessions` ni ANCHADAN BERI beradi, lekin
  // frontend uni HECH QACHON chaqirmagan: suhbat sahifa yangilanishi
  // bilan yo'qolardi va foydalanuvchi savolini qaytadan yozardi.
  const [tarixOchiq, setTarixOchiq] = useState(false)
  const [seanslar, setSeanslar] = useState<ChatSession[] | null>(null)
  const [seansXato, setSeansXato] = useState<string | null>(null)

  const seanslarniYukla = useCallback(async () => {
    setSeansXato(null)
    try {
      setSeanslar(await api.chatSessions())
    } catch (e) {
      // XATO YUTILMAYDI: bo'sh ro'yxat va yiqilgan so'rov BOSHQA
      // holatlar va foydalanuvchi farqni ko'rishi kerak.
      setSeanslar([])
      setSeansXato((e as Error).message)
    }
  }, [])

  /** Saqlangan xabar bloklaridan matnni ajratadi. */
  function blokMatni(m: ChatStoredMessage): string {
    const c = m.content
    if (typeof c === 'string') return c
    if (!Array.isArray(c)) return ''
    return c
      .filter((b): b is { type?: string; text?: string } =>
        !!b && typeof b === 'object')
      .filter((b) => typeof b.text === 'string')
      .map((b) => b.text as string)
      .join(String.fromCharCode(10))
  }

  async function seansOch(id: string) {
    setSeansXato(null)
    try {
      const r = await api.chatHistory(id)
      const msgs: Msg[] = r.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({
          role: m.role as 'user' | 'assistant',
          // XATOLI javob ham KO'RSATILADI — backend uni ataylab
          // saqlaydi, interfeys uni yashirsa sabab yo'qolardi.
          text: m.error ? `⚠ ${m.error}` : blokMatni(m),
        }))
        .filter((m) => m.text)
      reset()
      setTarix(msgs)
      setTarixOchiq(false)
    } catch (e) {
      setSeansXato((e as Error).message)
    }
  }

  async function seansArxivla(id: string) {
    try {
      await api.chatArchive(id)
      setSeanslar((xs) => (xs || []).filter((x) => x.id !== id))
    } catch (e) {
      setSeansXato((e as Error).message)
    }
  }

  // Oqim tugagach javobni tarixga ko'chiramiz — shunda keyingi savol
  // ekranni tozalamaydi va suhbat ko'rinib turadi.
  useEffect(() => {
    if (state.streaming || !state.text) return
    setTarix((h) => {
      if (h.length && h[h.length - 1].role === 'assistant') return h
      return [...h, { role: 'assistant', text: state.text, citations: state.citations }]
    })
  }, [state.streaming, state.text, state.citations])

  // Yangi matn kelganda pastga suramiz.
  useEffect(() => {
    oxiriRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state.text, tarix.length, state.tools.length])

  useEffect(() => () => stop(), [stop])   // panel yopilsa oqimni to'xtatamiz

  // MANBA RAQAMI bosilganda hujjatni ochamiz.
  //
  // Nega delegatsiya: `[3]` elementlari `dangerouslySetInnerHTML` ichida
  // yaratiladi — React ularga `onClick` bera olmaydi. Konteynerdagi
  // bitta ishlovchi hammasini qamrab oladi.
  //
  // Raqam -> massiv indeksi: server `manba_raqami` ni `ctx.citations`
  // dagi o'rni (1 dan) qilib beradi, frontend ham AYNAN shu tartibda
  // saqlaydi. Ya'ni [3] === citations[2].
  function manbaOch(e: React.MouseEvent | React.KeyboardEvent,
                    citations?: Citation[]) {
    const el = (e.target as HTMLElement | null)?.closest?.('[data-manba]')
    if (!el || !citations?.length || !onOpenCitation) return
    if ('key' in e && e.key !== 'Enter' && e.key !== ' ') return
    const n = Number(el.getAttribute('data-manba'))
    const c = Number.isFinite(n) ? citations[n - 1] : undefined
    if (!c) return          // model mavjud bo'lmagan raqam yozgan bo'lsa
    e.preventDefault()
    onOpenCitation(c)
  }

  function yubor() {
    const q = savol.trim()
    if (!q || state.streaming) return
    setTarix((h) => [...h, { role: 'user', text: q }])
    setSavol('')
    void send(q, { sessionId: state.sessionId, tenderId, lang })
    inputRef.current?.focus()
  }

  // Markdown FAQAT tugagan javoblar uchun: oqim davomida har token'da
  // qayta parse qilish sezilarli yuk beradi (o'rta serverda ham,
  // brauzerda ham) va yarim markdown baribir noto'g'ri ko'rinadi.
  const oqimHtml = useMemo(
    () => (state.streaming ? null : renderMarkdown(state.text)),
    [state.streaming, state.text],
  )

  const bosh = !tarix.length && !state.text && !state.error

  return (
    <div className="flex h-full flex-col bg-card">
      {/* --- Sarlavha va QAMROV chipi --------------------------------- */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Icon name="sparkle" size={16} className="text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-body font-medium">{t('chat.title')}</div>
          {/* Foydalanuvchi chat NIMAGA qarayotganini ko'rishi kerak */}
          <div className="truncate text-xs text-muted-foreground">
            {tenderId
              ? t('chat.scope.tender', { id: tenderId })
              : t('chat.scope.global')}
          </div>
        </div>
        <Button variant="ghost" size="sm"
          aria-pressed={tarixOchiq}
          onClick={() => {
            const yangi = !tarixOchiq
            setTarixOchiq(yangi)
            if (yangi && seanslar === null) void seanslarniYukla()
          }}
          title={t('chat.history')}>
          <Icon name="checklist" size={14} />
        </Button>
        {tarix.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => { reset(); setTarix([]) }}
            title={t('chat.new')}>
            <Icon name="plus" size={14} />
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onClose} title={t('common.close')}>
          <Icon name="close" size={14} />
        </Button>
      </div>

      {/* --- Suhbat ---------------------------------------------------- */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {tarixOchiq && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">
              {t('chat.history')}
            </div>
            {seansXato && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-caption
                            text-destructive">
                {t('chat.history.failed', { msg: seansXato })}
              </p>
            )}
            {seanslar !== null && !seanslar.length && !seansXato && (
              <p className="text-caption text-muted-foreground">
                {t('chat.history.empty')}
              </p>
            )}
            <ul className="divide-y divide-border overflow-hidden rounded-lg border">
              {(seanslar || []).map((sn) => (
                <li key={sn.id} className="flex items-center gap-1">
                  <button type="button"
                    onClick={() => void seansOch(sn.id)}
                    title={t('chat.history.open')}
                    className="min-w-0 flex-1 px-3 py-2 text-left transition-colors
                               hover:bg-accent/10">
                    <div className="truncate text-caption">
                      {sn.title || t('chat.scope.global')}
                    </div>
                    <div className="text-micro text-muted-foreground">
                      {new Date(sn.updated_at).toLocaleString()}
                      {sn.tender_id ? ` · #${sn.tender_id}` : ''}
                    </div>
                  </button>
                  <Button variant="ghost" size="sm"
                    title={t('chat.history.archive')}
                    onClick={() => void seansArxivla(sn.id)}>
                    <Icon name="trash" size={13} />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {bosh && !tarixOchiq && (
          <AIAssistantInterface tenderId={tenderId} onPick={(m) => {
            setSavol(m)
            inputRef.current?.focus()
          }} />
        )}

        {tarix.map((m, i) => (
          <div key={i} className={cn('text-body', m.role === 'user' && 'flex justify-end')}>
            {m.role === 'user' ? (
              <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2">{m.text}</div>
            ) : (
              <>
                <div className="chat-markdown"
                  onClick={(e) => manbaOch(e, m.citations)}
                  onKeyDown={(e) => manbaOch(e, m.citations)}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(m.text) }} />
                {!!m.citations?.length && (
                  /* ATAYLAB "iqtibos" EMAS, "topilgan bo'laklar".
                     Bular RETRIEVAL natijasi — model qaysi biriga
                     tayanganini bildirmaydi. Jonli evalda o'lchandi:
                     A5 holatida model to'g'ri raqam aytdi, lekin
                     BOSHQA bandga tayangan edi va bo'laklar ro'yxati
                     buni ko'rsatmasdi. "Manba" deb nomlash
                     foydalanuvchini chalg'itadi. */
                  <div className="mt-2">
                    <div className="mb-1 text-xs font-medium text-muted-foreground">
                      {t('chat.sources.title')}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {m.citations.map((c, j) => (
                        <CitationChip key={j} citation={c} index={j} onOpen={onOpenCitation} />
                      ))}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground/80">
                      {t('chat.sources.hint')}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        ))}

        {/* --- Ishlayotgan tool'lar --------------------------------- */}
        {!!state.tools.length && (
          <div className="flex flex-wrap gap-1.5">
            {state.tools.map((tl, i) => <ToolBadge key={i} tool={tl} />)}
          </div>
        )}

        {/* --- Oqib kelayotgan javob -------------------------------- */}
        {state.text && !tarix.some((m) => m.role === 'assistant' && m.text === state.text) && (
          <div className="text-body">
            {state.streaming
              // Oqim davomida XOM MATN: markdown hali to'liq emas.
              ? <div className="whitespace-pre-wrap">{state.text}</div>
              : <div className="chat-markdown"
                  onClick={(e) => manbaOch(e, state.citations)}
                  onKeyDown={(e) => manbaOch(e, state.citations)}
                  dangerouslySetInnerHTML={{ __html: oqimHtml ?? '' }} />}
          </div>
        )}

        {state.streaming && !state.text && !state.tools.length && (
          <div className="flex items-center gap-2 text-body text-muted-foreground"
            role="status" aria-live="polite">
            <Icon name="sparkle" size={14} />
            {t('chat.thinking')}
          </div>
        )}

        {state.error && (
          <div className="rounded-lg border border-urgent/40 bg-urgent-soft px-3 py-2
                          text-body text-urgent">
            {state.error}
          </div>
        )}

        {/* Xarajat — chat HAR SAVOLDA pul sarflaydi, buni yashirmaymiz */}
        {state.done && (
          <div className="text-xs text-muted-foreground">
            {t('chat.cost', {
              tokens: state.done.input_tokens + state.done.output_tokens,
              usd: state.done.cost_usd.toFixed(4),
              sec: (state.done.latency_ms / 1000).toFixed(1),
            })}
          </div>
        )}
        <div ref={oxiriRef} />
      </div>

      {/* --- Savol maydoni --------------------------------------------- */}
      <div className="border-t p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={savol}
            onChange={(e) => setSavol(e.target.value)}
            onKeyDown={(e) => {
              // Enter = yuborish, Shift+Enter = yangi qator.
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); yubor() }
            }}
            rows={2}
            placeholder={t('chat.placeholder')}
            disabled={state.streaming}
            className="min-h-[2.5rem] flex-1 resize-none rounded-md border bg-background
                       px-3 py-2 text-body outline-none focus:border-accent
                       disabled:opacity-60"
          />
          {state.streaming ? (
            <Button variant="outline" onClick={stop} title={t('chat.stop')}>
              <Icon name="close" size={14} />
            </Button>
          ) : (
            <Button onClick={yubor} disabled={!savol.trim()} title={t('chat.send')}>
              <Icon name="send" size={14} />
            </Button>
          )}
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">{t('chat.disclaimer')}</p>
      </div>
    </div>
  )
}
