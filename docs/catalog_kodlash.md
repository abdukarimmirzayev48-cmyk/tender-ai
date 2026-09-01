# Katalog kodlash — aniqlik/qamrov nuqtasi (Q-3)

**O'lchov: 2026-09-01.**

## Holat

| Ko'rsatkich | Qiymat |
|---|---|
| Mahsulot | 1 797 |
| **Aniq kod (8+)** | **467** (25.99%) |
| Keng kod (5) | 581 |
| **Kodsiz** | **749** (41.68%) |
| Har qanday kod | 58.32% |

## Avtomatik yo'l TUGAGAN

Tahlil **qayta yurgizildi** (585 s, 1 797 mahsulot) va natija
**aynan o'sha** chiqdi — yangi dalil to'planmagan.

```
catalog_kodla.py --qolla --quruq --company 2
  Qo'llash: 0 ta nomzod
```

**Chegarani pasaytirmasdan qo'shimcha kod berib bo'lmaydi.**

## Kodsizlikning O'LCHANGAN sabablari

| Sabab | Mahsulot | Ochiq tender uchrashuvi |
|---|---|---|
| `sozlar_mos_emas` | 502 | **7 441** |
| `nomzodsiz` | 578 | 1 022 |
| `dalil_kam` | 182 | 658 |
| `noaniq` | 21 | 63 |
| `tokensiz` | 13 | 0 |

`sozlar_mos_emas` eng katta biznes qiymatiga ega — lug'atdagi
so'zlar mahsulot nomiga mos kelmayapti.

## Kuchsiz dalil — AVTOMATIK EMAS, NAVBATGA

```
taklif      501
avtomatik   467
navbatga     34   <- kuchsiz dalil
```

34 ta taklifning ishonchi bor, lekin **dalili kam** — ular
`v_catalog_kod_navbat` ga boradi (1 330 element), avtomatik
qo'llanmaydi.

## Bu nuqson EMAS

749 kodsiz — **ataylab tanlangan** aniqlik/qamrov nuqtasi:
dalil yetarli bo'lmaganda kod **qo'yilmaydi**. 15-vazifada
o'lchangan: 383 inson yorlig'iga nisbatan **99.7%** aniqlik.

**Lekin bu hech qayerda tekshirilmasdi.** Endi
`_tests/catalog_kod_test.py` qo'riqlaydi:

- to'rtala chegara **qiymati** (`MIN_EVIDENCE`, `MIN_SHARE`,
  `KUCHSIZ_ISHONCH`, `KUCHSIZ_DALIL`);
- **hisob identiteti** `taklif = avtomatik + navbatga` — kuchsiz
  dalil na qo'llanadi, na yo'qoladi;
- kuchsiz dalilli mahsulotda **avtomatik aniq kod yo'q**;
- navbat **bo'sh emas**;
- sabablar yig'indisi = tahlil qilingan mahsulot soni.

Kimdir chegarani pasaytirsa yoki `NOT t.kuchsiz_dalil` shartini
olib tashlasa, qamrov "o'sardi" va precision **jimgina** yeyilardi.
Endi sinov **darhol yiqiladi**.

## Qolgan yo'l — INSON

Avtomatik yo'l tugagani uchun qamrovni oshirishning yagona
halol yo'li — **navbatni ko'rib chiqish** (`KodNavbat.tsx`,
`v_catalog_kod_navbat`). Bu qatlam **ishlayapti**: 1 048 / 1 427
= **73.4%** (`v_inson_halqasi`).
