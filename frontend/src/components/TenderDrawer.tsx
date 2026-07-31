import { useEffect, useState } from 'react'
import { api, apiUrl } from '@/api'
import { money, dateFmt, deadline, sourceUrl, fileSize, ago, DEADLINE_CLASS } from '@/format'
import Icon from './Icon'
import AiMatch from './AiMatch'
import GoNoGo from './GoNoGo'
import CompliancePanel from './CompliancePanel'
import PricingPanel from './PricingPanel'
import StockCheck from './StockCheck'
import DocumentText from './DocumentText'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import type { TenderDetail, MatchInfo } from '@/types'

interface TenderDrawerProps {
  id: number
  match?: MatchInfo
  onClose: () => void
  onOpenDocuments?: (docType: string) => void
}

// O'ng tomondagi tafsilot paneli: lotlar + tovarlar. match berilsa ball/sabab ham.
//
// Vengeance UI `Sheet` (Radix Dialog) ishlatiladi — fokus tuzog'i, Escape va
// scroll-lock tekinga keladi. Ilgari bularning har biri qo'lda yozilgan edi
// (`useEffect` + keydown listener), fokus esa hech qachon panel ichida
// ushlanmasdi — klaviatura bilan yurgan foydalanuvchi orqadagi jadvalga
// tushib ketardi.
export default function TenderDrawer({ id, match, onClose, onOpenDocuments }: TenderDrawerProps) {
  const [t, setT] = useState<TenderDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setT(null); setError(null)
    api.tender(id).then(setT).catch((e: Error) => setError(e.message))
  }, [id])

  const d = t ? deadline(t.close_at) : null

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose() }}>
      <SheetContent side="right" className="w-[640px] max-w-[92vw] overflow-y-auto p-0 sm:max-w-[92vw]">
        <SheetHeader className="sticky top-0 z-10 border-b bg-card px-5 py-3">
          <SheetTitle className="tabular text-[13px] font-normal text-muted-foreground">
            #{id}
          </SheetTitle>
        </SheetHeader>

        <div className="px-6 pb-10 pt-4">
          {error && (
            <div className="rounded-lg border border-urgent/40 bg-urgent-soft px-4 py-3 text-[13px] text-urgent">
              Xatolik: {error}
            </div>
          )}
          {!t && !error && (
            <div className="space-y-3">
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          )}

          {t && (
            <>
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{t.status_name || t.status}</Badge>
                {t.status === 'open' && d && (
                  <span className={cn('rounded px-2 py-0.5 text-[12px] font-semibold', DEADLINE_CLASS[d.level])}>
                    {d.text}
                  </span>
                )}
              </div>
              <h2 className="mb-3 mt-2.5 text-xl font-bold leading-snug">
                {t.name || `Tender #${t.id}`}
              </h2>

              {/* Rasmiy sahifaga havola — hujjatlar (texnik topshiriq, xarid
                  hujjatlari) faqat o'sha yerda mavjud, ommaviy API bermaydi. */}
              {sourceUrl(t) && (
                <a
                  className="mb-4 inline-flex items-center gap-1.5 rounded-md border border-primary px-3.5 py-2 text-[13px] font-semibold text-primary transition-colors hover:bg-secondary"
                  href={sourceUrl(t)!} target="_blank" rel="noopener noreferrer"
                  title="Hujjatlar, talablar va aloqa ma'lumotlari manbada"
                >
                  Manbada ochish
                  <Icon name="external" size={13} />
                </a>
              )}

              {/* AI TAHLILI — ruscha/texnik matnni o'zbekcha tushunarli qiladi.
                  Tahlil qilinmagan bo'lsa (kesh bo'sh) — umuman ko'rsatilmaydi. */}
              {t.ai && (
                <div className="mb-4 rounded-lg border bg-muted p-3.5">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <Icon name="sparkle" size={13} className="text-primary" />
                    <span className="text-[13px] font-semibold">AI xulosa</span>
                    {t.ai.category_tags?.map((c) => (
                      <span key={c} className="rounded bg-secondary px-1.5 py-px text-[11px] text-primary">
                        {c}
                      </span>
                    ))}
                  </div>
                  <p className="text-[13px] leading-relaxed">{t.ai.summary_uz}</p>
                  {t.ai.supplier_profile && (
                    <div className="mt-1.5 text-[13px]">
                      <b>Kimga mos:</b> {t.ai.supplier_profile}
                    </div>
                  )}
                  {!!t.ai.key_points?.length && (
                    <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[13px]">
                      {t.ai.key_points.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  )}
                </div>
              )}

              {/* AI MOSLIK — talab bo'yicha. Yuqoridagi "AI xulosa" tenderni
                  mustaqil tavsiflaydi; bu esa SIZNING katalogingizga nisbatan
                  hukm chiqaradi (mos / qisman / mos emas). */}
              <AiMatch tenderId={t.id} />

              {/* Go/No-Go — qatnashish qarori: muddat, byudjet, sertifikat,
                  tajriba va resursni ham hisobga oladi. */}
              <GoNoGo tenderId={t.id} />

              {/* P0-6 — SO'RALGAN MIQDOR OMBORDA BORMI */}
              <StockCheck tenderId={t.id} />

              {/* P0-7 — "qancha narx qo'yamiz?" (hisob brauzerda) */}
              <PricingPanel tender={t} />

              {/* P0-8 — "ariza to'plamim tayyormi?" */}
              <CompliancePanel tenderId={t.id} onOpenDocuments={onOpenDocuments} />

              {/* P0-2 — ilova hujjatlarining MATN holati */}
              <DocumentText tenderId={t.id} />

              {/* Moslik bloki. MAYDONLAR IXTIYORIY deb qaraladi: `match` ikki
                  manbadan keladi (katalog mosligi va saqlangan qidiruv), ular
                  har xil maydon to'plami beradi. */}
              {match && (
                <div className="mb-4 rounded-lg bg-secondary px-3.5 py-3">
                  <div className="tabular mb-1.5 text-sm">
                    Moslik <b>{match.score ?? 0}</b>/100
                  </div>
                  {!!match.matched_keywords?.length && (
                    <div className="mb-1.5 flex flex-wrap gap-1.5">
                      {match.matched_keywords.map((k) => (
                        <span key={k} className="rounded bg-card px-1.5 py-px text-[11px] text-primary">
                          {k}
                        </span>
                      ))}
                    </div>
                  )}
                  {!!match.reasons?.length && (
                    <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-primary">
                      {match.reasons.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  )}
                </div>
              )}

              <div className="mb-5 grid grid-cols-2 gap-x-6 gap-y-3">
                <Info label="Buyurtmachi" value={t.company?.name} />
                <Info label="Hudud" value={t.region?.name} />
                <Info label="Umumiy summa" value={money(t.totalcost, t.currency)} />
                <Info label="Valyuta" value={t.currency} />
                <Info label="E'lon qilingan" value={dateFmt(t.publicated_at)} />
                <Info label="Deadline" value={dateFmt(t.close_at)} />
                <Info label="Manba" value={t.source_platform} />
                {t.first_seen_at && <Info label="Bizda topildi" value={ago(t.first_seen_at)} />}
                <Info label="Lot / tovar" value={`${t.lot_count || 0} / ${t.good_count || 0}`} />
                {t.detail?.method_marks && <Info label="Baholash usuli" value={t.detail.method_marks} />}
                {t.detail?.close_time && <Info label="Qabul tugaydi" value={t.detail.close_time} />}
                {t.detail?.company_details && (
                  <Info label="Bank rekvizitlari" value={t.detail.company_details} />
                )}
              </div>

              {/* HUJJATLAR — mahsulotning eng qimmatli qismi: kompaniya texnik
                  topshiriqni o'qimasdan ariza bera olmaydi. */}
              {!!t.document_sections?.length && (
                <>
                  <SectionTitle>Hujjatlar ({t.doc_count})</SectionTitle>
                  {t.document_sections.map((s) => (
                    <div className="mb-3" key={s.section}>
                      <div className="mb-1 text-[12px] font-semibold text-muted-foreground">
                        {s.section}
                      </div>
                      {s.files.map((f) => (
                        <a
                          className="mb-1 flex items-center gap-2.5 rounded-md border px-2.5 py-2 text-[13px] transition-colors hover:bg-accent"
                          key={f.file_ref || f.file_id} href={apiUrl(f.download_url)}
                          target="_blank" rel="noopener noreferrer"
                        >
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                            {(f.file_type || '?').toLowerCase()}
                          </span>
                          <span className="flex-1 truncate">{f.name || f.file_id}</span>
                          <span className="tabular text-[12px] text-muted-foreground">
                            {fileSize(f.size_bytes)}
                          </span>
                          <Icon name="download" size={14} className="text-muted-foreground" />
                        </a>
                      ))}
                    </div>
                  ))}
                </>
              )}

              <SectionTitle>Lotlar va tovarlar</SectionTitle>
              {(t.lots || []).length === 0 && (
                <div className="text-[13px] text-muted-foreground">Lot ma'lumoti yo‘q.</div>
              )}

              {(t.lots || []).map((lot) => (
                <div className="mb-4" key={lot.lot_id}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3">
                    <strong className="text-[13px]">
                      Lot {lot.lot_id}{lot.title ? ` — ${lot.title}` : ''}
                    </strong>
                    <span className="tabular shrink-0 text-[12px] text-muted-foreground">
                      {lot.goods?.length ?? 0} tovar · {money(lot.total_sum_lot, t.currency)}
                    </span>
                  </div>

                  {/* Yetkazib berish shartlari — "bajara olamanmi?" savoliga javob */}
                  {!!lot.items?.length && (
                    <div className="mb-2 space-y-1.5 rounded-md bg-muted p-2.5">
                      {lot.items.map((it) => (
                        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12.5px]" key={it.item_id}>
                          <span className="font-medium">{it.name || it.product_code}</span>
                          {it.delivery_period != null && (
                            <span className="text-muted-foreground">
                              Yetkazish: <b className="text-foreground">{it.delivery_period} kun</b>
                            </span>
                          )}
                          {it.guarantee != null && (
                            <span className="text-muted-foreground">
                              Kafolat: <b className="text-foreground">{it.guarantee} kun</b>
                            </span>
                          )}
                          {it.prod_year && (
                            <span className="text-muted-foreground">
                              Yili: <b className="text-foreground">{it.prod_year}</b>
                            </span>
                          )}
                          {it.spec && <span className="text-muted-foreground">{it.spec}</span>}
                          {!!it.properties?.length && (
                            <div className="flex w-full flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-muted-foreground">
                              {it.properties.slice(0, 6).map((p, i) => (
                                <span key={i}>
                                  {p.prop_name}: <b className="text-foreground">{String(p.val_name)}</b>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {!!lot.goods?.length && (
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="border-b text-[11px] text-muted-foreground">
                          <th className="p-1.5 text-left font-semibold">Nomi</th>
                          <th className="p-1.5 text-left font-semibold">Birlik</th>
                          <th className="p-1.5 text-right font-semibold">Miqdor</th>
                          <th className="p-1.5 text-right font-semibold">Narx</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lot.goods.map((g, i) => (
                          <tr key={g.good_code + i} className="border-b border-border-soft">
                            <td className="p-1.5">{g.name || g.good_code}</td>
                            <td className="p-1.5">{g.unit || '—'}</td>
                            <td className="tabular whitespace-nowrap p-1.5 text-right">{g.amount ?? '—'}</td>
                            <td className="tabular whitespace-nowrap p-1.5 text-right">{money(g.price)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2.5 mt-[18px] border-t pt-3.5 text-[15px] font-semibold">{children}</h3>
  )
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value || '—'}</div>
    </div>
  )
}
