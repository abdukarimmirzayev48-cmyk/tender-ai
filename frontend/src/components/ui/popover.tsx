import * as React from 'react'
import * as PopoverPrimitive from '@radix-ui/react-popover'

import { cn } from '@/lib/utils'

// OCHILADIGAN PANEL — ilovada to'rt joyda kerak: mahsulot filtri, kategoriya
// filtri, manba holati va sozlamalar menyusi.
//
// AVVAL har biri O'ZI yozgan edi: `useState(open)` + `document`ga
// `mousedown` tinglovchisi. Natijada har birida bir xil kamchilik takrorlanardi:
//   · Escape ishlamasdi (to'rttadan bittasida bor edi);
//   · yopilgach fokus tugmaga QAYTMASDI — Tab bosilsa sahifa boshiga sakrardi;
//   · `aria-expanded` / `aria-controls` yo'q edi, ya'ni ekran o'quvchi
//     tugmaning nimadir ochishini bilmasdi;
//   · panel ekran chetiga chiqib ketsa kesilardi (joylashuv hisoblanmasdi).
// Radix bularning HAMMASINI qiladi va o'zimizda 4 marta takrorlangan
// ~25 qatorli mantiq yo'qoladi.

const Popover = PopoverPrimitive.Root
const PopoverTrigger = PopoverPrimitive.Trigger
const PopoverAnchor = PopoverPrimitive.Anchor

function PopoverContent({
  className, align = 'start', sideOffset = 6, ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          'z-50 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg',
          // Panel hech qachon ekrandan baland bo'lmaydi — Radix o'lchagan
          // bo'sh joy CSS o'zgaruvchisi orqali keladi.
          'max-h-[var(--radix-popover-content-available-height)]',
          'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
          'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
}

export { Popover, PopoverTrigger, PopoverContent, PopoverAnchor }
