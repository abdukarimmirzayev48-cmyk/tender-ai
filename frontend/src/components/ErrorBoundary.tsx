import React from 'react'
import Icon from './Icon'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'

// XATO CHEGARASI — render paytidagi xato butun ilovani o'chirmasligi uchun.
//
// NEGA KERAK: React 18 da render paytida ushlanmagan xato yuzaga kelsa, React
// BUTUN daraxtni uzib tashlaydi. Chegara bo'lmasa foydalanuvchi mutlaqo BO'SH
// oq sahifani ko'radi — na xabar, na tugma. Aynan shu holat "bildirishnomalar
// bo'limi bo'sh ochilmoqda" nosozligida bo'lgan edi (NotifySettings da hook
// erta `return` dan keyin chaqilgani uchun React xato bergan).
//
// Ildiz sabab tuzatildi, lekin chegara baribir kerak: keyingi xato ham
// jimgina oq ekranga aylanmasin, foydalanuvchi hech bo'lmasa NIMA bo'lganini
// ko'rsin va ilovaning qolgan qismi ishlashda davom etsin.
//
// SINF KOMPONENTI SHART: `getDerivedStateFromError` va `componentDidCatch`
// ning hook ekvivalenti React da hozircha yo'q.
interface Props {
  children: React.ReactNode
  /** Chegara qayta o'rnatiladigan qiymat (masalan ochiq bo'lim kaliti).
   *  O'zgarsa xato tozalanadi — foydalanuvchi boshqa bo'limga o'tib,
   *  qaytib kelganda "singan" holat yopishib qolmaydi. */
  resetKey?: unknown
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidUpdate(prev: Props) {
    // Bo'lim almashsa — yangi boshlanish.
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Konsolga to'liq stek — ishlab chiquvchi uchun. Foydalanuvchi ko'radigan
    // matn esa pastdagi `Fallback` da, tarjima qilingan holda.
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return <Fallback error={this.state.error} onRetry={() => this.setState({ error: null })} />
    }
    return this.props.children
  }
}

// Ko'rinish alohida funksional komponentda — shundagina `useT()` ishlatiladi
// (sinf komponentida hook chaqirib bo'lmaydi).
function Fallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const t = useT()
  return (
    <div role="alert"
      className="rounded-xl border border-urgent/40 bg-urgent-soft p-5 text-urgent-strong">
      <div className="flex items-center gap-2">
        <Icon name="alert" size={16} />
        <b className="text-body">{t('common.crashTitle')}</b>
      </div>
      <p className="mt-1.5 text-caption leading-relaxed">{t('common.crashBody')}</p>
      <pre className="mt-3 max-h-40 overflow-auto rounded-lg border border-current/20 bg-card/60 p-2.5 text-micro leading-relaxed text-foreground">
        {error.message}
      </pre>
      <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
        <Icon name="refresh" size={14} />
        {t('common.retry')}
      </Button>
    </div>
  )
}
