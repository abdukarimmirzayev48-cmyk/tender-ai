#!/usr/bin/env python3
"""
KOD-ASOSLI MOSLASHTIRISH — ikki narsani o'lchaydi.

  1. TAKLIF SIFATI — to'g'ri kod top-N ichida chiqdimi?
     (inson tasdiqlash ekranida uni topa oladimi)

  2. QAMROV O'ZGARISHI — broker nechta tenderni KO'RADI?
     hozirgi substring  vs  tasdiqlangan kodlar

HALOL CHEGARA — bu skript "to'g'rilik" ni O'LCHAMAYDI.
`TASDIQ` jadvalidagi moslik men (domen ko'ruvchisi rolida) qo'lda
belgilaganim, algoritm chiqargani EMAS. Ya'ni bu "algoritm to'g'ri
javob berdi" degani emas, "to'g'ri javob taklif ro'yxatida bor edi"
degani. Haqiqiy to'g'rilikni faqat pilot broker aytadi.

Kod-asosli moslikni `tender_category` oracle'i bilan tekshirib
BO'LMAYDI: `etl_categorize.py` kategoriyani AYNAN `good_code` dan
chiqaradi, ya'ni o'lchov 100% berardi va hech narsani isbotlamasdi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\ai_eval\\kod_eval.py --company 2
"""
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from api import db, kodlash, matching     # noqa: E402

BELGI = "[SINOV]"

# ---------------------------------------------------------------------
# INSON KO'RUVCHISINING QARORI (men, domen ko'ruvchisi rolida).
#
# Har qator: mahsulot nomi -> TO'G'RI kod(lar).
# Kodlar korpusning HAQIQIY mazmuniga qarab tanlandi, nazariy NACE
# ta'rifiga emas. Misol: `21.31` rasman farmatsevtika bo'limida, lekin
# bu korpusda unda "Стол медицинский", "Стол психолога" yotadi — ya'ni
# tibbiy mebel AYNAN o'sha yerda. Xaridorlar shunday kodlagan.
#
# `None` = korpusda mos kod YO'Q (mahsulot bu bozorda uchramaydi).
# Buni yashirmaymiz: kodsiz mahsulot moslashtirishda qatnashmaydi.
# ---------------------------------------------------------------------
TASDIQ = {
    "Tibbiy shkaf":               ["32.50"],          # Шкаф медицинский
    "Ko'rik kushetkasi":          ["32.50"],          # Кушетка для осмотра
    "Tibbiy stol":                ["21.31"],          # Стол медицинский
    "Tibbiy shirma":              ["21.31"],          # Ширма медицинская
    "Bir martalik shprits":       ["21.32"],          # tibbiy sarf materiallari
    "Steril bint":                ["21.32"],
    "Tibbiy qo'lqop (nitril)":    ["21.32"],
    "Reagent to'plami":           ["21.32"],          # Реагенты, тест-системы
    "Tonometr":                   ["32.50"],
    "Puls oksimetr":              ["32.50"],
    "Bemor monitori":             ["32.50"],
    "Laboratoriya mikroskopi":    ["26.70"],          # Optik mikroskop
    "Sterilizator (avtoklav)":    ["32.50"],
    "Tibbiy tarozi":              ["32.50"],
    "Kislorod konsentratori":     ["32.50"],
    "Dezinfeksiya vositasi":      ["20.41"],          # Гель для рук, мыло
    "Tibbiy chiqindi idishi":     ["32.99"],
    "Laboratoriya stoli":         ["31.09"],          # Стол лабораторный
    "Ofis kreslosi":              ["31.01"],          # Кресло офисное
    "Metall javon":               ["31.01"],          # Шкаф
    "Kompyuter (ish stansiyasi)": ["26.20"],          # Персональный компьютер
    "Printer (lazerli)":          ["26.20"],          # orgtexnika shu yerda
    "Videokuzatuv kamerasi":      ["26.40"],          # Камера видеонаблюдения
    "Uzluksiz quvvat manbai":     ["27.32"],          # kabel/quvvat
    "Tibbiy muzlatgich":          ["28.25"],          # sovutish uskunasi
}


def matn_reach(company_id: int) -> int:
    """Faqat MATN yo'li nechta ochiq tenderni ko'radi.

    DIQQAT: `product_matches` endi kodi BOR mahsulot uchun matnga
    TUSHMAYDI, shuning uchun bu yerda kodlar ataylab olib tashlanadi —
    aks holda funksiya yangi mantiqni O'ZI BILAN taqqoslagan bo'lardi.
    """
    prods = db.query(
        "SELECT name, category_code, keywords FROM catalog_product "
        "WHERE company_id=%(c)s AND name LIKE %(n)s", {"c": company_id, "n": BELGI + "%"})
    cands = db.query("""
        SELECT t.id, t.name,
               COALESCE(string_agg(DISTINCT g.name,' '),'') AS goods_blob,
               ARRAY(SELECT code FROM tender_category tc WHERE tc.tender_id=t.id) AS category_codes
        FROM tender t LEFT JOIN tender_good g ON g.tender_id=t.id
        WHERE t.status='open' AND (t.close_at IS NULL OR t.close_at > now())
        GROUP BY t.id""")
    korilgan = set()
    for c in cands:
        for p in prods:
            # `codes=[]` -> matn shoxchasi majburan yoqiladi
            if matching.product_matches(dict(c), dict(p, codes=[])):
                korilgan.add(c["id"])
                break
    return len(korilgan)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", type=int, required=True)
    ap.add_argument("--top", type=int, default=4)
    args = ap.parse_args()
    db.init_pool()
    cid = args.company

    prods = db.query(
        "SELECT id, name, category_code, keywords FROM catalog_product "
        "WHERE company_id=%(c)s AND name LIKE %(n)s ORDER BY name",
        {"c": cid, "n": BELGI + "%"})
    if not prods:
        print("Sinov katalogi yo'q. Avval: seed_catalog.py --company", cid)
        return 1

    # --- 1. TAKLIF SIFATI ---
    print(f"1) TAKLIF SIFATI — to'g'ri kod top-{args.top} ichidami?\n")
    topildi = topilmadi = kodsiz = 0
    for p in prods:
        nom = p["name"][len(BELGI) + 1:]
        kutilgan = TASDIQ.get(nom)
        if not kutilgan:
            kodsiz += 1
            continue
        t = kodlash.takliflar(dict(p), limit=args.top)
        kodlar = [x["code"] for x in t]
        ok = any(k in kodlar for k in kutilgan)
        orin = next((i + 1 for i, k in enumerate(kodlar) if k in kutilgan), None)
        topildi += ok
        topilmadi += (not ok)
        print(f"   {'OK ' if ok else 'YO`Q'} {nom[:31]:<31} kutilgan={','.join(kutilgan):<7} "
              f"o'rin={orin or '-':<3} taklif={','.join(kodlar)}")

    jami = topildi + topilmadi
    print(f"\n   top-{args.top} ichida: {topildi}/{jami} "
          f"({topildi / jami * 100:.0f}%)")

    # --- 2. TASDIQ (inson qarori simulyatsiyasi) ---
    for p in prods:
        nom = p["name"][len(BELGI) + 1:]
        for code in TASDIQ.get(nom) or []:
            if not db.query_one("SELECT 1 AS x FROM dim_good_code WHERE code=%(k)s",
                                {"k": code}):
                print(f"   [!] kod lug'atda yo'q: {code}")
                continue
            kodlash.taklif_yoz(cid, p["id"], [{"code": code, "skor": None}])
            kodlash.tasdiqla(cid, p["id"], code, kim="eval-review")

    h = kodlash.holat(cid)
    print(f"\n2) KODLASH HOLATI: mahsulot={h['mahsulot']} kodlangan={h['kodlangan']} "
          f"kodsiz={h['kodsiz']} qamrov={h['qamrov_pct']}%")

    # --- 3. QAMROV TAQQOSLASHI ---
    eski = matn_reach(cid)
    yangi_rows = kodlash.moslik(cid, only_open=True, limit=1000)
    yangi = len(yangi_rows)
    jami_ochiq = db.scalar(
        "SELECT count(*) FROM tender WHERE status='open' "
        "AND (close_at IS NULL OR close_at > now())")

    print(f"\n3) BROKER NECHTA OCHIQ TENDERNI KO'RADI (jami {jami_ochiq}):")
    print(f"   faqat MATN yo'li    : {eski:>4}  ({eski / jami_ochiq * 100:.1f}%)")
    print(f"   KOD yo'li           : {yangi:>4}  ({yangi / jami_ochiq * 100:.1f}%)")
    print("   (bu ikki raqam TAQQOSLANMAYDI: matn yo'li kodi bor mahsulot")
    print("    uchun umuman ochilmaydi, u faqat kodsizlar uchun zaxira)")

    print("\n   Eng ko'p mos pozitsiyali 5 ta tender:")
    for r in yangi_rows[:5]:
        print(f"     tender {r['tender_id']}: {r['mos_pozitsiya']} pozitsiya, "
              f"kod={','.join(r['kodlar'][:3])}")

    print("\n   DIQQAT: bu QAMROV o'lchovi, TO'G'RILIK emas. Topilgan "
          "tenderlarning\n   haqiqatan mos ekanini faqat pilot broker "
          "tasdiqlay oladi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
