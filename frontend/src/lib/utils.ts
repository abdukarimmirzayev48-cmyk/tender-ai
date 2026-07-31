import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Tailwind sinflarini birlashtiradi va ZIDDIYATLARNI hal qiladi.
 * `clsx` shartli sinflarni yig'adi, `twMerge` esa keyingi sinf oldingisini
 * bosishini ta'minlaydi (`px-2 px-4` -> `px-4`) — aks holda komponentga
 * tashqaridan berilgan `className` ichki standart qiymatni bosa olmasdi.
 *
 * Vengeance UI (shadcn registry) komponentlari SHU funksiyani `@/lib/utils`
 * dan import qiladi — fayl nomi va yo'li o'zgartirilmasin.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
