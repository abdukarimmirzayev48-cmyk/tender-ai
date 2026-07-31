# Telegram bildirishnoma (P0-10 ning ikkinchi kanali)

Email bildirishnomasi yoniga **Telegram** kanali qo'shildi. Ikkalasi
**mustaqil yoqiladi**, lekin **moslik chegarasi**, kuzatuv oynasi va ballash
ular uchun **bir xil** — nomzodlar bir marta hisoblanib, yoqilgan kanallarga
tarqatiladi.

Nega chegara umumiy: uni ikki joyda saqlasak ular ertami-kechmi bir-biridan
uzoqlashadi va foydalanuvchi nega Telegram boshqa natija berayotganini
tushunmay qoladi.

---

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `schema_patch_notify_telegram.sql` | `notify_settings` ga 2 ta ustun (idempotent) |
| `schema_patch_notify_subscribers.sql` | `notify_telegram_subscriber` jadvali |
| `api/telegram.py` | **faqat transport**: Bot API chaqiruvi, xabarni bo'lish, escape |
| `api/notify.py` | xabar matni (`render_telegram`), yuborish, jurnal, tsikl |
| `api/main.py` | `/notify/telegram/*` endpointlari |
| `frontend/src/components/NotifySettings.jsx` | ikki kanalli forma |
| `_tests/notify_test.py` | sinovlar — **haqiqiy xabar yubormaydi** |

`api/telegram.py` **xabar matnini qurmaydi**: summa/sana formatlash va
`card_url()` `api/notify.py` da turadi, ularni takrorlasak ikkita haqiqat
manbai paydo bo'lardi. Shu bo'linish tufayli import bir tomonlama
(`notify` → `telegram`), aylanma import yo'q.

---

## 0. O'rnatish — uch qadam

### 1) Baza patchi (bir marta)

```bash
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_telegram.sql
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_subscribers.sql
```

Birinchisi `notify_settings` ga `telegram_enabled` va `telegram_chat_id`
ustunlarini qo'shadi. Ikkinchisi `notify_telegram_subscriber` jadvalini
yaratadi va mavjud `telegram_chat_id` ni obunachiga **ko'chiradi** — patchdan
keyin siz hech narsa qilmasdan avvalgidek xabar olasiz.

> `telegram_chat_id` ustuni endi **ishlatilmaydi** (faqat orqaga moslik uchun
> qolgan) — qabul qiluvchilar `notify_telegram_subscriber` dan olinadi.

Patch qo'llanmagan bazada tizim **yiqilmaydi**: `notify.telegram_columns_ready()`
buni aniqlaydi, email bildirishnomasi ishlayveradi, interfeys esa
"baza patchi qo'llanmagan" deb ochiq aytadi.

### 1b) SMTP — endi PLATFORMA sozlamasi

Email kanali ham qayta ishlangan: foydalanuvchidan **pochta serveri
so'ralmaydi**. U interfeysда faqat **o'z emailini** yozadi; xabarni
platformaning o'zi yuboradi.

Server rekvizitlari `.env` da:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=tender-ai@kompaniya.uz
SMTP_TLS=1
```

`notify_settings` dagi `smtp_*` ustunlari **eskirdi** — o'chirilmadi
(ma'lumot yo'qotmaslik uchun), lekin endi o'qilmaydi.

> Nega: host/port/STARTTLS/login — operatorning infratuzilma detali.
> Foydalanuvchi unga javob bera olmaydi. Bundan tashqari har foydalanuvchi
> o'z pochta serverini kiritsa, xabarlar turli manzillardan kelib spamга
> tushardi.

### 2) `.env` ga bot tokeni

```
TELEGRAM_BOT_TOKEN=123456789:AA...
```

Token @BotFather dan olinadi (`/newbot` yoki `/mybots` → *API Token*).

**Token bazada SAQLANMAYDI** — `SMTP_PASSWORD` bilan bir xil qoida. Token bilan
botni to'liq boshqarish mumkin, baza dumpi esa ko'p qo'ldan o'tadi. Token yo'q
bo'lsa Telegram kanalini **yoqib bo'lmaydi** va tizim aniq xato beradi.

Tokendan keyin API'ni qayta ishga tushiring (`.env` import paytida o'qiladi).

### 3) Telegramni ulash — BIR MARTALIK HAVOLA

Chat ID **qo'lда kiritilmaydi** va botga shunchaki `/start` bosish ham
**yetarli emas**. Oqim:

1. Foydalanuvchi **Akkaunt → Bildirishnoma → Telegram → "Telegramni ulash"**
   ni bosadi.
2. Platforma bir martalik token yaratadi va havolani yangi oynada ochadi:
   `https://t.me/<bot>?start=<token>`
3. Telegram bot suhbatini ochadi. Foydalanuvchi **Start** bosadi — Telegram
   botga aynan `/start <token>` xabarini yuboradi.
4. `notify.consume_links()` `getUpdates` dan o'sha tokenli xabarni topadi,
   tokenni **band qiladi** va chatni ulanma qilib yozadi.
5. Interfeys havolani ochgach holatni qisqa oraliqda so'rab turadi va ulanish
   yakunlanishi bilan ro'yxatni o'zi yangilaydi — foydalanuvchi qaytib kelib
   hech narsa bosmaydi.

**Guruhga ulash**: botni guruhga qo'shing va guruhда tokenni yuboring. Guruh
ID lari **manfiy** bo'ladi (`-1001234567890`) — shuning uchun ustun `TEXT`.

Token **30 daqiqa** amal qiladi va **bir marta** ishlaydi (`notify_telegram_link`).

> **Bot suhbatni o'zi boshlay olmaydi** — bu Telegram cheklovi. Shuning uchun
> birinchi qadamni doim odam qiladi; platforma faqat havolani beradi.

### Nega token kerak

Tizimda autentifikatsiya yo'q. Tokensiz model — "`/start` bosgan har kim
obunachi" — **botni topgan istalgan odamga** kompaniyangizga mos tenderlar
ro'yxatini (moslik ballari bilan) ochib berardi. Bot tasodifan qo'shilgan
guruh ham xabar olardi.

Token esa **"bu suhbat platformadagi foydalanuvchiga tegishli" degan yagona
dalil**: uni faqat interfeysга kira olgan odam oladi.

**Tokensiz `/start` — hech narsa qilmaydi.** `consume_links()` uni e'tiborga
olmaydi.

Ulangan har bir suhbat interfeysда ro'yxatda turadi: uni **so'ndirish**
(`enabled=false`) yoki **uzish** mumkin.

> `schema_patch_notify_link.sql` eski usulda qo'shilgan barcha obunachilarni
> `source='legacy'` deb belgilab, **o'chirib qo'yadi** — ular tasdiqlanmagan.
> Ularni qayta ulash uchun havoladan foydalaniladi.

---

## 1. Endpointlar

| Metod | Yo'l | Vazifasi |
|---|---|---|
| `GET` | `/notify/settings` | sozlamalar + `telegram_token_set`, `subscribers_ready` |
| `PUT` | `/notify/settings` | `telegram_enabled` ni saqlaydi (chat ID **kerak emas**) |
| `GET` | `/notify/telegram/bot` | bot `username` i (kimga `/start` yozish kerak) |
| `GET` | `/notify/telegram/subscribers` | ulangan suhbatlar ro'yxati |
| `POST`| `/notify/telegram/link` | bir martalik ulash havolasini yaratadi |
| `GET` | `/notify/telegram/link/{token}` | havola bosildimi (+ tokenlarni o'qiydi) |
| `PUT` | `/notify/telegram/subscribers/{chat_id}` | `{enabled}` — yoqish/o'chirish |
| `DELETE`| `/notify/telegram/subscribers/{chat_id}` | ro'yxatdan olib tashlash |
| `POST`| `/notify/telegram/test` | sinov xabari (`?chat_id=` — faqat bittasiga) |

**Token hech qaysi javobda qaytmaydi** — faqat `telegram_token_set: true/false`.

Sinov xabari `telegram_enabled` ni **talab qilmaydi**: u aynan "yoqishdan oldin
ishlayaptimi?" degan savolga javob beradi.

`DELETE` — obunachi `/start` ni **qayta bossa yana qo'shiladi**. Butunlay
to'xtatish uchun o'chirish emas, `enabled=false` ishlatiladi.

---

## 2. Takroriy xabar bo'lmasligi

`notify_sent` PK — `(tender_id, kind)`. Har kanal, Telegramда esa **har
obunachi** o'z `kind` ini yozadi:

| Kanal | `kind` | `email` ustuni |
|---|---|---|
| Email | `new_match` | qabul qiluvchi manzil |
| Telegram | `new_match_tg:<chat_id>` | `tg:<chat_id>` |

Nega kanal bo'yicha alohida: agar ikkala kanal bitta `new_match` qatoriga
tayansa, keyinroq Telegram yoqilganда email allaqachon "yuborilgan" deb
belgilagan tenderlar Telegramга **hech qachon** tushmasdi.

Nega **obunachi** bo'yicha alohida: obunachi bittadan ko'p. Hammasi bitta
`new_match_tg` qatoriga tayansa, birinchi obunachiga yuborilgan tender
qolganlariga hech qachon ketmasdi — ya'ni bugun `/start` bosgan odam
kechagi tenderlarni **umuman ko'rmasdi**.

Shu sababli `run()` da cheklov (`--limit`) **har obunachiда, o'z jurnali
bo'yicha filtrlangandan keyin** qo'llanadi.

Bitta obunachi yiqilsa (bot bloklangan, guruhdan chiqarilgan) — **qolganlariga
baribir ketadi**, xato esa natijadagi `telegram.errors` da qaytadi.

---

## 3. Kanallar bir-birini yiqitmaydi

`notify.run()` Telegram xatosida **email yuborilishini bekor qilmaydi** va
aksincha. Har kanal xatosi natijadagi o'z `error` maydonida qaytadi:

```json
{
  "found": 3, "sent": 3, "to": "siz@kompaniya.uz", "error": null,
  "telegram": { "enabled": true, "found": 3, "sent": 0, "messages": 0,
                "chat_id": "-100123", "error": "Chat topilmadi. ..." }
}
```

Xato **jimgina yutilmaydi**: `notify_new.py` `error` maydonlarini ko'radi va
**exit 2** bilan tugaydi — cron logда nosozlik ko'rinadi.

---

## 4. Xabar ko'rinishi

Telegram HTML rejimi (`parse_mode=HTML`) — faqat `<b>`, `<i>`, `<a>` ishlatiladi.

```
🟢 100 ball · katalog
Server infratuzilmasi xaridi        ← havola: base_url + /?tender=<id>
🏢 AGROBANK ATB
💰 17 128 200 000 UZS   ⏳ 31.07.2026 18:51
📍 Toshkent shahri
• Katalogingizga mos: kompyuter (kategoriya bo'yicha)
```

* **TZ qabul mezoni** — tender nomining o'zi tizimdagi **kartochkaga havola**.
* `&`, `<`, `>` escape qilinadi (aks holda Telegram xabarni rad etadi),
  **apostrof esa tegilmaydi** — o'zbekcha matnда u har qadamda uchraydi va
  `&#x27;` ga aylansa xabar o'qib bo'lmas holga keladi.
* Telegram bitta xabarga **4096 belgi** beradi. Uzun ro'yxat bo'linadi va
  kesim **blok chegarasidan** o'tadi: tender o'rtasidan kesilsa ochilgan
  `<b>`/`<a>` tegi yopilmay qoladi va Telegram **butun xabarni** rad etadi.
* Ball darajasi emoji bilan: 🟢 100, 🔵 ≥85, ⚪️ qolgani (Telegramда rang yo'q).

---

## 5. Tekshirish

```bash
# 1) Sozlamalar (token topildimi, patch qo'llandimi)
curl http://localhost:8000/notify/settings

# 2) Bot kim
curl http://localhost:8000/notify/telegram/bot

# 3) Kim /start bosgan
curl http://localhost:8000/notify/telegram/chats

# 4) Nima ketishini ko'rish (HECH NARSA yuborilmaydi)
python notify_new.py --dry-run --since-hours 168

# 5) Sinovlar — haqiqiy email ham, Telegram xabari ham yuborilmaydi
.venv/Scripts/python.exe _tests/notify_test.py
```

Soatlik yurish o'zgarmagan: `run_etl.py` ETL dan keyin `notify_new.py` ni
chaqiradi, u esa **yoqilgan barcha kanallarga** yuboradi.
