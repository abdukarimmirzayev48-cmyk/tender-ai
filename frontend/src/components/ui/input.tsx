import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
    return (
        <input
            type={type}
            data-slot="input"
            className={cn(
                'border-input file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground flex h-9 w-full min-w-0 rounded-md border bg-card px-3 py-1 outline-none transition-colors file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-body file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
                // MOBILDA 16px. iOS Safari 16px dan kichik maydonga bosilganda
                // sahifani ZUMLAYDI va qaytarmaydi — foydalanuvchi har yozgandan
                // keyin qo'lda kichraytirishga majbur bo'lardi. Keng ekranda
                // ilovaning o'z o'lchamiga qaytadi.
                'text-base md:text-body',
                'focus-visible:border-ring',
                'aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/25',
                className
            )}
            {...props}
        />
    )
}

export { Input }
