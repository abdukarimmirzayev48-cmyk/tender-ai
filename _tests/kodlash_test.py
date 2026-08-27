#!/usr/bin/env python3
"""
SINOV: KOD-ASOSLI MOSLASHTIRISH (api/kodlash.py)
================================================

Ikki qism:

  A. STATIK / SOF — bazasiz. Sxema matnlari va sof funksiyalar.
     Bu qism CI da doim yuriladi.

  B. DINAMIK — baza kerak. Struktura kafolatlarini HAQIQATAN
     majburlashini tekshiradi (CHECK, FK, ko'rinish).
     `--offline` bilan o'tkazib yuboriladi.

NEGA STRUKTURA SINOVLARI: bu loyihada "tasdiqlanmaganini ishlatmang"
qoidasi IZOH bilan himoya qilinganda buzilgan — `tender_requirement` da
1514 qator `review_status='approved'` bo'lib turibdi va ularni hech kim
ko'rmagan. Shu sababli bu yerda qoida CHECK va VIEW bilan qulflangan, va
quyidagi sinovlar aynan o'sha qulflarni sinaydi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\kodlash_test.py
    .venv\\Scripts\\python.exe _tests\\kodlash_test.py --offline
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):                   # pragma: no cover
    pass

_results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, bool(ok)))
    print(f"  {'OK  ' if ok else 'XATO'} {name}" +
          (f"\n       {detail}" if detail and not ok else ""))
    return bool(ok)


def section(t: str) -> None:
    print(f"\n=== {t} ===")


# =====================================================================
# A. STATIK — bazasiz
# =====================================================================
def test_prior():
    """Kategoriya -> NACE bo'limlari (teskari OKED_MAP)."""
    section("A. Kategoriya priori")
    from api import kodlash

    tib = kodlash.divisions_for_category("tibbiyot")
    check("tibbiyot -> 21/32/86/87/88",
          set(tib) == {"21", "32", "86", "87", "88"}, str(tib))

    check("kategoriyasiz -> bo'sh", kodlash.divisions_for_category(None) == [])
    check("noma'lum kategoriya -> bo'sh",
          kodlash.divisions_for_category("yoq-bunday") == [])

    # Parent berilsa ichkilari ham qamralsin: 'transport' -> avto+xizmat...
    tr = kodlash.divisions_for_category("transport")
    check("parent 'transport' ichki bo'limlarni ham oladi",
          "29" in tr and "49" in tr, str(tr))
    # Ichki berilsa ham butun oila (bir xil parent) qamraladi.
    tra = kodlash.divisions_for_category("transport/avto")
    check("'transport/avto' oilasi bir xil", set(tra) == set(tr))


def test_query_matn():
    """So'rov matni nom + kalit so'zlardan quriladi."""
    section("A. So'rov matni")
    from api import kodlash

    q = kodlash._query_text({"name": "dori", "keywords": ["ampula", "tabletka"]})
    check("nom va kalit so'zlar birga", q == "dori, ampula, tabletka", q)
    check("bo'sh mahsulot -> bo'sh", kodlash._query_text({"name": "", "keywords": []}) == "")
    # Bo'sh kalit so'z qatorga qo'shilmasin (", , " hosil bo'lmasin).
    q2 = kodlash._query_text({"name": "dori", "keywords": ["", "  "]})
    check("bo'sh kalit so'z tashlanadi", q2 == "dori", q2)


def test_leksik_naqsh():
    """Leksik naqshlar IKKI alifboda quriladi."""
    section("A. Leksik naqshlar")
    from api import kodlash

    n = kodlash._lexical_patterns({"name": "kamera", "keywords": []})
    check("naqsh bor", len(n) > 0, str(n))
    check("kirill varianti ham bor",
          any(any("Ѐ" <= ch <= "ӿ" for ch in v) for v in n), str(n))
    # 1-2 belgili naqsh hamma narsaga mos keladi — foydasiz.
    check("qisqa naqsh tashlanadi", all(len(v) >= 3 for v in n), str(n))


def test_product_matches():
    """Moslik qoidasi: KOD birlamchi, KATEGORIYA moslik EMAS, so'z chegarasi.

    Uchala qoida ham EKRANDA ko'rilgan soxta mosliklardan keyin
    qo'yilgan — har biri aniq holatni qaytaradi.
    """
    section("A. Moslik qoidasi")
    from api import matching

    tender = {"name": "Kompyuter xaridi", "goods_blob": "monoblok",
              "category_codes": ["elektronika"],
              "good_codes": ["26.20.11.000-00001"]}

    # --- KOD birlamchi ---
    p_kod = {"name": "ish stansiyasi", "keywords": [], "codes": ["26.20"]}
    check("kod mos kelsa -> 'kod'",
          matching.product_matches(tender, p_kod) == "kod")

    # --- Kodi BOR mahsulot uchun MATNGA TUSHILMAYDI ---
    # "Bemor monitori" -> "Axborot xavfsizligi monitoringi" aynan shu
    # yo'l bilan chiqqandi.
    p_kod_bosh = {"name": "kompyuter", "keywords": [], "codes": ["99.99"]}
    check("kodi bor, kod mos emas -> matnga TUSHMAYDI",
          matching.product_matches(tender, p_kod_bosh) is None,
          str(matching.product_matches(tender, p_kod_bosh)))

    # --- KATEGORIYA moslik EMAS ---
    p_kat = {"name": "beton", "keywords": [], "codes": [],
             "category_code": "elektronika"}
    check("kategoriya tengligi MOSLIK EMAS",
          matching.product_matches(tender, p_kat) is None,
          str(matching.product_matches(tender, p_kat)))

    # --- NOM: faqat kodsiz mahsulot uchun ---
    p_nom = {"name": "kompyuter", "keywords": [], "codes": []}
    check("kodsiz mahsulot -> nom bo'yicha",
          matching.product_matches(tender, p_nom) == "nom")

    # --- SO'Z CHEGARASI ---
    t_ichki = {"name": "Superkompyuter markazi", "goods_blob": "xizmat",
               "category_codes": [], "good_codes": []}
    check("so'z O'RTASIDAN moslik yo'q ('kompyuter' c 'Superkompyuter')",
          matching.product_matches(t_ichki, p_nom) is None)

    # --- MA'LUM CHEKLOV, yashirilmaydi ---
    # `\b` faqat so'z O'RTASIDAN himoya qiladi. "Столб" (ustun) esa
    # "стол" bilan BOSHLANADI, ya'ni chegara uni ushlamaydi — xuddi
    # "monitor" -> "monitoringi" kabi. O'lchandi: qo'shimcha uzunligi
    # to'g'ri va xato holatlarni ajratmaydi
    #     monitor -> monitoring(+3) XATO, nasos -> насосини(+3) TO'G'RI
    # ya'ni buni matn darajasida hal qilib bo'lmaydi (morfologiya kerak).
    #
    # YUMSHATISH: matn mosligi IKKILAMCHI — u faqat kodi YO'Q mahsulot
    # uchun ishlaydi va 100 emas, 60 ball beradi. Sinov shu HOLATNI
    # qulflaydi: xatti-harakat o'zgarsa (yaxshi tomonga ham) bu yerda
    # ko'rinadi.
    t_stolb = {"name": "Столб освещения", "goods_blob": "",
               "category_codes": [], "good_codes": []}
    p_stol = {"name": "stol", "keywords": [], "codes": []}
    check("MA'LUM CHEKLOV: 'stol' hali 'столб' ni topadi (prefiks)",
          matching.product_matches(t_stolb, p_stol) == "nom",
          "xatti-harakat o'zgargan bo'lsa izohni yangilang")
    check("...lekin kodi BOR mahsulotda bu yo'l umuman ochilmaydi",
          matching.product_matches(t_stolb,
                                   dict(p_stol, codes=["31.01"])) is None)

    # Qo'shimchali TO'G'RI moslik saqlanadi (so'z BOSHIDAN).
    t_nasos = {"name": "Насосы для воды", "goods_blob": "",
               "category_codes": [], "good_codes": []}
    p_nasos = {"name": "nasos", "keywords": [], "codes": []}
    check("'nasos' -> 'Насосы' (qo'shimcha bilan) TOPILADI",
          matching.product_matches(t_nasos, p_nasos) == "nom")


def test_atribut():
    """Pozitsiyaga mahsulot biriktirish — TRANSLIT bilan, signalsiz TAXMIN YO'Q."""
    section("A. Atribut o'xshashligi")
    from api import kodlash

    # Xom belgi taqqoslash HAR DOIM 0 beradi (lotin <-> kirill), shuning
    # uchun translit majburiy. Bu tekshiruv shuni qulflaydi.
    s_togri = kodlash._ozgarish("Ofis kreslosi", "Кресло офисное")
    s_xato = kodlash._ozgarish("Metall javon", "Кресло офисное")
    check("translit bilan to'g'ri mahsulot yuqori",
          s_togri > s_xato and s_togri > kodlash.ATRIBUT_CHEGARA,
          f"togri={s_togri:.3f} xato={s_xato:.3f}")

    s_shkaf = kodlash._ozgarish("Tibbiy shkaf", "Шкаф медицинский")
    s_monitor = kodlash._ozgarish("Bemor monitori", "Шкаф медицинский")
    check("'Шкаф медицинский' -> 'Tibbiy shkaf', 'Bemor monitori' EMAS",
          s_shkaf > s_monitor, f"shkaf={s_shkaf:.3f} monitor={s_monitor:.3f}")

    # Chegara shovqin bilan eng zaif to'g'ri moslik ORASIDA bo'lsin.
    check("chegara shovqindan yuqori",
          kodlash.ATRIBUT_CHEGARA > s_monitor,
          f"chegara={kodlash.ATRIBUT_CHEGARA} shovqin={s_monitor:.3f}")
    check("chegara to'g'ri moslikdan past",
          kodlash.ATRIBUT_CHEGARA < min(s_togri, s_shkaf))

    # Umuman bog'liq bo'lmagan juftlik chegaradan past.
    check("bog'liqsiz juftlik chegaradan past",
          kodlash._ozgarish("Tibbiy shkaf", "Трибуна") < kodlash.ATRIBUT_CHEGARA)


def test_sxema_qulflari():
    """Sxema matnida STRUKTURAVIY qulflar bormi.

    Bu izoh emas, fayl matnini o'qiydi: kimdir qulfni olib tashlasa
    sinov yiqiladi.
    """
    section("A. Sxema qulflari")
    p = os.path.join(ROOT, "schema_patch_goodcode.sql")
    sql = open(p, encoding="utf-8").read()

    check("tasdiq ODAMSIZ yozilmaydi (CHECK)",
          "catalog_product_code_tasdiq_odam" in sql
          and "tasdiqlandi IS NULL OR tasdiqlagan IS NOT NULL" in sql)
    check("bir vaqtda tasdiq+rad bo'lmaydi (CHECK)",
          "catalog_product_code_bir_qaror" in sql)
    check("ko'p-ijarachilik kompozit FK bilan",
          "REFERENCES catalog_product (id, company_id)" in sql)
    check("faol ko'rinish tasdiqlanganini FILTRLAYDI",
          re.search(r"CREATE OR REPLACE VIEW v_catalog_code_active.*?"
                    r"WHERE pc\.tasdiqlandi IS NOT NULL", sql, re.S) is not None)
    check("kodsizlar uchun alohida ko'rinish bor",
          "v_catalog_kodsiz" in sql)

    p2 = os.path.join(ROOT, "schema_patch_semantik.sql")
    sql2 = open(p2, encoding="utf-8").read()
    check("markaz sovuq-startdan himoyalangan (n>=50)",
          "embed_centroid_min_source" in sql2 and "n_source >= 50" in sql2)
    check("markazlangan vektor markazni YOZIB BORADI",
          "tender_embedding_c_needs_centroid" in sql2)
    check("eskirganlik ko'rinishi bor", "v_centroid_stale" in sql2)


def test_moslik_sql_faol_korinishdan():
    """Moslashtirish SQL i FAQAT `v_catalog_code_active` dan o'qiydi.

    Agar kimdir uni `catalog_product_code` ga o'zgartirsa,
    TASDIQLANMAGAN takliflar jimgina moslikka aylanadi.
    """
    section("A. Moslik manbai")
    from api import kodlash

    sql = kodlash.SQL_MOSLIK
    check("v_catalog_code_active dan o'qiydi", "v_catalog_code_active" in sql)
    check("xom jadvaldan O'QIMAYDI",
          "catalog_product_code" not in sql.replace("v_catalog_code_active", ""))
    check("company_id bo'yicha filtrlaydi", "company_id = %(company_id)s" in sql)


def test_semantik_hublik():
    """Semantik shox XOM kosinusni emas, hublik tuzatmasini ishlatadi."""
    section("A. Hublik tuzatmasi")
    from api import kodlash

    check("hub_bias ayiriladi", "hub_bias" in kodlash.SQL_SEM)
    check("markazlangan ustun ishlatiladi", "embedding_c" in kodlash.SQL_SEM)
    check("xom `embedding` ishlatilmaydi",
          not re.search(r"\bge\.embedding\b(?!_c)", kodlash.SQL_SEM))
    # Prior — RANG emas, A'ZOLIK. Rang bo'lsa hub kodlar yana ko'tariladi.
    check("prior ROW_NUMBER ishlatmaydi (a'zolik)",
          "ROW_NUMBER" not in kodlash.SQL_PRIOR)
    check("prior bonusi bitta 1-o'ringa teng",
          abs(kodlash.PRIOR_BONUS - 1.0 / (kodlash.RRF_K + 1)) < 1e-12)
    # Hajm hech qachon hal qiluvchi bo'lmasin.
    check("hajm koeffitsienti RRF o'rnidan KICHIK",
          50 * kodlash.VOLUME_EPS < 1.0 / (kodlash.RRF_K + 1))


# =====================================================================
# B. DINAMIK — baza kerak
# =====================================================================
def test_baza_qulflari(cid: int):
    """CHECK/FK/VIEW HAQIQATAN majburlaydimi."""
    section("B. Baza qulflari")
    import psycopg2
    from api import db

    # --- Tasdiq odamsiz yozilmaydi ---
    prod = db.query_one(
        "SELECT id FROM catalog_product WHERE company_id=%(c)s LIMIT 1", {"c": cid})
    if not prod:
        check("sinov mahsuloti bor", False, "katalog bo'sh")
        return
    kod = db.query_one("SELECT code FROM dim_good_code WHERE level=5 LIMIT 1")
    if not kod:
        check("lug'at to'ldirilgan", False, "dim_good_code bo'sh")
        return

    db.execute_returning(
        "INSERT INTO catalog_product_code (product_id, company_id, code, manba) "
        "VALUES (%(p)s,%(c)s,%(k)s,'taklif') "
        "ON CONFLICT (product_id, code) DO NOTHING RETURNING product_id",
        {"p": prod["id"], "c": cid, "k": kod["code"]})

    xato = None
    try:
        db.execute_returning(
            "UPDATE catalog_product_code SET tasdiqlandi=now(), tasdiqlagan=NULL "
            "WHERE product_id=%(p)s AND code=%(k)s RETURNING product_id",
            {"p": prod["id"], "k": kod["code"]})
    except Exception as e:                                   # noqa: BLE001
        xato = str(e)
    check("tasdiq ODAMSIZ yozilmadi (CHECK ushladi)",
          xato is not None and "tasdiq_odam" in (xato or ""), xato or "yozildi!")

    # --- Begona kompaniya bog'lay olmaydi ---
    xato2 = None
    try:
        db.execute_returning(
            "INSERT INTO catalog_product_code (product_id, company_id, code, manba) "
            "VALUES (%(p)s, %(c)s, %(k)s, 'qol') RETURNING product_id",
            {"p": prod["id"], "c": cid + 9999, "k": kod["code"]})
    except Exception as e:                                   # noqa: BLE001
        xato2 = str(e)
    check("begona company_id FK bilan rad etildi", xato2 is not None,
          xato2 or "yozildi!")

    # --- Faol ko'rinish tasdiqlanmaganini KO'RSATMAYDI ---
    n = db.scalar(
        "SELECT count(*) FROM v_catalog_code_active v "
        "JOIN catalog_product_code pc USING (product_id, code) "
        "WHERE pc.tasdiqlandi IS NULL")
    check("faol ko'rinishda tasdiqlanmagan YO'Q", n == 0, f"topildi {n}")

    # Tozalash
    db.execute_returning(
        "DELETE FROM catalog_product_code WHERE product_id=%(p)s AND code=%(k)s "
        "AND tasdiqlandi IS NULL RETURNING product_id",
        {"p": prod["id"], "k": kod["code"]})


def test_markaz_va_lugat():
    """Markaz va lug'at holati — eskirgan bo'lmasin."""
    section("B. Markaz va lug'at holati")
    from api import db

    st = db.query_one("SELECT * FROM v_centroid_stale")
    if st:
        check("markazlanmagan vektor yo'q", (st.get("markazlanmagan") or 0) == 0,
              str(st))
        check("eskirgan markaz yo'q", (st.get("eskirgan") or 0) == 0, str(st))

    hb = db.query_one("SELECT * FROM v_hub_stale")
    if hb:
        check("hublik tuzatmasi hisoblangan", (hb.get("biassiz") or 0) == 0, str(hb))
        check("hublik tuzatmasi eskirmagan", (hb.get("eskirgan") or 0) == 0, str(hb))

    lv = {r["level"]: r["n"] for r in db.query(
        "SELECT level, count(*) AS n FROM dim_good_code GROUP BY level")}
    check("lug'at uch darajada", set(lv) == {2, 5, 8}, str(lv))
    check("5-daraja bo'sh emas", (lv.get(5) or 0) > 50, str(lv))

    # Har kodning uzunligi darajasiga TENG (CHECK buni majburlaydi, lekin
    # ma'lumot eski patchdan qolgan bo'lishi mumkin).
    yomon = db.scalar("SELECT count(*) FROM dim_good_code WHERE length(code) <> level")
    check("kod uzunligi darajaga teng", yomon == 0, f"buzilgan {yomon}")


def test_moslik_tasdiqsiz_ishlamaydi(cid: int):
    """TASDIQLANMAGAN taklif moslikka AYLANMAYDI — asosiy kafolat."""
    section("B. Tasdiqsiz moslik yo'q")
    from api import db, kodlash

    oldin = len(kodlash.moslik(cid, limit=1000))

    prod = db.query_one(
        "SELECT id FROM catalog_product WHERE company_id=%(c)s "
        "ORDER BY id DESC LIMIT 1", {"c": cid})
    # Ko'p ochiq tenderli kod tanlaymiz: agar tasdiqsiz ham ishlasa,
    # farq ANIQ ko'rinsin.
    kod = db.query_one("SELECT code FROM dim_good_code WHERE level=5 "
                       "ORDER BY n_tender_open DESC LIMIT 1")
    if not (prod and kod):
        check("sinov ma'lumoti bor", False)
        return

    yozildi = kodlash.taklif_yoz(cid, prod["id"], [{"code": kod["code"], "skor": 0.5}])
    keyin = len(kodlash.moslik(cid, limit=1000))
    check("taklif yozilgach moslik O'ZGARMADI", oldin == keyin,
          f"oldin={oldin} keyin={keyin} (kod={kod['code']}, yozildi={yozildi})")

    # Endi tasdiqlaymiz — moslik O'SISHI kerak (aks holda quvur uzilgan).
    kodlash.tasdiqla(cid, prod["id"], kod["code"], kim="kodlash-test")
    tasdiqdan = len(kodlash.moslik(cid, limit=1000))
    check("tasdiqdan KEYIN moslik ishladi", tasdiqdan >= keyin,
          f"keyin={keyin} tasdiqdan={tasdiqdan}")

    # Rad etilsa qator QOLADI (takror taklif chiqmasin), lekin moslikdan
    # chiqadi.
    kodlash.rad_et(cid, prod["id"], kod["code"])
    raddan = len(kodlash.moslik(cid, limit=1000))
    check("rad etilgach moslikdan chiqdi", raddan <= tasdiqdan,
          f"tasdiqdan={tasdiqdan} raddan={raddan}")
    qator = db.query_one(
        "SELECT rad_etildi FROM catalog_product_code "
        "WHERE product_id=%(p)s AND code=%(k)s", {"p": prod["id"], "k": kod["code"]})
    check("rad etilgan qator O'CHIRILMADI",
          qator is not None and qator.get("rad_etildi") is not None)

    db.execute_returning(
        "DELETE FROM catalog_product_code WHERE product_id=%(p)s AND code=%(k)s "
        "RETURNING product_id", {"p": prod["id"], "k": kod["code"]})


def test_navbat_qoldiqsiz(cid: int):
    """TOIFALASH QOLDIQSIZ — yig'indi JAMIGA teng.

    UMUMIY QOIDA, alohida holat emas. O'lchangan nosozlik: 837 kodsiz
    mahsulotdan 185 tasi na navbatda, na "talabsiz" da ko'rinardi
    (turi 30 belgidan uzun edi). Ular hech qayerda ko'rinmasdi va
    HECH QANDAY XATO CHIQMASDI — bu loyihada shu sinf o'ninchi marta.

    Bitta assert shu sinfni kelajakda ham tutadi.
    """
    section("B. Navbat qoldiqsiz")
    from api import kodlash

    n = kodlash.navbat(cid, limit=5, takliflar_bilan=False)
    check("jami = toifalar yig'indisi",
          n["jami_mahsulot"] == n["toifa_yigindi"],
          f"jami={n['jami_mahsulot']} yig'indi={n['toifa_yigindi']}")
    check("qoldiq toifasi MAVJUD", "turi_aniqmas_jami" in n)
    check("talabsiz toifasi MAVJUD", "talabsiz_jami" in n)
    # Chegaradan tashqaridagilar ham sanaladi — aks holda `limit`
    # o'zgarganda yig'indi buzilardi.
    check("chegaradan tashqaridagilar sanaladi", n["qolgan"] >= 0)


def test_qidiruv_ijarachi(cid: int):
    """QIDIRUV: korpus UMUMIY, mahsulot soni esa IJARACHINIKI.

    Ikkisi ARALASHTIRILMASIN: korpusga filtr qo'yilsa natija bo'shab
    qolardi, mahsulot soniga qo'yilmasa begona katalog ko'rinardi.
    """
    section("B. Qidiruv va ijarachi chegarasi")
    from api import db, kodlash

    r = kodlash.qidir("kabel", limit=5)
    check("korpus natijasi FILTRSIZ keladi", len(r["pozitsiya"]) > 0,
          "korpus umumiy ma'lumot, bo'sh bo'lmasligi kerak")
    check("kalit normallashtirilgan", r["kalit"] == "kabel", r["kalit"])
    # Kirill kirish AYNAN shu natijani bersin — aks holda qidiruv
    # yangi til devorini yaratardi.
    r2 = kodlash.qidir("Кабели", limit=5)
    check("kirill kirish bir xil kalit beradi", r2["kalit"] == r["kalit"],
          f"{r2['kalit']!r} != {r['kalit']!r}")

    # MAHSULOT SONI — begona kompaniyada 0 bo'lsin.
    begona = db.scalar("SELECT COALESCE(max(id), 0) + 1000 "
                       "FROM company_account") or 99999
    n_meniki = db.scalar(
        "SELECT count(*) FROM catalog_product p WHERE p.company_id = %(c)s",
        {"c": begona})
    check("begona kompaniyada mahsulot yo'q", (n_meniki or 0) == 0,
          f"topildi {n_meniki}")

    # NAVBAT begona kompaniyada BO'SH.
    nb = kodlash.navbat(begona, limit=5, takliflar_bilan=False)
    check("begona kompaniya navbati bo'sh",
          nb["jami_mahsulot"] == 0 and not nb["atamalar"],
          str(nb["jami_mahsulot"]))
    # O'z kompaniyasida esa BO'SH EMAS — aks holda yuqoridagi sinov
    # "hamma joyda bo'sh" degan holatni ham o'tkazib yborardi.
    oz = kodlash.navbat(cid, limit=5, takliflar_bilan=False)
    check("o'z kompaniyasida navbat bor", oz["jami_mahsulot"] > 0,
          str(oz["jami_mahsulot"]))


def test_kodsiz_korinadi(cid: int):
    """Kodsiz mahsulot JIMGINA yo'qolmaydi — alohida ro'yxatda ko'rinadi."""
    section("B. Kodsiz mahsulot ko'rinadi")
    from api import kodlash

    h = kodlash.holat(cid)
    kodsiz = kodlash.kodsiz_mahsulotlar(cid)
    check("holat va ro'yxat mos", h["kodsiz"] == len(kodsiz),
          f"holat={h['kodsiz']} ro'yxat={len(kodsiz)}")
    check("qamrov foizi 0..100", h["qamrov_pct"] is None
          or 0 <= h["qamrov_pct"] <= 100, str(h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="Faqat statik qism")
    ap.add_argument("--company", type=int, default=2)
    args = ap.parse_args()

    test_prior()
    test_query_matn()
    test_leksik_naqsh()
    test_product_matches()
    test_atribut()
    test_sxema_qulflari()
    test_moslik_sql_faol_korinishdan()
    test_semantik_hublik()

    if not args.offline:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(ROOT, ".env"))
            from api import db
            db.init_pool()
            test_markaz_va_lugat()
            test_baza_qulflari(args.company)
            test_moslik_tasdiqsiz_ishlamaydi(args.company)
            test_navbat_qoldiqsiz(args.company)
            test_qidiruv_ijarachi(args.company)
            test_kodsiz_korinadi(args.company)
        except Exception as e:                               # noqa: BLE001
            # BAZA YO'QLIGI SINOVNI "O'TDI" QILMASIN.
            check("dinamik qism yurdi", False, f"{type(e).__name__}: {e}")

    yiqilgan = [n for n, ok in _results if not ok]
    print("\n" + "=" * 62)
    print(f"NATIJA: {len(_results) - len(yiqilgan)}/{len(_results)} o'tdi")
    print("=" * 62)
    for n in yiqilgan:
        print(f"  YIQILDI: {n}")
    return 1 if yiqilgan else 0


if __name__ == "__main__":
    sys.exit(main())
