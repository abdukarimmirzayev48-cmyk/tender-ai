import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite konfiguratsiyasi. Dev-server :5173 da ishlaydi (backend CORS shunga ruxsat bergan).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
})
