import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Vite konfiguratsiyasi. Dev-server :5173 da ishlaydi (backend CORS shunga ruxsat bergan).
//
// `@` taxallusi SHART: shadcn uslubidagi komponentlar
// `@/lib/utils` dan `cn()` ni import qiladi. Taxallus tsconfig.app.json da ham
// takrorlanadi — biri bundler, ikkinchisi tur tekshiruvi uchun.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    // ngrok (yoki boshqa tunnel) uchun: tashqi manzildan kelgan so'rovlar ham
    // qabul qilinsin. Vite 5.4.12+ notanish Host sarlavhasini bloklaydi
    // ("Blocked request. This host is not allowed") — shuning uchun allowedHosts.
    host: true,
    allowedHosts: ['.ngrok-free.app', '.ngrok.app', '.ngrok-free.dev', '.ngrok.io'],
    // HMR tunnel ortida HTTPS/443 orqali keladi; aks holda WebSocket ulanmaydi.
    hmr: { clientPort: 443 },
    // API'ni SHU domen ostida uzatamiz => bitta tunnel yetadi va CORS kerak emas.
    // Frontend .env da VITE_API_BASE=/api bo'lishi shart.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
