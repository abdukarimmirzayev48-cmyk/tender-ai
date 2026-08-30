# Ma'lumot xaritasi — huquqiy tekshiruv uchun texnik asos

**Sana:** 2026-08-31 · **Baza:** `xtxarid` · **O'lchov usuli:** kodni o'qish va bazaga so'rov

---

## 0. Bu hujjat NIMA EMAS

> Bu yerda **huquqiy xulosa YO'Q**. "Ruxsat etiladi", "qonuniy",
> "shaxsiy ma'lumot hisoblanadi" kabi baholar berilmagan — ular
> yuristning ishi.
>
> Bu yerda faqat **o'lchangan faktlar**: qayerdan olinadi, nima
> saqlanadi, qayerga yuboriladi, qancha vaqt turadi.
>
> Aniqlanmagan narsa **NOMA'LUM** deb belgilangan (§9). "Noma'lum" va
> "yo'q" bu hujjatda aralashtirilmaydi.

---

## 1. Tashqi ma'lumot manbalari

| # | Domen | Usul | Endpoint | Chastota | Kim chaqiradi |
|---|---|---|---|---|---|
| S1 | `api.xt-xarid.uz` | JSON-RPC `POST` | `/rpc` (`method=ref`) | **soatiga 1** | `etl_tenders.py` |
| S2 | `api.xt-xarid.uz` | JSON-RPC `POST` | `/urpc` | soatiga 1 | `etl_details.py` |
| S3 | `api.xt-xarid.uz` | `GET` (proksi) | `/file/{file_id}` | talab bo'yicha | `api/main.py` yuklab olish |
| S4 | `apietender.uzex.uz` | REST `POST` | `/api/common/TradeList` | **soatiga 1** | `etl_uzex.py` |
| S5 | `apietender.uzex.uz` | REST `GET` | `/api/common/GetTrade/{id}` | soatiga 1 | `etl_uzex.py` |
| S6 | `apietender.uzex.uz` | REST `POST` | `/api/common/DownloadFile` | talab bo'yicha | hujjat matnini ajratish |
| S7 | `apietender.uzex.uz` | REST `GET` | `/api/Libs/GetRegions` | kamdan-kam | `etl_dims.py` |

**Chastota tasdiqlandi** (Windows Task Scheduler'dan o'qildi, taxmin emas):

```
TenderAI-ETL-Hourly : interval = PT1H, state = Ready
TenderAI-RAG        : interval = PT1H, state = Ready
```

**Reyestrlar (S1):** `ref_tender_public`, `ref_selection_public` —
ikkalasi ham ochiq reyestr. **Savdo turlari (S4):** `TypeId=1`
("tanlov") va `TypeId=2` ("tender").

**Autentifikatsiya:** manbalarga **kalit yoki hisob ishlatilmaydi** —
so'rovlar anonim, faqat `User-Agent` sarlavhasi bilan
(`etl_uzex.py:_BROWSER_UA`). Ya'ni tizim yopiq API ga kirmaydi.

**Hajm (o'lchandi):** `uzex` 2 683 tender, `xt-xarid` 922 tender.

### 1.1 Qayta tarqatish xulqi

| Nima | Bizda saqlanadimi | Foydalanuvchiga qanday beriladi |
|---|---|---|
| Tender metama'lumoti | **Ha** (`tender`, `tender_detail`, `tender_item`) | Interfeys va API orqali |
| Xom manba javobi | **Ha** (`raw_json`, 3 605 + 2 964 + 11 898 qator) | API da bevosita berilmaydi |
| Hujjat **fayli** | **YO'Q** | `/documents/{id}/download` — manbadan **proksi/redirect**, faylni saqlamaymiz |
| Hujjat **matni** | **Ha** (`tender_document_text`, 4 011 qator, **134 MB**) | Chat javoblarida iqtibos sifatida |
| Hujjat bo'laklari | **Ha** (`doc_chunk`, 188 561 qator) | Semantik qidiruvda |

Hujjat fayli **diskda saqlanmaydi**: yuklab olish so'rovi manbaga
uzatiladi (`StreamingResponse`, `Content-Disposition: attachment`).
Matn esa ajratib olinadi va saqlanadi.

---

## 2. Nozik yoki shaxsiy bo'lishi mumkin bo'lgan maydonlar

> Quyidagi raqamlar **naqsh mavjudligini** o'lchaydi. Qiymatlar bu
> hujjatga **ko'chirilmagan**. "Shaxsiy ma'lumotmi" degan savol —
> yuristniki.

### 2.1 Ommaviy manbadan kelgan (jismoniy shaxsga tegishli bo'lishi mumkin)

| Maydon | Jadval | To'ldirilgan | O'lchangan xususiyat |
|---|---|---|---|
| `director` | `tender_detail` | **2 964** | 2 959 tasida ism ko'rinishidagi matn |
| `contacts` (JSON ichida) | `tender.raw_json->detail` | **2 683** | o'rtacha 80 belgi; **78** tasida 7+ raqamli ketma-ketlik, **50** tasida email naqshi |
| `company_details` | `tender_detail` | **2 960** | matn (`TEXT`), tuzilmasi tahlil qilinmagan |
| `delivery_address` | `tender_item` | **9 973** | yetkazib berish manzili |
| `company_name` | `tender` | 3 605 | yuridik shaxs nomi |
| Hujjat matni | `tender_document_text` | 4 011 | **441** tasida email naqshi, **212** tasida telefon formatidagi naqsh |
| Xom JSON | `tender.raw_json` | 3 605 | **3 605** tasida telefonga o'xshash raqam naqshi, **52** tasida email naqshi |

### 2.2 Tizimning o'zi yaratgan

| Maydon | Jadval | Qatorlar | Izoh |
|---|---|---|---|
| `username`, `email`, `password_hash` | `company_account` | 4 | Kompaniya hisobi (odam emas — hodimlar ERP da) |
| `contact_name`, `email`, `phone` | `company_profile` | 1 | Kompaniya kiritgan aloqa ma'lumoti |
| `ip`, `user_agent`, `username` | `login_attempt` | 74 | **90 kundan keyin avtomatik o'chadi** |
| `ip`, `user_agent`, `token_hash` | `company_session` | 21 | Muddati tugagach o'chadi |
| `ip`, `user_agent`, `actor_id` | `audit_jurnal` | 5 | **APPEND-ONLY — o'chirilmaydi** |
| `login`, `ism`, `rol` | `actor` | 5 | ERP hodimiga xarita (parol yo'q) |
| `content`, `citations` | `chat_message` | 245 | Saqlangan suhbat + iqtibos |
| `email`, `telegram_chat_id` | `notify_settings`, `notify_sent` | 1 / 22 | Bildirishnoma manzillari |

---

## 3. Ma'lumot hayot sikli

```
[1] OLISH            soatiga 1 marta, anonim HTTP
     S1,S2  api.xt-xarid.uz/rpc,/urpc      -> etl_tenders.py, etl_details.py
     S4,S5  apietender.uzex.uz/api/...     -> etl_uzex.py
          |
          v
[2] SAQLASH          PostgreSQL `xtxarid`, sxema `public`
     tender (3 605) · tender_detail (2 964) · tender_item (11 898)
     tender_document (10 634) — METAMA'LUMOT, fayl emas
     raw_json — manba javobi O'ZGARTIRILMASDAN
          |
          v
[3] QAYTA ISHLASH
     etl_doc_text.py   hujjat matnini ajratadi -> tender_document_text (4 011, 134 MB)
     etl_categorize    kategoriya  ·  etl_lots  lotlar
     etl_requirement   talab ajratish (NAQSH bilan — pul sarflamaydi)
          |
          v
[4] VEKTORLASH       LOKAL model, tashqariga chiqmaydi
     etl_embed.py -> doc_chunk (188 561; 102 174 vektorlangan)
     model: intfloat/multilingual-e5-small (384 o'lcham), EMBED_PROVIDER=local
          |
          v
[5] AI QIDIRUV       gibrid: pgvector (semantik) + tsvector (leksik)
     chat -> 9 ta tool, HAMMASI FAQAT O'QIYDI
     `company_id` tool sxemasida YO'Q — sessiyadan keladi
          |
          v
[6] BILDIRISHNOMA    SMTP (kompaniya sozlamasi) · api.telegram.org
     notify_sent (22)
          |
          v
[7] SAQLASH MUDDATI  -> §7 (hozir: tender ma'lumoti uchun muddat YO'Q)
```

---

## 4. Kelib chiqish (provenance) — o'lchangan

Har yozuv ommaviy manbaga qaytarib bog'lanadi. **`v_manba_qamrov`**
buni o'lchaydi:

| Jadval | Jami | Platformasiz | Manba id siz | Vaqtsiz | URL siz |
|---|---|---|---|---|---|
| `tender` | 3 605 | **0** | **0** | **0** | **0** |
| `tender_document` | 10 634 | **0** | **0** | **0** | **0** |
| `doc_chunk` | 188 561 | — | **0** | **0** | **0** |

**Bo'shliq topildi va to'ldirildi.** Ommaviy havolani qurish naqshi
**faqat frontendda** edi (`frontend/src/format.ts`), ya'ni bazadan
so'ralganda mashina o'qiy oladigan javob yo'q edi — auditor naqshni
qo'lda ko'chirishi kerak bo'lardi. `schema_patch_manba_url.sql`
uni bazaga ko'chirdi:

```sql
SELECT ichki_id, platforma, manbadagi_id, ommaviy_url,
       birinchi_korilgan, oxirgi_olingan
  FROM v_tender_manba WHERE ichki_id = 12345;

SELECT * FROM v_hujjat_manba WHERE tender_id = 12345;
SELECT * FROM v_manba_qamrov;             -- to'liqlik o'lchovi
```

API orqali ham: `GET /manba/tender/{id}`, `GET /manba/qamrov`
(ikkalasi ham kirish talab qiladi).

**Havola naqshi:**
`xt-xarid` → `https://xt-xarid.uz/procedure/{source_id}/core` ·
`uzex` → `https://etender.uzex.uz/lot/{source_id}`

Noma'lum platforma uchun **NULL qaytadi**, taxminiy havola emas.

> **Muhim:** manbadagi **asl `source_id`** ishlatiladi. Ichki
> `tender.id` global (source_id + platforma ofseti) va u manba
> saytida **mavjud emas**.

---

## 5. Tashqi AI/model provayderlari

| Provayder | Nima yuborilardi | Hozirgi holat |
|---|---|---|
| **Anthropic** (`anthropic` SDK) | Chat savoli + qidiruvdan topilgan hujjat bo'laklari; tender tavsifi (go/no-go, moslashtirish); talab matni | **BLOKLANGAN** |
| **Voyage** (embedding) | Bo'lak matni | **BLOKLANGAN** (`EMBED_PROVIDER=local`) |
| **Telegram** (`api.telegram.org`) | `chat_id` + tender kartochkasi matni | Faol (kompaniya yoqsa) |
| **SMTP** (kompaniya serveri) | Email manzili + tender kartochkasi | Faol (kompaniya yoqsa) |
| **HuggingFace** | — | Model **birinchi yuklab olishda**; keyin lokal, matn yuborilmaydi |

### 5.1 Pullik AI standart holatda O'CHIQ — tekshirildi

```
paid_allowed()        -> False
paid_guard('sinov')   -> "BLOKLANGAN: pullik amallar o'chirilgan"
get_client()          -> BLOKLANDI
EMBED_PROVIDER        -> local
.env da AI_PAID_ENABLED  -> UMUMAN YO'Q (standart "0")
```

**Qulf yagona nuqtada.** Har Anthropic chaqiruvi `ai.get_client()`
dan o'tadi, `paid_guard()` esa **kesh tekshiruvidan ham OLDIN**
chaqiriladi — ya'ni bir marta yaratilgan mijoz qulfni chetlab
o'tolmaydi. `api/ai_gonogo.py` va `api/ai_match.py` da `paid_guard`
to'g'ridan-to'g'ri chaqirilmaydi, lekin ular `ai.get_client()` ni
ishlatadi va qulf o'sha yerda ishlaydi (jonli tekshirildi).

`ANTHROPIC_API_KEY` `.env` da **mavjud**, lekin qulf tufayli
ishlatilmaydi. `_tests/paid_guard_test.py` (13/13) buni qo'riqlaydi.

### 5.2 Prompt injection va ijarachi izolyatsiyasi

- 9 ta tool ham **faqat o'qiydi** (manba tahlili bilan tasdiqlangan).
- `company_id` **hech bir tool sxemasida yo'q** — u sessiyadan keladi
  va model o'zgartira olmaydi. Ya'ni hujjat ichidagi injection eng
  ko'pi bilan **o'sha ijarachining o'z ma'lumotini** o'qitadi.
- `_tests/xavfsizlik_test.py` ikkalasini ham tekshiradi.

---

## 6. Iqtibos va manba ishonchi

`chat_message.citations` (245 qator) har javob uchun manba
bo'laklarini saqlaydi. RAG bazaviy o'lchovi
(`_tests/ai_eval/results/rag_eval_baseline.json`): **citation hit
rate = 1.000**, gibrid Recall@8 = 0.705.

> **Halol cheklov:** javob sifati, tool tanlash va gallyutsinatsiya
> **o'lchanmagan** — ular pullik model chaqiruvisiz o'lchab bo'lmaydi.

---

## 7. Saqlash muddati va o'chirish — hozirgi holat

### 7.1 Mavjud avtomatik tozalash (faqat 2 ta)

| Nima | Qoida | Qayerda |
|---|---|---|
| `company_session` | `expires_at < now()` — kirish paytida | `auth.SESSION_CLEAN_SQL` |
| `login_attempt` | **90 kun** (`AUTH_ATTEMPT_KEEP_DAYS`) | `auth.ATTEMPT_CLEAN_SQL` |

### 7.2 Saqlash muddati YO'Q

`tender`, `tender_detail`, `tender_item`, `tender_document`,
`tender_document_text` (134 MB), `doc_chunk` (188 561),
`chat_message`, `notify_sent`, `audit_jurnal` — **hech qaysisida
muddat yo'q**. Ma'lumot cheksiz turadi.

### 7.3 O'chirish — o'lchangan cheklov

`company_account` ga **26 ta FK**, ulardan **25 tasi CASCADE**.
Kaskadsiz yagona: `tender_requirement.reviewed_by`.

**Ijarachini hozir o'chirib BO'LMAYDI.** Empirik tekshirildi
(tranzaksiya qaytarildi, hech narsa o'chirilmadi):

```
DELETE FROM company_account WHERE id = <sinov ijarachisi>;
-->  ОШИБКА: audit_jurnal FAQAT QO'SHILADI: DELETE taqiqlangan
```

Ya'ni audit jurnalining append-only kafolati (huquqiy javobgarlik
uchun kerak) ijarachini o'chirish yo'lini **to'sib qo'yadi**. Ikki
talab bir-biriga qarshi turadi va bu **arxitekturaviy qaror**
talab qiladi — texnik "tuzatish" emas.

### 7.4 Mavjud o'chirish endpointlari (5 ta, obyekt darajasida)

`DELETE /company/documents/{id}` · `/notify/telegram/subscribers/{chat_id}` ·
`/searches/{id}` · `/catalog/{product_id}` · `/chat/sessions/{id}`

**Ijarachi darajasida o'chirish yoki eksport endpointi YO'Q.**

---

## 8. Kelajak uchun kerak bo'ladigan texnik nazoratlar

> Bular **tavsiya**, huquqiy talab emas — qaysi biri kerakligini
> yurist aytadi.

| # | Nazorat | Hozirgi holat | Nima kerak |
|---|---|---|---|
| K1 | **Ijarachini o'chirish** | Mumkin emas (§7.3) | Audit va o'chirish o'rtasidagi qarama-qarshilikni hal qilish: arxivlash + anonimlashtirish yoki audit uchun alohida saqlash |
| K2 | **Saqlash muddati** | Yo'q (§7.2) | Jadval bo'yicha muddat; yopilgan tenderlar uchun arxiv/o'chirish; `close_at` allaqachon bor |
| K3 | **Kirish jurnali (kim nimani KO'RDI)** | `audit_jurnal` faqat **o'zgarishlarni** yozadi | O'qish jurnali — hozir yo'q va bu ochiq aytiladi |
| K4 | **Manba atributsiyasi interfeysda** | Havola bor (`sourceUrl()`) | Yuklab olish va iqtibos yonida ham ko'rsatish |
| K5 | **Opt-out / bloklash** | **Mexanizm yo'q** | Manba yoki subyekt bo'yicha bloklash ro'yxati; `tender_document.holat` ga `bloklangan` qiymati qo'shish mumkin |
| K6 | **Shaxsiy maydonlarni niqoblash** | Yo'q | `director`, `contacts`, hujjat matnidagi email/telefon — indekslashdan oldin niqoblash imkoniyati |
| K7 | **Eksport (ijarachi ma'lumoti)** | Yo'q | Mashina o'qiy oladigan eksport endpointi |
| K8 | **Xom JSON saqlash siyosati** | Cheksiz (§1.1) | `raw_json` eng ko'p shaxsiy ma'lumot saqlaydigan joy — kerakligini qayta ko'rib chiqish |

---

## 9. NOMA'LUM — aniq belgilangan

Quyidagilar **tekshirilmadi** va bu hujjat ular haqida da'vo
qilmaydi:

1. **Manba platformalarining foydalanish shartlari.**
   `xt-xarid.uz` va `uzex.uz` saytlarining shartlari, `robots.txt`
   yoki API shartnomasi **o'qilmagan**. Ma'lumot yig'ish va qayta
   tarqatishga ruxsat berilganmi — **noma'lum**.
2. **`company_details` maydonining ichki tuzilishi.** U `TEXT`
   (JSON emas), 2 960 qatorda to'ldirilgan; ichida nima borligi
   **tahlil qilinmagan**.
3. **`contacts` maydonidagi ma'lumot kimga tegishli.** O'lchandi:
   2 683 qatorda to'ldirilgan, 78 tasida telefonga o'xshash raqam,
   50 tasida email. **Bu jismoniy shaxsniki yoki tashkilotniki —
   aniqlanmagan.**
4. **Hujjat matnlaridagi shaxsiy ma'lumot hajmi.** 441 ta matnda
   email naqshi, 212 tasida telefon naqshi topildi. **Kontekst
   tekshirilmagan.**
5. **Ma'lumot qayerda joylashgan (data residency).** Baza hozir
   ishlab chiquvchi mashinasida (`localhost`). Ishlab chiqarish
   joylashuvi **hal qilinmagan**.
6. **Zaxira nusxalari qayerda saqlanadi va qancha turadi.**
   Repozitoriyada `.dump` fayllari bor (kuzatilmaydi), lekin
   **zaxira siyosati yo'q**.
7. **Subprotsessorlar ro'yxati.** Anthropic va Telegram ishlatilishi
   mumkin (§5), lekin shartnomaviy holat **noma'lum**.
8. **Uzoq muddatli saqlash uchun huquqiy asos.** §7.2 da muddat
   yo'qligi **fakt sifatida** qayd etildi; uning maqbulligi
   baholanmagan.

---

## 10. Tekshirish buyruqlari

Bu hujjatdagi har raqamni qayta o'lchash mumkin:

```sql
-- Kelib chiqish to'liqligi
SELECT * FROM v_manba_qamrov;

-- Bitta tenderning manbaga qaytish yo'li
SELECT * FROM v_tender_manba WHERE ichki_id = <id>;
SELECT * FROM v_hujjat_manba WHERE tender_id = <id>;

-- Saqlangan hajm
SELECT count(*) FROM tender_document_text;
SELECT count(*), count(embedding) FROM doc_chunk;

-- Shaxsiy bo'lishi mumkin bo'lgan maydonlar (SANOQ, qiymat emas)
SELECT count(*) FROM tender_detail WHERE director IS NOT NULL;
SELECT count(*) FROM tender_item  WHERE delivery_address IS NOT NULL;
SELECT count(*) FROM tender
 WHERE raw_json->'detail'->>'contacts' ~* '[a-z0-9._%+-]+@[a-z0-9.-]+';
```

```powershell
# Pullik AI holati
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); from api import ai; print(ai.paid_allowed())"

# ETL chastotasi (Windows)
Get-ScheduledTask | Where-Object { $_.TaskName -like 'TenderAI*' }
```
