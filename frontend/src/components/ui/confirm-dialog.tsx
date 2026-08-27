import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'

import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// TASDIQLASH OYNASI — `window.confirm()` o'rniga.
//
// NEGA: brauzerning o'z oynasi ilovaning shriftini, rangini va tilini
// bilmaydi; sarlavhasi o'rniga sayt manzilini ko'rsatadi; mobil brauzerlarda
// "bu saytga boshqa ruxsat bermaslik" katagi bilan keladi — foydalanuvchi
// uni bir marta belgilasa, o'chirish tasdiqsiz ketaveradi. Bundan tashqari
// u xavfli amalni oddiy amaldan ajratmaydi: "O'chirish" va "Bekor qilish"
// bir xil ko'rinadi.
//
// Radix `Dialog` fokusni ushlaydi, Escape'ni qayta ishlaydi va ochilganda
// ekran o'quvchiga sarlavha bilan tavsifni o'qiydi.

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  /** Tasdiq tugmasi matni. Berilmasa — "O'chirish". */
  confirmLabel?: string
  /** `false` bo'lsa tugma neytral ko'rinadi (o'chirish emas, oddiy amal). */
  destructive?: boolean
  onConfirm: () => void
}

export function ConfirmDialog({
  open, onOpenChange, title, description,
  confirmLabel, destructive = true, onConfirm,
}: ConfirmDialogProps) {
  const t = useT()
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/40 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 w-[min(24rem,calc(100vw-2rem))]',
            '-translate-x-1/2 -translate-y-1/2 rounded-lg border bg-popover p-5 shadow-lg',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
          )}
        >
          <Dialog.Title className="text-lead font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-1.5 text-body text-muted-foreground">
            {description || t('common.irreversible')}
          </Dialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="outline" size="sm">{t('common.cancel')}</Button>
            </Dialog.Close>
            <Button
              size="sm"
              variant={destructive ? 'destructive' : 'default'}
              onClick={() => { onOpenChange(false); onConfirm() }}
            >
              {confirmLabel || t('common.delete')}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/**
 * Tasdiqlash oynasini boshqarish uchun qisqartma.
 *
 *   const del = useConfirm<Product>()
 *   ...
 *   <button onClick={() => del.ask(p)}>O'chirish</button>
 *   <ConfirmDialog {...del.props} title={...} onConfirm={() => remove(del.target!)} />
 *
 * Nishon (`target`) saqlanadi, chunki oyna ochilgandan keyin ham
 * "aynan qaysi element" degan savolga javob kerak.
 */
export function useConfirm<T>() {
  const [target, setTarget] = React.useState<T | null>(null)
  return {
    target,
    ask: (v: T) => setTarget(v),
    props: {
      open: target !== null,
      onOpenChange: (o: boolean) => { if (!o) setTarget(null) },
    },
  }
}
