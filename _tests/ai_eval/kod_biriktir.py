#!/usr/bin/env python3
"""
KATALOGGA TASNIFLAGICH KODINI BIRIKTIRISH — TUR darajasida.

NEGA TUR DARAJASIDA: katalogda 1797 mahsulot bor, lekin ular
`keywords[2]` bo'yicha 363 turga bo'linadi va eng ko'p 40 turi
katalogning 80% ini qoplaydi. Ya'ni 1797 ta qaror emas, o'nlab.

NEGA QO'LDA XARITA: avtomatik taklif o'lchandi va yetarli emas —
semantik shox hub kodlarni ko'taradi (`26.70` "Штатив для фотокамер"
va `26.60` "Вторичный эталон" deyarli har turda birinchi chiqadi),
prefiks-leksik qidiruv esa xizmat kodlarini tortadi (`33.12`, `52.24`).

KODLAR FOYDALANUVCHI TASDIQLAGAN (2026-08-28 suhbati). Har kodning
haqiqiy pozitsiyalari tekshirilgan:

    26.40  Камера видеонаблюдения, Микрофон, Аудио спикерфон
    26.30  Коммутатор, Мини АТС, Веб-камера, Видеорегистратор
    26.20  Ноутбук, Жесткий диск, Блок питания, Интерактивная панель

RAD ETILGANLAR (qamrovni oshirardi, lekin mos emas):
    26.51  Дефектоскоп, Термопара, Кульман  — o'lchov asboblari
    25.72  Петля мебельная, Шайба            — "Замок" tasodifiy tushgan
    27.32  Кабель силовой                    — kuchlanish kabeli

SHUBHALI TUR KODSIZ QOLADI. "Bilmayman" ni "mos" ga aylantirmaymiz —
kodsiz mahsulot `v_catalog_kodsiz` da ko'rinadi va interfeys buni
ANIQ ko'rsatadi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\ai_eval\\kod_biriktir.py --company 2 --dry-run
    .venv\\Scripts\\python.exe _tests\\ai_eval\\kod_biriktir.py --company 2 --kim kompaniya
    .venv\\Scripts\\python.exe _tests\\ai_eval\\kod_biriktir.py --company 2 --tozala
"""
import argparse
import os
import re
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from api import db, kodlash        # noqa: E402

# Tur nomidagi NAQSH -> kod. Naqsh kichik harfda, `re.search` bilan.
# Tartib MUHIM: birinchi mos kelgan naqsh g'olib, shuning uchun
# aniqrog'i yuqorida turadi.
XARITA = [
    # --- 26.40  video / audio ---
    (r"камер|camera",              "26.40"),   # IP/PTZ/HD/besimli kameralar
    (r"\bnvr\b|\bdvr\b|регистратор", "26.40"), # video yozuvchi
    (r"домофон",                   "26.40"),
    (r"монитор",                   "26.40"),
    (r"акустик|динамик|усилител",  "26.40"),

    # --- 26.30  tarmoq / aloqa ---
    (r"коммутатор|свич|switch",    "26.30"),
    (r"wi-?fi|роутер|маршрутизатор|mesh|мост", "26.30"),
    (r"сетевое оборудование",      "26.30"),

    # --- 26.20  hisoblash / xotira / quvvat ---
    (r"систем[аы] хранени|\bhdd\b|жестк",  "26.20"),
    (r"\bups\b|ибп|источник[иа]? питани|стабилизатор", "26.20"),
    (r"сервер",                    "26.20"),
]

#: Bu turlar ATAYLAB kodsiz qoladi — ular aksessuar yoki noaniq, va
#: kod berilsa butun kod oilasini "mos" qilib yuborardi.
#:   Кронштейн, Шкафы, Кабельная продукция, HDMI кабели, Замок,
#:   Турникеты, Шлагбаумы, Датчики, Прочее, Умные дом, ...
#: Ular `v_catalog_kodsiz` da ko'rinadi.


def kod_uchun(tur: str) -> str | None:
    t = (tur or "").lower()
    for naqsh, kod in XARITA:
        if re.search(naqsh, t):
            return kod
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", type=int, required=True)
    ap.add_argument("--kim", default="", help="Tasdiqlagan foydalanuvchi")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tozala", action="store_true")
    args = ap.parse_args()
    db.init_pool()
    cid = args.company

    if args.tozala:
        n = db.execute_returning(
            "WITH d AS (DELETE FROM catalog_product_code WHERE company_id=%(c)s "
            "RETURNING 1) SELECT count(*) AS n FROM d", {"c": cid})
        print(f"O'chirildi: {(n or {}).get('n', 0)} ta bog'lanish.")
        return 0

    prods = db.query(
        "SELECT id, name, keywords FROM catalog_product WHERE company_id=%(c)s",
        {"c": cid})

    reja: dict[str, list[int]] = {}
    kodsiz = 0
    for p in prods:
        kw = p["keywords"] or []
        tur = kw[1] if len(kw) >= 2 else (kw[0] if kw else p["name"])
        kod = kod_uchun(tur or "") or kod_uchun(p["name"] or "")
        if not kod:
            kodsiz += 1
            continue
        reja.setdefault(kod, []).append(p["id"])

    print(f"Mahsulot: {len(prods)}")
    for kod in sorted(reja):
        d = db.query_one("SELECT name_ru, n_tender_open FROM dim_good_code "
                         "WHERE code=%(k)s", {"k": kod}) or {}
        print(f"  {kod}  {len(reja[kod]):5d} mahsulot  "
              f"-> {d.get('n_tender_open')} ochiq tender  "
              f"({(d.get('name_ru') or '')[:34]})")
    print(f"  kodsiz {kodsiz:5d} mahsulot (ATAYLAB — shubhali turlar)")

    if args.dry_run:
        print("\n--dry-run: bazaga yozilmadi.")
        return 0
    if not (args.kim or "").strip():
        print("\nXATO: --kim majburiy. Tasdiq ODAMSIZ yozilmaydi "
              "(catalog_product_code_tasdiq_odam CHECK).")
        return 2

    yozildi = 0
    for kod, ids in reja.items():
        for pid in ids:
            kodlash.taklif_yoz(cid, pid, [{"code": kod, "skor": None}])
            if kodlash.tasdiqla(cid, pid, kod, kim=args.kim.strip()):
                yozildi += 1
    print(f"\nTasdiqlandi: {yozildi} ta bog'lanish ({args.kim}).")
    print("Holat:", kodlash.holat(cid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
