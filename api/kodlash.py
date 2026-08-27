"""
KODLASH — katalog mahsuloti <-> rasmiy tasniflagich (`good_code`)
=================================================================

NEGA BU MODUL BOR (o'lchangan, taxmin emas)
-------------------------------------------
Matn bo'yicha moslashtirish TILGA BOG'LIQ va shu sababli yiqiladi. Korpus
rus va o'zbek-kirillda, foydalanuvchi o'zbek-lotinda yozadi:

    "dori"                              -> Сосуд Дьюара, Чай зеленый     XATO
    "дори"  (transliteratsiya)          -> Урна                          XATO
    "лекарственные средства препараты"  -> 21.40, 86.23                  TO'G'RI

Ya'ni yetishmayotgani boshqa ALIFBO emas (`translit.py` buni yopmaydi),
boshqa LUG'AT. Ayni paytda `tender_good.good_code` qamrovi 100% (1880/1880
ochiq pozitsiya) va kod TILGA BOG'LIQ EMAS:

    substring "dori"       ->  6 ochiq tender
    gibrid semantik        ->  6 ochiq tender
    good_code LIKE '21%'   -> 63 ochiq tender, 124 pozitsiya

DIZAYN
------
Semantika HAR QIDIRUVDA emas, mahsulot qo'shilganda BIR MARTA ishlaydi:

    mahsulot --(taklif: 3 signal)--> nomzod kodlar --(INSON)--> tasdiqlangan
                                                                     |
    tender pozitsiyasi --(good_code)--------------------------------(join)--> moslik

Tasdiqlangandan keyin moslashtirish — indeksli `LIKE` join. Model
chaqirilmaydi, token sarflanmaydi, til farqi yo'q.

TASDIQ MAJBURIY
---------------
`catalog_product_code.tasdiqlandi IS NULL` bo'lgan qator moslashtirishda
ISHLATILMAYDI va buni struktura ta'minlaydi (`v_catalog_code_active`
ko'rinishi + `CHECK (tasdiqlandi IS NULL OR tasdiqlagan IS NOT NULL)`).

Sabab tarixiy: bu loyihada `tender_requirement` da 1514 qator
`review_status='approved'` bo'lib turibdi va ularni HECH KIM ko'rmagan —
kodning o'zi tasdiqlagan. Natijada `v_review_disagreement` "0%
kelishmovchilik" ko'rsatadi, ya'ni asbob o'zini o'lchaydi. Bu yerda o'sha
xato takrorlanmaydi.

NIMA O'LCHANMAGAN (halol qoldiriladi)
-------------------------------------
Kod-asosli moslikni `tender_category` oracle'i bilan tekshirib BO'LMAYDI:
`etl_categorize.py` kategoriyani AYNAN `good_code` dan chiqaradi
(good_code -> NACE bo'limi -> kategoriya). Ya'ni o'lchov 100% berardi va
hech narsani isbotlamasdi. Yagona haqiqiy tekshiruv — inson tasdig'i,
ya'ni `v_code_review` navbati.

Manba ma'lumoti ham mukammal emas: 21.31 (farmatsevtika) kodi ostida
"Стол психолога" uchraydi — xaridor pozitsiyani noto'g'ri kodlagan.
Inson tasdig'i aynan shuni ushlaydi.
"""
from typing import Any, Dict, List, Optional, Sequence

from api import categories as C
from api import db, translit

#: Taklif uchun ishlatiladigan daraja. 2 juda keng (butun NACE bo'limi),
#: 8 juda tor (823 ta sinf, ko'pi bitta tenderda uchraydi). 5 — guruh.
DEFAULT_LEVEL = 5

#: RRF birlashtirish konstantasi. Klassik qiymat; kichikroq bo'lsa
#: birinchi o'rinlar haddan tashqari ustunlik qiladi.
RRF_K = 60

#: Kategoriya oilasiga a'zolik bonusi. Qiymat ATAYLAB `1/(RRF_K+1)` ga
#: teng — ya'ni "bitta signal bo'yicha 1-o'rin" ga arziydi. Undan katta
#: bo'lsa prior hamma narsani hal qilardi (kategoriya xato qo'yilgan
#: mahsulot hech qachon to'g'ri kod topmasdi); kichik bo'lsa begona
#: oiladagi semantik shovqin o'tib ketardi.
PRIOR_BONUS = 1.0 / (RRF_K + 1)

#: Hajm koeffitsienti — faqat TENGLARNI ajratadi. 50 ta ochiq tenderli
#: kod ham 0.0005 oladi, ya'ni bitta RRF o'rnining (0.016) 3% i.
#: Hech qachon hal qiluvchi emas — bu ataylab.
VOLUME_EPS = 1e-5

#: Bitta mahsulot uchun ko'rsatiladigan taklif soni. Inson 30 soniyada
#: ko'rib chiqadigan miqdor — undan ko'pi tasdiqni "keyingi safar" ga
#: suradi va navbat o'sib ketadi.
DEFAULT_LIMIT = 8


# ---------------------------------------------------------------------------
# 1. KATEGORIYA PRIORI — bepul va tilga bog'liq emas
# ---------------------------------------------------------------------------
def divisions_for_category(category_code: Optional[str]) -> List[str]:
    """Ichki kategoriya kodi -> NACE bo'limlari (`OKED_MAP` ning teskarisi).

    'tibbiyot' -> ['21', '32', '86', '87', '88']

    NEGA KUCHLI SIGNAL: bu bog'lanish deterministik va TILGA BOG'LIQ EMAS.
    Mahsulotda kategoriya belgilangan bo'lsa, nomzodlar darhol to'g'ri
    oilaga qisqaradi — semantik model umuman kerak bo'lmasligi mumkin.

    Parent kategoriya berilsa ichkilari ham qamraladi
    ('transport' -> 'transport/avto' bo'limlari ham).
    """
    if not category_code:
        return []
    parent = C.parent_of(category_code)
    out = [d for d, c in C.OKED_MAP.items()
           if c == category_code or C.parent_of(c) == parent]
    return sorted(set(out))


def _query_text(product: Dict[str, Any]) -> str:
    """Mahsulotdan qidiruv matni.

    Nom + kalit so'zlar BIRGA beriladi: o'lchandi, bitta so'z ("dori")
    e5 uchun juda zaif signal — korpusdagi eng yaqin 6 natija bir-biridan
    0.007 ga farq qilardi.
    """
    qismlar = [(product.get("name") or "").strip()]
    qismlar += [k.strip() for k in (product.get("keywords") or []) if k and k.strip()]
    return ", ".join(q for q in qismlar if q)


def _lexical_patterns(product: Dict[str, Any]) -> List[str]:
    """Leksik qidiruv naqshlari — HAR IKKI alifboda.

    `translit.variants()` lotin<->kirill o'qishlarini beradi. Bu lug'at
    nomlari kirillda bo'lgani uchun zarur, LEKIN yetarli emas: o'lchandi,
    "дори" ham noto'g'ri kod topadi. Shuning uchun leksik — uch signaldan
    faqat BITTASI.
    """
    out: List[str] = []
    for term in [product.get("name")] + list(product.get("keywords") or []):
        if term and term.strip():
            out.extend(translit.variants(term))
    seen, res = set(), []
    for v in out:
        if v and v not in seen and len(v) >= 3:
            seen.add(v)
            res.append(v)
    return res[:12]


# ---------------------------------------------------------------------------
# 2. TAKLIF — uch signalni RRF bilan birlashtiradi
# ---------------------------------------------------------------------------
#: Semantik shox. `embedding_c` — MARKAZLASHTIRILGAN vektor
#: (schema_patch_semantik.sql). Xom `embedding` ishlatilmaydi: o'lchandi,
#: korpus markazining normasi 0.909 (anizotropiya) va ma'nosiz so'rov
#: max 0.826 kosinus oladi, ya'ni xom kosinus ranglash signali EMAS.
#:
#: HUBLIK TUZATMASI (CSLS): xom kosinus emas, `cos - hub_bias`.
#: O'lchandi — `86.90` ("Услуга по лабораторному анализу") 25 mahsulotning
#: 14 tasida 1-o'ringa chiqardi, chunki uning vektori HAR QANDAY tibbiy
#: so'rovga yaqin (183 ta kod unga kosinus>0.3 da, aniq kod 32.50 da 124).
#: `hub_bias` = kodning O'Z 10 qo'shnisiga o'rtacha yaqinligi
#: (schema_patch_goodcode_2.sql). 86.90 -> 0.570, 32.50 -> 0.466.
#:
#: DIQQAT — bu ifoda HNSW indeksidan foydalanmaydi (arifmetika bor).
#: 1146 ta kod uchun to'liq skan millisekundlar oladi. Lug'at o'n
#: minglarga o'ssa qayta ko'rib chiqish kerak.
SQL_SEM = """
SELECT ge.code,
       ROW_NUMBER() OVER (
           ORDER BY (1 - (ge.embedding_c <=> %(qvec)s::vector))
                    - COALESCE(ge.hub_bias, 0) DESC) AS rnk
FROM good_code_embedding ge
JOIN dim_good_code d ON d.code = ge.code
WHERE ge.embedding_c IS NOT NULL
  AND d.level = %(level)s
  AND d.n_tender_open > 0
ORDER BY (1 - (ge.embedding_c <=> %(qvec)s::vector))
         - COALESCE(ge.hub_bias, 0) DESC
LIMIT %(cap)s
"""

#: Leksik shox — lug'at nomlari bo'yicha trigram o'xshashligi.
#: `names` massivi chastota bo'yicha tartiblangan, shuning uchun
#: birinchi nomlar guruhning haqiqiy vakili.
SQL_LEX = """
SELECT d.code,
       ROW_NUMBER() OVER (ORDER BY max(similarity(lower(n.nom), p.naqsh)) DESC) AS rnk
FROM dim_good_code d
CROSS JOIN LATERAL unnest(d.names) AS n(nom)
CROSS JOIN unnest(%(naqshlar)s::text[]) AS p(naqsh)
WHERE d.level = %(level)s
  AND d.n_tender_open > 0
  AND lower(n.nom) %% p.naqsh
GROUP BY d.code
ORDER BY max(similarity(lower(n.nom), p.naqsh)) DESC
LIMIT %(cap)s
"""

#: Kategoriya priori — A'ZOLIK, RANG EMAS.
#:
#: NEGA RANG EMAS: prior avval RRF ga uchinchi RANGLANGAN ro'yxat bo'lib
#: kirardi va o'lchandi — `86.90` ("Услуга по лабораторному анализу",
#: bor-yo'g'i 1 ta ochiq tender) 25 mahsulotning 14 tasida BIRINCHI
#: o'ringa chiqdi. Sabab: u ikkita zaif signaldan (prior + semantik)
#: ball yig'ib, bitta kuchli signalga ega kodni bosib ketardi.
#:
#: Endi prior — BITTA BONUS: to'g'ri NACE oilasidami yoki yo'q. Tartibni
#: leksik va semantik hal qiladi, prior esa begona oilani pastga suradi.
SQL_PRIOR = """
SELECT d.code
FROM dim_good_code d
WHERE d.level = %(level)s
  AND substring(d.code from 1 for 2) = ANY(%(divisions)s)
"""


def takliflar(product: Dict[str, Any],
              level: int = DEFAULT_LEVEL,
              limit: int = DEFAULT_LIMIT,
              cap: int = 40) -> List[Dict[str, Any]]:
    """Mahsulot uchun nomzod kodlar — RRF bilan birlashtirilgan.

    `product`: `name`, `keywords`, `category_code` (ixtiyoriy).

    Qaytadi: [{code, name_ru, n_tender_open, skor, signallar}] — skor
    bo'yicha kamayish tartibida.

    SKOR FOIZ EMAS. U RRF yig'indisi, ya'ni faqat TARTIBLASH uchun.
    O'lchandi: markazlangan kosinusning absolyut qiymati shovqindan
    ajralmaydi (shovqin p99 = 0.119, haqiqiy so'rov top-1 = 0.139), ya'ni
    undan "% moslik" yasash yolg'on bo'lardi. Interfeys shuning uchun
    RAQAM emas, `n_tender_open` (oqibat) ko'rsatadi.
    """
    qmatn = _query_text(product)
    if not qmatn:
        return []

    divisions = divisions_for_category(product.get("category_code"))
    naqshlar = _lexical_patterns(product)

    ranklar: Dict[str, Dict[str, int]] = {}

    def yig(nom: str, rows: Sequence[Dict[str, Any]]) -> None:
        for r in rows:
            ranklar.setdefault(r["code"], {})[nom] = int(r["rnk"])

    # --- Signal 1: leksik (trigram, ikki alifboda) ---
    if naqshlar:
        yig("leksik", db.query(SQL_LEX,
                               {"level": level, "naqshlar": naqshlar, "cap": cap}))

    # --- Signal 2: semantik (markazlangan vektor) ---
    # AI IXTIYORIY: model yo'q bo'lsa yoki lug'at hali vektorlanmagan
    # bo'lsa, leksik signal ishlayveradi. Jimgina bo'sh natija emas.
    try:
        from api import ai_chat
        qvec = ai_chat.vec_literal(ai_chat.embed_query(qmatn))
        yig("semantik", db.query(SQL_SEM,
                                 {"qvec": qvec, "level": level, "cap": cap}))
    except Exception:                                        # noqa: BLE001
        pass

    if not ranklar:
        return []

    # --- Prior: A'ZOLIK bonusi (rang emas) ---
    oila = set()
    if divisions:
        oila = {r["code"] for r in db.query(
            SQL_PRIOR, {"level": level, "divisions": divisions})}

    skorlar: Dict[str, float] = {}
    for code, sig in ranklar.items():
        s = sum(1.0 / (RRF_K + r) for r in sig.values())
        if code in oila:
            s += PRIOR_BONUS
        skorlar[code] = s

    hajm = {r["code"]: r["n_tender_open"] for r in db.query(
        "SELECT code, n_tender_open FROM dim_good_code WHERE code = ANY(%(c)s)",
        {"c": list(skorlar)})}
    for code in skorlar:
        skorlar[code] += min(hajm.get(code, 0), 50) * VOLUME_EPS

    eng = sorted(skorlar, key=lambda c: -skorlar[c])[:limit]

    rows = db.query(
        "SELECT code, name_ru, names, n_tender_open, n_position "
        "FROM dim_good_code WHERE code = ANY(%(codes)s)", {"codes": eng})
    bymap = {r["code"]: r for r in rows}

    out = []
    for code in eng:
        r = bymap.get(code)
        if not r:
            continue
        out.append({
            "code": code,
            "name_ru": r["name_ru"],
            "namunalar": (r["names"] or [])[:4],
            "n_tender_open": r["n_tender_open"],
            "n_position": r["n_position"],
            "skor": round(skorlar[code], 5),
            # SHAFFOFLIK: qaysi signal ushbu kodni ko'rsatgani ko'rinsin.
            # "qora quti bo'lmasin" — inson NEGA taklif qilinganini bilsin.
            "signallar": sorted(ranklar[code]) + (["oila"] if code in oila else []),
        })
    return out


# ---------------------------------------------------------------------------
# 3. TASDIQ / RAD — faqat inson
# ---------------------------------------------------------------------------
def taklif_yoz(company_id: int, product_id: int,
               kodlar: Sequence[Dict[str, Any]]) -> int:
    """Takliflarni TASDIQLANMAGAN holda yozadi. Qaytadi: yozilgan soni.

    Mavjud qatorga TEGMAYDI — inson allaqachon qaror qilgan bo'lsa
    (tasdiq yoki rad), taklif uni bekor qilmaydi.
    """
    n = 0
    for k in kodlar:
        # RETURNING bor — `execute_returning` yozadi va commit qiladi
        # (loyiha konvensiyasi; `query()` rollback qiladi, yozish uchun
        # yaramaydi). Qator allaqachon bo'lsa DO NOTHING hech narsa
        # qaytarmaydi, ya'ni `row is None` = "yangi yozilmadi".
        row = db.execute_returning(
            "INSERT INTO catalog_product_code "
            "  (product_id, company_id, code, manba, skor) "
            "VALUES (%(p)s, %(c)s, %(k)s, 'taklif', %(s)s) "
            "ON CONFLICT (product_id, code) DO NOTHING "
            "RETURNING product_id",
            {"p": product_id, "c": company_id, "k": k["code"],
             "s": k.get("skor")})
        n += 1 if row else 0
    return n


def tasdiqla(company_id: int, product_id: int, code: str, kim: str) -> bool:
    """Inson tasdig'i. `kim` — `company_account.username`, MAJBURIY.

    `kim` bo'sh bo'lsa baza CHECK bilan rad etadi
    (`catalog_product_code_tasdiq_odam`) — bu ataylab: tasdiq odamsiz
    yozilmasin.
    """
    if not (kim or "").strip():
        raise ValueError("tasdiqlagan (kim) bo'sh bo'la olmaydi")
    # `company_id` shartda TURISHI SHART — ko'p-ijarachilik: A kompaniya
    # B ning bog'lanishini tasdiqlay olmasin. Statik SQL skaneri
    # (_tests/multitenant_test.py) shu qoidani majburlaydi.
    row = db.execute_returning(
        "UPDATE catalog_product_code "
        "SET tasdiqlandi = now(), tasdiqlagan = %(kim)s, rad_etildi = NULL "
        "WHERE product_id = %(p)s AND code = %(k)s AND company_id = %(c)s "
        "RETURNING product_id",
        {"p": product_id, "k": code, "c": company_id, "kim": kim.strip()})
    return row is not None


def rad_et(company_id: int, product_id: int, code: str) -> bool:
    """Inson rad etdi. Qator O'CHIRILMAYDI — aks holda keyingi taklif
    uni qayta chiqarardi va inson bir ishni takror qilardi."""
    row = db.execute_returning(
        "UPDATE catalog_product_code "
        "SET rad_etildi = now(), tasdiqlandi = NULL, tasdiqlagan = NULL "
        "WHERE product_id = %(p)s AND code = %(k)s AND company_id = %(c)s "
        "RETURNING product_id",
        {"p": product_id, "k": code, "c": company_id})
    return row is not None


# ---------------------------------------------------------------------------
# 4. MOSLASHTIRISH — tasdiqlangan kodlar bo'yicha, POZITSIYA darajasida
# ---------------------------------------------------------------------------
#: NEGA POZITSIYA DARAJASIDA: o'lchandi — bitta tenderда ham
#: "Стол ученический" (31.01), ham "Шкаф медицинский" (32.50) bo'ladi.
#: Tender darajasidagi kategoriya shuning uchun qo'pol. Tibbiy shkaf
#: sotuvchi broker o'sha tenderni KO'RISHI kerak, lekin QAYSI pozitsiya
#: unga tegishli ekanini ham bilishi kerak — TZ dagi `match_line` shu.
SQL_MOSLIK = """
WITH kodlar AS (
    -- ALIAS MAJBURIY (`v.`). Bu so'rovda ijarachi ustunining IKKI xil
    -- ma'nosi uchrashadi: `t.company_id` — BUYURTMACHI tashkiloti (manba
    -- platformadan kelgan), `v.company_id` — BIZNING ijarachimiz.
    -- Aliassiz qoldirilsa PostgreSQL o'zi tanlaydi: xato chiqmaydi,
    -- natija noto'g'ri bo'ladi. `_tests/multitenant_test.py` (A4) buni
    -- statik tekshiradi (u izoh matnini ham skanerlaydi, shuning uchun
    -- bu yerda ham aliasli shakl yozilgan).
    SELECT DISTINCT v.code, v.product_id, v.product_name
    FROM v_catalog_code_active v
    WHERE v.company_id = %(company_id)s
)
SELECT t.id                                   AS tender_id,
       count(DISTINCT g.good_code)            AS mos_pozitsiya,
       sum(g.totalcost_item)                  AS mos_summa,
       array_agg(DISTINCT k.product_name)     AS mahsulotlar,
       array_agg(DISTINCT g.name)             AS pozitsiyalar,
       array_agg(DISTINCT k.code)             AS kodlar
FROM kodlar k
JOIN tender_good g ON g.good_code LIKE k.code || '%%'
JOIN tender t      ON t.id = g.tender_id
WHERE (%(only_open)s IS FALSE
       OR (t.status = 'open' AND (t.close_at IS NULL OR t.close_at > now())))
GROUP BY t.id
ORDER BY mos_pozitsiya DESC, mos_summa DESC NULLS LAST
LIMIT %(limit)s
"""


def moslik(company_id: int, only_open: bool = True,
           limit: int = 200) -> List[Dict[str, Any]]:
    """Kompaniyaning TASDIQLANGAN kodlari bo'yicha mos tenderlar.

    Tasdiqlangan kodi yo'q bo'lsa BO'SH ro'yxat qaytadi — va chaqiruvchi
    buni "moslik yo'q" deb EMAS, "katalog hali kodlanmagan" deb
    ko'rsatishi shart (`v_catalog_kodsiz`). Ikkisi butunlay boshqa holat.
    """
    return db.query(SQL_MOSLIK, {"company_id": company_id,
                                 "only_open": only_open, "limit": limit})


#: Bitta tenderning MOS POZITSIYALARI — dalil bilan.
#:
#: NEGA POZITSIYA QAYTADI: broker "bu tender menga mos" degan da'voni
#: TEKSHIRA olishi kerak. Mahsulot nomini ko'rsatish yetarli emas —
#: o'lchandi, bir kod (masalan `32.50`) katalogning 8 ta mahsuloti
#: bilan bog'langan bo'lishi mumkin va u holda qaysi biri
#: ko'rsatilishi TASODIFIY bo'lib qoladi: "Шкаф медицинский"
#: pozitsiyasi yonida "Bemor monitori" chiqardi.
SQL_POZITSIYALAR = """
SELECT g.tender_id, g.good_code, g.name AS pozitsiya,
       g.amount, g.unit, g.totalcost_item,
       v.code, v.product_id, v.product_name
FROM tender_good g
JOIN v_catalog_code_active v
  ON g.good_code LIKE v.code || '%%'
 AND v.company_id = %(company_id)s
WHERE g.tender_id = ANY(%(ids)s)
  AND g.name IS NOT NULL
ORDER BY g.tender_id, g.good_code
"""


#: Atribut uchun eng kichik o'xshashlik. Bundan past bo'lsa MAHSULOT
#: BIRIKTIRILMAYDI — "Шкаф для книг" (kitob javoni) katalogdagi hech
#: bir mahsulotga o'xshamaydi va unga tasodifiy nom yopishtirish
#: foydalanuvchini chalg'itadi. O'lchangan qiymatlar:
#:     "Кресло офисное"   -> "Ofis kreslosi"  0.348   (to'g'ri)
#:     "Шкаф медицинский" -> "Tibbiy shkaf"   0.192   (to'g'ri)
#:     "Шкаф медицинский" -> "Bemor monitori" 0.030   (shovqin)
#: 0.05 shovqin (0.03) dan yuqori, eng zaif to'g'ri moslik (0.179) dan past.
ATRIBUT_CHEGARA = 0.05


def _uchliklar(s: str) -> set:
    s = f"  {(s or '').lower().strip()}  "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def _ozgarish(katalog_nomi: str, pozitsiya: str) -> float:
    """Katalog nomi va tender pozitsiyasining o'xshashligi, 0..1.

    TRANSLITERATSIYA MAJBURIY. Katalog o'zbek-lotinda, korpus rus va
    o'zbek-kirillda — xom belgi-uchliklar HAR DOIM 0 beradi:

        xom:        "Кресло офисное" <-> "Ofis kreslosi"  = 0.000
        translit:                                          = 0.348

    Xom taqqoslash bilan atribut butunlay tasodifiy bo'lardi va aynan
    shu sababli "Шкаф медицинский" pozitsiyasi yonida "Bemor monitori"
    ko'rinardi.
    """
    nishon = translit.norm_text(pozitsiya)
    B = _uchliklar(nishon)
    if not B:
        return 0.0
    eng = 0.0
    for v in (translit.variants(katalog_nomi) or [katalog_nomi]):
        A = _uchliklar(v)
        if A:
            eng = max(eng, len(A & B) / len(A | B))
    return eng


def pozitsiya_moslik(company_id: int,
                     tender_ids: Sequence[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Tender -> mos pozitsiyalar ro'yxati, TO'G'RI mahsulot atributi bilan.

    Bir kodni bir necha mahsulot baham ko'rsa, pozitsiyaga NOMI eng
    yaqin mahsulot biriktiriladi. Bu taxmin va shundayligicha
    belgilanadi (`aniq=False`) — interfeys shubhani yashirmasin.
    """
    if not tender_ids:
        return {}
    rows = db.query(SQL_POZITSIYALAR,
                    {"company_id": company_id, "ids": list(tender_ids)})

    # Pozitsiya bo'yicha guruhlaymiz: bitta pozitsiyaga bir nechta
    # mahsulot da'vogar bo'lishi mumkin.
    davogarlar: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        davogarlar.setdefault((r["tender_id"], r["good_code"], r["pozitsiya"]),
                              []).append(r)

    out: Dict[int, List[Dict[str, Any]]] = {}
    for (tid, gcode, poz), lst in davogarlar.items():
        if len(lst) == 1:
            eng, aniq = lst[0], True
        else:
            # Bir kodni bir necha mahsulot baham ko'rgan -> pozitsiya
            # nomiga eng yaqinini tanlaymiz.
            eng = max(lst, key=lambda r: _ozgarish(r["product_name"], poz))
            skor = _ozgarish(eng["product_name"], poz)
            if skor < ATRIBUT_CHEGARA:
                # SIGNAL YO'Q -> TAXMIN QILMAYMIZ. Pozitsiya ko'rsatiladi,
                # mahsulot nomi esa NULL. Tasodifiy nom yopishtirish
                # foydalanuvchini chalg'itadi (bu aynan shikoyat
                # qilingan xatti-harakat edi).
                out.setdefault(tid, []).append({
                    "pozitsiya": poz, "good_code": gcode, "kod": eng["code"],
                    "mahsulot": None, "mahsulot_id": None,
                    "aniq": False, "davogar": len(lst),
                    "miqdor": (float(eng["amount"])
                               if eng["amount"] is not None else None),
                    "birlik": eng["unit"],
                    "summa": (float(eng["totalcost_item"])
                              if eng["totalcost_item"] is not None else None),
                })
                continue
            aniq = False
        out.setdefault(tid, []).append({
            "pozitsiya": poz,
            "good_code": gcode,
            "kod": eng["code"],
            "mahsulot": eng["product_name"],
            "mahsulot_id": eng["product_id"],
            # `aniq=False` -> bir kodni bir necha mahsulot baham ko'rgan,
            # mahsulot nomi TAXMIN. Interfeys buni ko'rsatishi kerak.
            "aniq": aniq,
            "davogar": len(lst),
            "miqdor": float(eng["amount"]) if eng["amount"] is not None else None,
            "birlik": eng["unit"],
            "summa": (float(eng["totalcost_item"])
                      if eng["totalcost_item"] is not None else None),
        })
    return out


def kodsiz_mahsulotlar(company_id: int) -> List[Dict[str, Any]]:
    """Tasdiqlangan kodi YO'Q mahsulotlar — moslashtirishda ko'rinmaydi."""
    return db.query(
        "SELECT product_id, name, kutayotgan_taklif FROM v_catalog_kodsiz "
        "WHERE company_id = %(c)s ORDER BY name", {"c": company_id})


def holat(company_id: int) -> Dict[str, Any]:
    """Kodlash holati — interfeys va sinov uchun bitta manba."""
    row = db.query_one(
        "SELECT (SELECT count(*) FROM catalog_product WHERE company_id=%(c)s) AS mahsulot,"
        "       (SELECT count(DISTINCT product_id) FROM v_catalog_code_active"
        "         WHERE company_id=%(c)s) AS kodlangan,"
        "       (SELECT count(*) FROM v_code_review WHERE company_id=%(c)s) AS kutayotgan",
        {"c": company_id}) or {}
    mahsulot = row.get("mahsulot") or 0
    kodlangan = row.get("kodlangan") or 0
    return {
        "mahsulot": mahsulot,
        "kodlangan": kodlangan,
        "kodsiz": mahsulot - kodlangan,
        "kutayotgan_taklif": row.get("kutayotgan") or 0,
        # Qamrov FOIZI — bu HALOL foiz, chunki maxraj aniq (jami mahsulot).
        "qamrov_pct": round(kodlangan / mahsulot * 100, 1) if mahsulot else None,
    }
