# Tender-AI → ERP — BOSQICHLAR

Har bosqich: **maqsad → nima qilinadi → nima QILINMAYDI → qabul mezonlari**.
Bosqich yakunlanmaguncha keyingisi boshlanmaydi; har bosqich o'z
`schema_patch_erp_*.sql` + integratsiya hujjati bilan keladi.

---

## 0-bosqich — Poydevor (1-bosqich bilan birga, alohida sanalmaydi)

- `erp` sxemasi, `erp.broker`, `erp.client_company` (minimal: `id, name`).
- `api/erp/` paketi, `/erp` prefiksi, `frontend/src/components/erp/`.
- Sinov skeleti `_tests/erp_test.py` (TestClient, `ZZTEST ` prefiksli
  yozuvlar bilan tozalanadigan — `import.md` uslubi).

---

## 1-bosqich — Tenderni "ishga olish" + Opportunity pipeline  ◀ HOZIR

### Maqsad

Tender ro'yxatdan kompaniyaning ichki ish kartasiga aylanadi; rahbar kim
nima ustida ishlayotganini bir ekranda ko'radi.

### Nima qilinadi

| # | Ish | Fayl |
|---|---|---|
| 1.1 | Sxema: `erp.opportunity`, `erp.opportunity_history`, `erp.broker`, `erp.client_company` | `schema_patch_erp_1.sql` |
| 1.2 | API: opportunity CRUD (delete yo'q), status o'tish, broker/mijoz ro'yxati, stats | `api/erp/opportunity.py`, `api/erp/stats.py` |
| 1.3 | "Ishga olish" tugmasi + forma (broker, mijoz, ustuvorlik, ehtimol, izoh, keyingi vazifa) | `TenderDrawer.jsx` + `erp/TakeTenderDialog.jsx` |
| 1.4 | Bo'lim "Ishdagi tenderlar": Kanban + jadval, filtr (broker, mijoz, status), qidiruv | `erp/OpportunityBoard.jsx`, `erp/OpportunityTable.jsx` |
| 1.5 | Opportunity kartasi: snapshot + xodim maydonlari tahriri + status + tarix + tabda mavjud panellar | `erp/OpportunityCard.jsx` |
| 1.6 | Rahbar paneli: status bo'yicha soni/summa, broker bo'yicha, yaqin deadline'lar | `erp/OpportunityStats.jsx` |
| 1.7 | Sinov | `_tests/erp_test.py` |

Broker va mijoz 1-bosqichda **oddiy ro'yxat** sifatida boshqariladi
(qo'shish/nomini tahrirlash) — alohida sahifasiz, "Ishga olish"
formasidagi "+ yangi" tugmasi bilan.

### Nima QILINMAYDI

Buxgalteriya, ombor, HR, AI hujjat tayyorlash, shartnoma, yetkazib berish,
murakkab scoring, bildirishnoma, fayl yuklash, login/rollar, opportunity
o'chirish, status ketma-ketligini majburlash.

### Qabul mezonlari

- [ ] Tender panelida "Ishga olish" tugmasi bor; bosilganda forma ochiladi;
      saqlangach panelda "Ishga olingan" nishoni va "Kartaga o'tish" havolasi.
- [ ] Bir tender bir mijoz uchun ikkinchi marta ishga olinmaydi
      (409 + mavjud kartaga havola).
- [ ] Kartada tenderning 9 ta maydoni avtomatik to'lgan, hujjatlar ro'yxati
      ko'rinadi (jonli, `tender_id` orqali).
- [ ] Kanbanda 9 ta ustun; kartani sudrab ko'chirish statusni o'zgartiradi;
      yangilangach joyida qoladi.
- [ ] Jadval: Tender · Mijoz · Mas'ul · Deadline · Summa · Status; ustun
      bo'yicha saralash; broker/mijoz/status filtri.
- [ ] Yakuniy statusdan qaytarish izohsiz rad etiladi (400).
- [ ] Har status o'zgarishi kartadagi "Tarix" bo'limida ko'rinadi.
- [ ] Rahbar paneli: qancha ishga olingan / topshirilgan / yutilgan /
      yutqazilgan / rad etilgan — soni va summasi; 7 kun ichidagi
      deadline'lar ro'yxati.
- [ ] `_tests/erp_test.py` o'tadi, bazani o'zidan keyin tozalaydi.
- [ ] `public.*` jadvallariga hech qanday yozuv qo'shilmagan/o'zgarmagan
      (sinovda tekshiriladi).

---

## 2-bosqich — Mijoz korxonalar bazasi va korxona passporti

### Maqsad

Broker qaysi korxona nomidan qatnashayotganini to'liq biladi; tender
cheklisti (P0-8) **mijoz** hujjatlariga qarab ishlaydi.

### Nima qilinadi

- `erp.client_company` kengayadi: INN, OKED, yuridik/faktik manzil,
  bank rekvizitlari, rahbar, aloqa shaxsi, telefon/email, MCHJ/AJ turi,
  soliq rejimi, izoh.
- `erp.client_contact` — bir korxonada bir nechta aloqa shaxsi.
- `erp.client_document` — mijoz hujjatlari (guvohnoma, litsenziya,
  sertifikat...) — `company_document` (P0-8) bilan **bir xil** `doc_type`
  kanonik ro'yxati (`compliance.DOC_TYPES`) ishlatiladi.
- **Cheklist integratsiyasi:** `GET /tenders/{id}/compliance?client_id=N`
  — `compliance.check()` ga ixtiyoriy `client_id` parametri; berilsa
  `company_document` o'rniga `erp.client_document` bilan solishtiradi.
  Bu `api/compliance.py` ga **kichik** o'zgarish (manba jadvalini tanlash),
  qoidalar o'zgarmaydi. Opportunity kartasi cheklistni doim o'z `client_id`
  bilan chaqiradi.
- Mijozlar sahifasi: ro'yxat, passport kartasi, hujjatlari, shu mijozning
  barcha opportunity'lari va natijalari (yutish foizi).
- Mijoz bo'yicha hisobot `GET /erp/stats` ga qo'shiladi.

### Nima QILINMAYDI

Shartnoma, to'lov, mijoz kirishi (portal), fayl yuklash (hali `file_ref`
havola), mijozga avtomatik xabar.

### Qabul mezonlari

- [ ] Mijoz kartasida passport to'liq; INN bo'yicha takror rad etiladi.
- [ ] Opportunity kartasidagi cheklist mijoz hujjatlariga qarab "bor/yo'q/
      muddati o'tgan" ko'rsatadi.
- [ ] Mijoz sahifasida uning tenderlari tarixi va yutish foizi.
- [ ] `company_profile`/`company_document` (broker kompaniyasining o'zi)
      avvalgidek ishlaydi — mijoz bazasi uning o'rnini bosmaydi.

---

## 3-bosqich — Vazifalar, eslatmalar va bildirishnoma

- `erp.opportunity_task` — keyingi vazifa bitta maydondan ro'yxatga
  aylanadi (mas'ul, muddat, bajarildi).
- Deadline/vazifa eslatmalari — `api/erp/remind.py` skripti, `run_etl.py`
  post-qadami sifatida (`etl.md` 4-bo'lim uslubi); transport sifatida
  mavjud `api/telegram.py` va SMTP sozlamasi, **platforma tilida**
  (`api/i18n.py`).
- Broker bo'yicha "mening bugungi ishlarim" ko'rinishi.
- Yutish/yutqazish sabablari lug'ati (`lost_reason`) — keyingi tahlil uchun.

---

## 4-bosqich — Taklif va topshirish

- Taklif paketi: narx hisobi (P0-7) natijasi + cheklist holati + hujjatlar
  ro'yxati bir joyda, "Topshirildi" statusiga o'tishda **tekshiruv**
  (cheklistda `blocking > 0` bo'lsa ogohlantirish — taqiq emas).
- Topshirilgan taklif versiyasi muzlatiladi (`erp.submission` — narx,
  sana, kim topshirdi, qaysi hujjatlar bilan).
- Manbadan natija kuzatish (agar platforma ochiq bersa) — `won/lost`
  ni taklif qilish, **avtomatik o'zgartirmaslik**.

---

## 5-bosqich va undan keyin — ERP "og'ir" modullari

Shartnoma va uning bosqichlari, yetkazib berish, hisob-faktura va to'lovlar,
ombor harakati (P0-6 qoldig'i bilan bog'lanadi), HR (brokerlar KPI).
**Shu bosqichga kelganda `erp_arxitektura.md` 1-bo'limdagi "qayta ko'rish"
shartlari tekshiriladi** — ehtimol ajratish vaqti keladi.

---

## Har bosqich uchun umumiy qoida

1. Bosqich boshida `schema_patch_erp_N.sql` (idempotent) va
   `erp_integratsiya_N.md` yoziladi.
2. `public.*` ga yozuv yo'q; mavjud modullarga o'zgarish faqat
   **ixtiyoriy parametr** ko'rinishida (2-bosqichdagi `client_id` kabi) —
   parametr berilmasa eski xatti-harakat saqlanadi.
3. Har bosqich o'z sinovi bilan yopiladi; sinov bazani tozalaydi.
4. "Nima QILINMAYDI" ro'yxati — majburiy. U bosqich o'rtasida kengayishni
   to'xtatadi.
