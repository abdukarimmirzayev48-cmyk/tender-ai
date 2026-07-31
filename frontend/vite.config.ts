import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Vite konfiguratsiyasi. Dev-server :5173 da ishlaydi (backend CORS shunga ruxsat bergan).
//
// `@` taxallusi SHART: Vengeance UI (shadcn registry) komponentlari
// `@/lib/utils` dan `cn()` ni import qiladi. Taxallus tsconfig.app.json da ham
// takrorlanadi — biri bundler, ikkinchisi tur tekshiruvi uchun.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
  },
})
