import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { I18nProvider } from './i18n'
import { ThemeProvider } from './theme'
import './index.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root topilmadi — index.html ni tekshiring.')

// Til va mavzu — butun ilova uchun ikki provider. Ikkalasi ham
// `localStorage` dan o'qiydi; mavzu esa `index.html` dagi kichik skript
// bilan React dan OLDIN qo'yiladi (oq chaqnash bo'lmasin).
createRoot(root).render(
  <React.StrictMode>
    <ThemeProvider>
      <I18nProvider>
        {/* Oxirgi himoya: panel darajasidagi chegaralardan o'tib ketgan xato
            ham oq ekran emas, o'qiladigan xabar bo'lib chiqsin. */}
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </I18nProvider>
    </ThemeProvider>
  </React.StrictMode>,
)
