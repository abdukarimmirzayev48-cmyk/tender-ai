import path from 'node:path'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// --- QURILMA QO'ROVULI: mahalliy manzil singib qolmasin ---------------------
//
// O'LCHANGAN NOSOZLIK (2026-09-01). `deploy/bin/deploy.sh` relizni
// `git archive` bilan yasaydi, `frontend/.env` esa KUZATILMAGAN fayl —
// relizga tushmaydi. Shu sababli qurilma `VITE_API_BASE` siz yurardi va
// zaxira qiymat qurilmaga singib qolardi:
//
//     dist/assets/index-*.js:  localhost:8000  x1   (butun API)
//     dist/assets/index-*.js:  localhost:5173  x3   (sozlama shakli)
//
// Ya'ni ishlab chiqarish sahifasidagi HAR so'rov foydalanuvchi
// brauzerida `localhost:8000` ga ketardi va buni HECH NARSA
// ko'rsatmasdi — qurilma muvaffaqiyatli tugardi.
//
// NEGA `APP_ENV`, `mode` EMAS: `vite build` ning standart rejimi
// HAR DOIM `production`, ishlab chiquvchi o'z mashinasida qurganda
// ham. `mode` ga qarasak, mahalliy `VITE_ERP_WEB=http://localhost:5174`
// bilan oddiy qurilma ham yiqilardi. Muhitning HAQIQIY nomi
// `APP_ENV` da (`deploy.sh` uni beradi).
function mahalliymi(u: string): boolean {
  const host = (u.match(/^[a-z][a-z0-9+.-]*:\/\/([^/?#]+)/i)?.[1] || '')
    .replace(/^.*@/, '').replace(/:\d+$/, '').toLowerCase()
  if (!host) return false          // nisbiy yo'l (`/api`) — mahalliy emas
  return host === 'localhost' || host.endsWith('.localhost')
    || host === 'host.docker.internal' || host.endsWith('.local')
    || host.endsWith('.internal') || /^127\./.test(host)
    || host === '0.0.0.0' || host === '::1' || host === '[::1]'
    || /^10\./.test(host) || /^192\.168\./.test(host)
    || /^172\.(1[6-9]|2\d|3[01])\./.test(host)
}

function ommaviyUrlQorovuli(env: Record<string, string>): Plugin {
  return {
    name: 'ommaviy-url-qorovuli',
    apply: 'build',
    buildStart() {
      const muhit = (process.env.APP_ENV || 'dev').trim().toLowerCase()
      const qatiy = muhit === 'staging' || muhit === 'production'
      const xato: string[] = []
      const ogoh: string[] = []

      const api = (env.VITE_API_BASE || '').trim()
      if (!api) {
        (qatiy ? xato : ogoh).push(
          `VITE_API_BASE berilmagan — zaxira \`/api\` ishlatiladi`)
      } else if (mahalliymi(api)) {
        (qatiy ? xato : ogoh).push(
          `VITE_API_BASE mahalliy manzilga ishora qilyapti: ${api}`)
      } else if (/^[a-z][a-z0-9+.-]*:\/\//i.test(api)) {
        // To'liq manzil cross-site bo'ladi va sessiya cookie'si
        // (`SameSite=Lax`) YUBORILMAYDI — kirish umuman ishlamaydi.
        (qatiy ? xato : ogoh).push(
          `VITE_API_BASE to'liq manzil (${api}) — same-origin \`/api\` kerak`)
      }

      const erp = (env.VITE_ERP_WEB || '').trim()
      if (erp && mahalliymi(erp)) {
        (qatiy ? xato : ogoh).push(
          `VITE_ERP_WEB mahalliy manzilga ishora qilyapti: ${erp}`)
      }

      for (const o of ogoh) this.warn(`ommaviy manzil: ${o}`)
      if (xato.length) {
        // QURILMA TO'XTAYDI. Buzuq qurilmani chiqarib, nosozlikni
        // foydalanuvchining brauzerida ko'rsatishdan ko'ra shu yerda
        // yiqilgan yaxshi.
        throw new Error(
          [`APP_ENV=${muhit} uchun frontend sozlamasi YAROQSIZ:`,
            ...xato.map((x) => `  - ${x}`),
            `  Tuzatish: \`deploy/env/${muhit}.env\` da VITE_API_BASE=/api.`,
          ].join('\n'))
      }
    },
  }
}

// Vite konfiguratsiyasi. Dev-server :5173 da ishlaydi (backend CORS shunga ruxsat bergan).
//
// `@` taxallusi SHART: shadcn uslubidagi komponentlar
// `@/lib/utils` dan `cn()` ni import qiladi. Taxallus tsconfig.app.json da ham
// takrorlanadi — biri bundler, ikkinchisi tur tekshiruvi uchun.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, 'VITE_')
  return {
  plugins: [react(), tailwindcss(), ommaviyUrlQorovuli(env)],
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
  }
})
