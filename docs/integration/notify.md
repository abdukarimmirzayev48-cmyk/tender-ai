# Email bildirishnoma (TZ P0-10) — INTEGRATSIYA QADAMLARI

> Bu fayldagi kod **umumiy fayllarga** tegadi (`api/main.py`, `frontend/src/api.js`,
> `frontend/src/App.jsx`, `run_etl.py`). Ular parallel ishlayotgan boshqa agentlar
> tomonidan ham tahrirlanadi, shuning uchun bu yerga **aynan ko'chiriladigan**
> ko'rinishda yozildi — o'zgartirishsiz qo'ying.

Yangi (mustaqil, hech kimga tegmaydigan) fayllar:

| Fayl | Vazifasi |
|---|---|
| `schema_patch_notify.sql` | `notify_settings` + `notify_sent` jadvallari (idempotent) |
| `api/notify.py` | nomzodlarni topish, ballash, xabar matni, SMTP |
| `notify_new.py` | ETL dan keyin chaqiriladigan skript |
| `frontend/src/components/NotifySettings.jsx` | akkaunt sahifasidagi forma |
| `frontend/src/styles/notify.css` | shu formaning uslublari |
| `_tests/notify_test.py` | sinovlar (haqiqiy email YUBORMAYDI) |

---

## 0. Baza va `.env`

```bash
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify.sql
```

`.env` ga **bitta qator** qo'shiladi (`.env.example` da izohi bilan bor):

```
SMTP_PASSWORD=
```

**SMTP paroli bazada saqlanmaydi.** `notify_settings` da faqat host/port/user/
from_email/chegara turadi. Parol bo'sh bo'lsa va `smtp_user` to'ldirilgan bo'lsa —
tizim `NotifyError` bilan **aniq xato** beradi, jimgina "yuborildi" demaydi.

---

## 1. `api/main.py` — endpointlar

### 1.1. Import qatoriga `notify` qo'shing

Bor qator (36-satr atrofida):

```python
from api import ai, ai_gonogo, ai_match, db, matching, queries  # noqa: E402  (load_dotenv dan keyin bo'lishi shart)
```

Yangi ko'rinishi:

```python
from api import ai, ai_gonogo, ai_match, db, matching, notify, queries  # noqa: E402  (load_dotenv dan keyin bo'lishi shart)
```

> `api/notify.py` `api.main` ni **modul darajasida import qilmaydi** (aylanma
> import bo'lardi) — `_product_matches` ni funksiya ichida kech import qiladi.
> Shuning uchun yuqoridagi qator xavfsiz.

### 1.2. So'rov modeli — boshqa `...In` modellari yoniga (100-satr atrofi)

```python
class NotifySettingsIn(BaseModel):
    """Email bildirishnoma sozlamalari. SMTP PAROLI YO'Q — u .env dan
    o'qiladi (SMTP_PASSWORD), bazaga ham, bu modelga ham tushmaydi."""
    enabled: bool = False
    email: Optional[str] = None          # bo'sh -> company_profile.email
    min_score: int = 70                  # moslik chegarasi (TZ: sozlanadi)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_use_tls: bool = True
    from_email: Optional[str] = None
    base_url: Optional[str] = None       # bo'sh -> `api/ommaviy_url.py`
```

> **19-vazifadan keyin:** kartochka havolasi `api/ommaviy_url.py`
> da quriladi (yagona manba). Bazadagi ijarachi qiymati mahalliy
> bo'lsa muhitdagi `APP_PUBLIC_URL` yutadi, `staging`/`production`
> da esa mahalliy manzil umuman qabul qilinmaydi. Batafsil:
> `docs/deploy.md` §10.

### 1.3. Endpointlar — `/catalog/seen` dan keyin (945-satr atrofi)

```python
# ---------------------------------------------------------------------------
# EMAIL BILDIRISHNOMA (TZ P0-10) — "mosligi yuqori yangi tender chiqdi"
# Xabarni `notify_new.py` skripti ETL dan keyin yuboradi; bu yerdagi
# endpointlar faqat SOZLAMALARNI boshqaradi va sinov xabarini yuboradi.
# ---------------------------------------------------------------------------
@app.get("/notify/settings")
def get_notify_settings():
    """Bildirishnoma sozlamalari. `smtp_password_set` — parol .env da bormi
    (parolning O'ZI hech qachon qaytmaydi)."""
    return notify.get_settings()


@app.put("/notify/settings")
def put_notify_settings(s: NotifySettingsIn):
    """Sozlamalarni saqlaydi (bitta faol yozuv)."""
    return notify.save_settings(s.model_dump())


@app.post("/notify/test")
def notify_test():
    """Sinov xabari — sozlamalar haqiqatan ishlayaptimi.
    `notify_sent` ga YOZMAYDI, ya'ni haqiqiy bildirishnomalarga ta'sir qilmaydi."""
    try:
        return notify.send_test()
    except notify.NotifyError as e:
        # Sozlama/SMTP xatosi — foydalanuvchi tuzatishi mumkin -> 400
        raise HTTPException(status_code=400, detail=str(e))
```

> Ixtiyoriy (qulay, lekin TZ talab qilmaydi) — interfeysdan qo'lda yurgizish:
>
> ```python
> @app.post("/notify/run")
> def notify_run(dry_run: bool = Query(True, description="Yubormasdan ko'rish")):
>     """Bildirishnoma tsiklini qo'lda yurgizadi (standart: dry-run)."""
>     try:
>         res = notify.run(dry_run=dry_run)
>     except notify.NotifyError as e:
>         raise HTTPException(status_code=400, detail=str(e))
>     # Xabar tanasi (text/html) javobda kerak emas — faqat xulosa
>     return {k: v for k, v in res.items() if k not in ("text", "html")}
> ```

---

## 2. `frontend/src/api.js` — IXTIYORIY

`NotifySettings.jsx` **hozircha o'zi so'rov qiladi** (faqat `apiUrl()` ni oladi),
shuning uchun bu qadam **shart emas** — komponent api.js ga tegmasdan ishlaydi.
Agar barcha so'rovlar bitta joydan o'tishi tamoyilini saqlamoqchi bo'lsangiz,
`api` obyektiga qo'shing:

```js
  // Email bildirishnoma (P0-10)
  notifySettings: () => request('GET', '/notify/settings'),
  saveNotifySettings: (body) => request('PUT', '/notify/settings', { body }),
  notifyTest: () => request('POST', '/notify/test'),
```

Keyin `NotifySettings.jsx` dagi `req(...)` chaqiruvlarini almashtiring:

| Hozirgi | Yangi |
|---|---|
| `req('GET', '/notify/settings')` | `api.notifySettings()` |
| `req('PUT', '/notify/settings', {...})` | `api.saveNotifySettings({...})` |
| `req('POST', '/notify/test')` | `api.notifyTest()` |

---

## 3. `frontend/src/App.jsx` — ikki o'zgarish

### 3.1. Akkaunt sahifasiga formani qo'shish

Import (14-satr atrofi, `CompanyProfile` yoniga):

```jsx
import NotifySettings from './components/NotifySettings.jsx'
```

Bor qator (295-satr atrofi):

```jsx
        {view === 'account' && <CompanyProfile standalone onSaved={setAccount} />}
```

Yangi ko'rinishi:

```jsx
        {view === 'account' && (
          <>
            <CompanyProfile standalone onSaved={setAccount} />
            <NotifySettings />
          </>
        )}
```

### 3.2. Emaildagi havolani ochish — `?tender=<id>` (TZ QABUL MEZONI)

Bildirishnomadagi har havola `base_url + /?tender=<id>` ko'rinishida.
Bu holda tender kartochkasi (drawer) **avtomatik ochilishi** kerak.
Boshqa `useEffect` lar yoniga qo'ying:

```jsx
  // Email bildirishnomadagi kartochka havolasi: /?tender=123 -> drawer ochiladi.
  // TZ P0-10 qabul mezoni: "xabar tizimdagi tender kartochkasiga havolani
  // o'z ichiga oladi" — havola BOSILGANDA aynan o'sha kartochka ochilsin.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('tender')
    if (id) setSelected({ id: Number(id) })
  }, [])
```

Drawer yopilganda manzil tozalansin (aks holda yangilashda qayta ochiladi) —
bor qator (307-satr atrofi):

```jsx
      {selected && (
        <TenderDrawer id={selected.id} match={selected.match} onClose={() => setSelected(null)} />
```

Yangi ko'rinishi:

```jsx
      {selected && (
        <TenderDrawer id={selected.id} match={selected.match} onClose={() => {
          setSelected(null)
          // Emaildan kelgan ?tender= parametrini olib tashlaymiz
          if (new URLSearchParams(window.location.search).has('tender')) {
            window.history.replaceState({}, '', window.location.pathname)
          }
        }} />
```

---

## 4. `run_etl.py` — ETL dan keyin xabar yuborish

TZ: *"bildirishnoma soatlik kuzatish tsikli davomida keladi"*. Skript ETL
tugagach chaqiriladi va **oxirgi tsiklda birinchi marta ko'rilgan**
(`tender.first_seen_at` ≥ oxirgi `etl_run` tsikli boshlanishi) tenderlarni oladi.

`main()` ichida, kategoriyalash qadamidan **keyin** (121-satr atrofi):

```python
    # 3) Kategoriyalash (yangi tenderlarni belgilaydi) — post-qadam
    run_step("categorize", "etl_categorize.py", [], None)

    # 4) Email bildirishnoma (P0-10) — mosligi chegaradan yuqori YANGI
    #    tenderlar haqida xabar. Kategoriyalashdan KEYIN turishi shart:
    #    moslik balli kategoriya kodlariga tayanadi. Sozlama o'chiq bo'lsa
    #    yoki yangi tender bo'lmasa — skript jimgina 0 bilan tugaydi.
    run_step("notify", "notify_new.py", [], None)
```

Alohida ham yurgizsa bo'ladi:

```bash
python notify_new.py --dry-run      # nima ketishini ko'rsatadi (yubormaydi)
python notify_new.py                # haqiqiy yuborish
python notify_new.py --min-score 85 --limit 5
python notify_new.py --force        # allaqachon xabar ketganlarni ham
```

### Soatlik jadval

Soatlik jadvalni `register_task.ps1` (boshqa agent qo'shgan) o'rnatadi va u
`run_etl.py` ni yurgizadi. Shuning uchun yuqoridagi **4-qadam yetarli** —
bildirishnoma har tsiklda avtomatik ketadi, alohida jadval yozuvi kerak emas.
Bu TZ qabul mezonini yopadi: *"bildirishnoma soatlik kuzatish tsikli davomida
keladi"*.

Agar jadval baribir alohida chaqiruv qo'shmoqchi bo'lsa, u **ETL dan keyin**
turishi shart (aks holda "yangi" tenderlar hali bazada bo'lmaydi).

---

## 5. Tekshirish ro'yxati (integratsiyadan keyin)

```bash
# 1) Sozlamalar o'qiladimi
curl http://localhost:8000/notify/settings

# 2) Chegara saqlanadimi
curl -X PUT http://localhost:8000/notify/settings -H 'Content-Type: application/json' \
  -d '{"enabled":true,"email":"siz@kompaniya.uz","min_score":85,
       "smtp_host":"smtp.gmail.com","smtp_port":587,"smtp_user":"siz@kompaniya.uz",
       "smtp_use_tls":true,"from_email":"siz@kompaniya.uz",
       "base_url":"http://localhost:5173"}'

# 3) Nima ketishini ko'rish (hech narsa yuborilmaydi)
python notify_new.py --dry-run --since-hours 168
```

Interfeysda: **Akkaunt** sahifasi → *Email bildirishnoma* → chegarani
o'zgartiring → **Saqlash** → **Sinov xabarini yuborish**.
SMTP sozlanmagan bo'lsa tugma qizil xato matnini ko'rsatadi (jimgina
"muvaffaqiyatli" demaydi).
