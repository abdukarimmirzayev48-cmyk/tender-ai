import Icon from './Icon'
import { useT } from '@/i18n'
import type { Citation } from '@/hooks/useChatStream'

// TOPILGAN BO'LAK — qidiruv qaytargan hujjat parchasi.
//
// DIQQAT: bu IQTIBOS EMAS. Model javobida qaysi bo'lakka
// tayanganini AYTMAYDI, biz esa taxmin qilmaymiz — ro'yxat
// shunchaki `search_documents` qaytargan 8 ta parcha.
// Jonli evalda (2026-08-25) model to'g'ri raqam aytib, BOSHQA
// bandga tayangan holat qayd etildi. Shuning uchun sarlavha
// "Topilgan hujjat bo'laklari" — "Manba" emas.
//
// NEGA `<a href>` EMAS: `markdown.ts` model chiqishidagi HAMMA havolani
// o'chiradi, chunki ular tender hujjatidan (tashqi manbadan) kelgan
// bo'lishi mumkin. Iqtibos esa BIZNING ma'lumotimiz — `tender_id`,
// `file_ref` va `char_start` serverdan, `doc_chunk` jadvalidan keladi.
// Shuning uchun u tugma: bosilganda ilova ichida hujjat matnini ochadi,
// tashqariga hech qayerga olib chiqmaydi.

interface CitationChipProps {
  citation: Citation
  index: number
  /** Hujjat matnini ochish — `DocumentText` paneliga o'tadi. */
  onOpen?: (c: Citation) => void
}

export default function CitationChip({ citation, index, onOpen }: CitationChipProps) {
  const t = useT()
  // Fayl nomi ma'nosiz raqam bo'lishi mumkin (`202604090556245824.pdf`) —
  // bunda kesib ko'rsatamiz, chunki to'liq nom foyda bermaydi.
  const nom = citation.file_name || citation.file_ref || t('chat.citation.file')
  const qisqa = nom.length > 26 ? `${nom.slice(0, 24)}…` : nom

  return (
    <button
      type="button"
      onClick={() => onOpen?.(citation)}
      disabled={!onOpen}
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border
                 border-border bg-card px-2 py-1 text-left text-xs
                 text-muted-foreground transition hover:border-accent/50
                 hover:text-foreground disabled:cursor-default
                 disabled:hover:border-border disabled:hover:text-muted-foreground"
      title={citation.snippet || qisqa}
    >
      <span className="shrink-0 font-medium text-accent">[{index + 1}]</span>
      <Icon name="clip" size={12} className="shrink-0" />
      <span className="truncate">{qisqa}</span>
      {/* Belgi o'rni — foydalanuvchi hujjatning QAYSI joyi ekanini ko'radi */}
      <span className="shrink-0 tabular-nums opacity-60">
        {t('chat.citation.at', { pos: citation.char_start })}
      </span>
    </button>
  )
}
