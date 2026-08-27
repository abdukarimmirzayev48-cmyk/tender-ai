import { useState } from 'react'
import { api, ApiError } from '@/api'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// PAROLNI O'ZGARTIRISH (auth-6).
//
// JORIY parol majburiy — bu formallik emas. Ochiq qolgan kompyuter yoki
// o'g'irlangan sessiya bilan begona odam parolni o'zgartirib, hisobni
// butunlay egallab olardi: egasi endi kira olmasdi, hujumchi esa qola
// berardi. Kompaniya hisobi BITTA, ya'ni bu yerda zarar ERP dagidan ham
// kattaroq.
//
// PAROL QOIDASI BU YERDA TAKRORLANMAYDI. Uzunlik talabi serverda
// (`AUTH_PASSWORD_MIN`) va uning xato matni nima qilish kerakligini
// aytadi. Bu yerda takrorlansa, ikki joyda ikki xil raqam qolib ketishi
// aniq. Shuning uchun faqat FORMANING o'z shartlari tekshiriladi:
// maydonlar to'la va ikki nusxa mos.
//
// Server xatosi O'ZBEKCHA keladi, interfeys esa uch tilli. Shuning uchun
// bilingan holatlar (429, 503) mijoz tilida ko'rsatiladi; qolganlari
// serverdan qanday kelsa shunday — noma'lum xatoni "tarjima qilib"
// yashirgandan ko'ra aslini ko'rsatgan afzal.

export default function PasswordPanel() {
  const t = useT()
  const [cur, setCur] = useState('')
  const [pw1, setPw1] = useState('')
  const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const mismatch = pw2.length > 0 && pw1 !== pw2
  const ready = cur.length > 0 && pw1.length > 0 && pw1 === pw2 && !busy

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!ready) return
    setBusy(true); setError(null); setDone(null)
    try {
      const r = await api.setPassword(cur, pw1)
      // Yopilgan sessiyalar soni AYTILADI: odam "boshqa
      // qurilmalarimdan chiqarildimi?" degan savolga javob olishi kerak.
      setDone(r.closed_sessions > 0
        ? t('pwd.doneClosed', { n: r.closed_sessions })
        : t('pwd.done'))
      setCur(''); setPw1(''); setPw2('')
    } catch (err) {
      const a = err as ApiError
      setError(
        a.status === 429
          ? t('auth.tooManyAttempts',
            { n: Math.max(1, Math.round((a.retryAfter ?? 900) / 60)) })
          : a.message.replace(/^\d+:\s*/, ''))
    } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      <p className="text-caption text-muted-foreground">{t('pwd.intro')}</p>

      <div className="space-y-1.5">
        <label htmlFor="pwd-cur" className="text-caption font-semibold text-muted-foreground">{t('pwd.current')}</label>
        <Input id="pwd-cur" type="password" autoComplete="current-password"
          value={cur} onChange={(e) => setCur(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="pwd-new" className="text-caption font-semibold text-muted-foreground">{t('pwd.new')}</label>
        <Input id="pwd-new" type="password" autoComplete="new-password"
          value={pw1} onChange={(e) => setPw1(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="pwd-rep" className="text-caption font-semibold text-muted-foreground">{t('pwd.repeat')}</label>
        <Input id="pwd-rep" type="password" autoComplete="new-password"
          value={pw2} onChange={(e) => setPw2(e.target.value)} />
        {mismatch && (
          <p className="text-caption text-destructive">{t('pwd.mismatch')}</p>
        )}
      </div>

      <p className="text-micro text-muted-foreground">{t('pwd.sessionsNote')}</p>

      {error && (
        <p role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-caption text-destructive">
          {error}
        </p>
      )}
      {done && (
        <p role="status"
          className="rounded-md border border-ok/40 bg-ok-soft px-3 py-2 text-caption text-ok-strong">
          {done}
        </p>
      )}

      <Button type="submit" disabled={!ready}>
        {busy ? t('pwd.saving') : t('pwd.save')}
      </Button>
    </form>
  )
}
