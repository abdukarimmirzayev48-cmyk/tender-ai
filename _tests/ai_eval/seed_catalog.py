#!/usr/bin/env python3
"""
SINOV KATALOGI — realistik, korpus lug'atiga tayangan.

NEGA KERAK: bazadagi katalogda 2 qator bor ("dori", "Hikvision kamera"),
`stock_qty` va `cost_price` 100% NULL. Bunday katalog bilan
moslashtirish sifatini o'lchab bo'lmaydi — natija katalogning
kambag'alligini o'lchaydi, algoritmni emas.

Bu katalog O'YLAB TOPILMAGAN: pozitsiya nomlari korpusda haqiqatan
uchraydigan tovarlardan olingan (`tender_good.name`), profil esa
`company_profile` dagi "Alfa Med — tibbiy uskunalarni yetkazib berish".

DIQQAT: bu SINOV ma'lumoti. Real broker fayli kelganda o'rnini bo'shatadi.
Prefiks `[SINOV]` — `--tozala` uni aniq topib o'chiradi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\ai_eval\\seed_catalog.py --company 2
    .venv\\Scripts\\python.exe _tests\\ai_eval\\seed_catalog.py --company 2 --tozala
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

BELGI = "[SINOV]"

# (nom, kategoriya, kalit so'zlar, birlik, tannarx UZS, qoldiq)
#
# Tibbiy uskuna va materiallar yetkazib beruvchi — "Alfa Med" profiliga
# mos. Nomlar o'zbek-lotinda (foydalanuvchi shunday yozadi), korpus esa
# rus/kirillda — bu AYNAN o'lchamoqchi bo'lgan holat.
MAHSULOTLAR = [
    ("Tibbiy shkaf",              "tibbiyot",   ["shkaf", "med shkaf"],       "dona",  4_200_000,  12),
    ("Ko'rik kushetkasi",         "tibbiyot",   ["kushetka", "divan"],        "dona",  2_800_000,   8),
    ("Tibbiy stol",               "tibbiyot",   ["stol", "manipulyatsiya"],   "dona",  1_900_000,  15),
    ("Tibbiy shirma",             "tibbiyot",   ["shirma", "parda"],          "dona",    950_000,  20),
    ("Bir martalik shprits",      "tibbiyot",   ["shprits", "igna"],          "dona",      1_200, 50_000),
    ("Steril bint",               "tibbiyot",   ["bint", "bog'lam"],          "dona",      3_500, 12_000),
    ("Tibbiy qo'lqop (nitril)",   "tibbiyot",   ["qo'lqop", "perchatka"],     "quti",     85_000,   900),
    ("Reagent to'plami",          "tibbiyot",   ["reagent", "test-tizim"],    "to'plam", 1_500_000,  40),
    ("Tonometr",                  "tibbiyot",   ["tonometr", "bosim"],        "dona",    420_000,  60),
    ("Puls oksimetr",             "tibbiyot",   ["oksimetr", "puls"],         "dona",    310_000,  45),
    ("Bemor monitori",            "tibbiyot",   ["monitor", "kardiomonitor"], "dona", 28_000_000,   4),
    ("Laboratoriya mikroskopi",   "tibbiyot",   ["mikroskop"],                "dona", 15_000_000,   3),
    ("Sterilizator (avtoklav)",   "tibbiyot",   ["sterilizator", "avtoklav"], "dona",  9_500_000,   5),
    ("Tibbiy tarozi",             "tibbiyot",   ["tarozi", "vaznlar"],        "dona",  1_100_000,  10),
    ("Kislorod konsentratori",    "tibbiyot",   ["kislorod", "konsentrator"], "dona", 12_000_000,   6),
    ("Dezinfeksiya vositasi",     "kimyo",      ["dezinfeksiya", "antiseptik"], "litr",   45_000,  700),
    ("Tibbiy chiqindi idishi",    "tibbiyot",   ["idish", "konteyner"],       "dona",    120_000, 150),
    ("Laboratoriya stoli",        "mebel",      ["stol", "laboratoriya"],     "dona",  3_400_000,   7),
    ("Ofis kreslosi",             "mebel",      ["kreslo", "stul"],           "dona",    780_000,  25),
    ("Metall javon",              "mebel",      ["javon", "shkaf"],           "dona",  1_600_000,  18),
    ("Kompyuter (ish stansiyasi)", "elektronika", ["kompyuter", "monoblok"],  "dona",  8_900_000,  10),
    ("Printer (lazerli)",         "elektronika", ["printer", "MFU"],          "dona",  3_200_000,  14),
    ("Videokuzatuv kamerasi",     "elektronika", ["kamera", "IP kamera"],     "dona",  1_450_000,  30),
    ("Uzluksiz quvvat manbai",    "elektr",     ["UPS", "quvvat manbai"],     "dona",  2_100_000,  16),
    # DIQQAT: nom ANIQ bo'lishi shart. Avval bu qator "Kondensator
    # (tibbiy muzlatgich)" edi va u soxta moslik keltirdi: rasmiy
    # tasniflagichda `28.99.30` = "Конденсатор" (sanoat kondensatori),
    # ya'ni lokomotiv ehtiyot qismlari tenderidagi "Калорифер" ham shu
    # kodga tushardi. Katalog nomi ikki ma'noli bo'lsa, kod ham ikki
    # ma'noli bo'ladi — bu ALGORITM emas, MA'LUMOT xatosi.
    ("Tibbiy muzlatgich",         "mashina",    ["muzlatgich", "sovutgich"], "dona", 18_000_000, 3),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", type=int, required=True)
    ap.add_argument("--tozala", action="store_true",
                    help="Faqat o'chiradi (sinov qatorlarini)")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["XT_DB_DSN"])
    cur = conn.cursor()

    # Sinov qatorlarini har doim avval tozalaymiz — takroriy yurgizish
    # nusxa yasamasin. `catalog_product_code` CASCADE bilan ketadi.
    cur.execute("DELETE FROM catalog_product "
                "WHERE company_id=%s AND name LIKE %s", (args.company, BELGI + "%"))
    ochirildi = cur.rowcount
    if args.tozala:
        conn.commit()
        print(f"O'chirildi: {ochirildi} ta sinov qatori.")
        return 0

    for nom, kat, kalit, birlik, narx, qoldiq in MAHSULOTLAR:
        cur.execute("""
            INSERT INTO catalog_product
                (company_id, name, category_code, keywords, unit,
                 price, cost_price, currency, stock_qty, stock_unit,
                 stock_updated_at, notify)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'UZS', %s, %s, now(), TRUE)""",
            (args.company, f"{BELGI} {nom}", kat, kalit, birlik,
             narx * 1.25, narx, qoldiq, birlik))

    conn.commit()
    cur.execute("SELECT count(*) FROM catalog_product WHERE company_id=%s",
                (args.company,))
    print(f"O'chirildi {ochirildi}, qo'shildi {len(MAHSULOTLAR)}. "
          f"Kompaniya {args.company} katalogi: {cur.fetchone()[0]} qator.")
    print("Keyingi qadam: kod takliflarini yasash va TASDIQLASH.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
