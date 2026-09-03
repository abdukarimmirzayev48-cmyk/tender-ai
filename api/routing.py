"""
BROKERGA YO'NALTIRISH — "bu tender kimga tegishli va u nima qildi?"
==================================================================

Zanjir: tender -> talab ajratish -> malaka tekshiruvi -> NAVBAT ->
broker qarori.

NEGA TENDER-AI TOMONDA, ERP DA EMAS
═══════════════════════════════════
Chegara simmetrik va SINOV BILAN QULFLANGAN (`_tests/auth_test.py`):

    ERP        `public.*` dan O'QIYDI, YOZMAYDI.
    Tender-AI  `erp.v_tender_status` dan O'QIYDI, YOZMAYDI.

Yo'naltirishni `erp.*` ga yozish bu shartnomani buzardi va IKKALA
loyihaning sinovini yiqitardi. Shuning uchun navbat shu tomonda
turadi: tender-ai "kimga tavsiya qilaman" deydi, ERP o'zi bilganini
qiladi. Ikkisi `erp.v_tender_status` orqali solishtiriladi.

IKKI QAROR ARALASHMAYDI
═══════════════════════
`ai_qaror` va `inson_qaror` ALOHIDA ustun. Bitta "status" ga qo'shib
yuborilsa "model necha foizda haq edi" degan savolga javob qolmasdi —
`blind_value` bilan bir xil sabab (§16.56).

Va `inson_qaror` YOZILGACH MASHINA UNI QAYTA YOZMAYDI. Talab
o'zgarganda `ai_qaror` yangilanadi, inson qarori esa turaveradi va
`ai_ozgardi` bayrog'i qo'yiladi — broker o'zi qayta ko'radi.
Bu `tender_requirement` dagi `ON CONFLICT` tuynugidan olingan saboq.

DIQQAT — bu jumla bir muddat YOLG'ON edi. `ai_ozgardi` ustuni
yozilmagan, faqat SHU IZOHDA tasvirlangan edi (`grep` bitta natija
bergan: izohning o'zi). Ya'ni izoh himoyani va'da qilgan, himoya esa
yo'q edi. `schema_patch_routing_2.sql` bilan tuzatildi va endi
`CHECK (NOT ai_ozgardi OR ai_qaror_eski IS NOT NULL)` cheklovi
qoidani BAZADA ushlab turadi.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from api import db, qualification, xatolar

#: Broker qarorlari.
INSON_QARORLAR = ("olindi", "rad", "kutilsin")

#: Oqim holatlari.
HOLATLAR = ("yangi", "korilmoqda", "yopildi")

#: Qaysi AI qarori navbatga tushadi. `no_go` ATAYLAB YO'Q: brokerni
#: 139 ta rad etilgan tender bilan ko'mib tashlash navbatni
#: foydasiz qiladi. Lekin ular YO'QOLMAYDI — `--barchasi` bilan
#: yoziladi va interfeysda alohida filtr bo'ladi.
NAVBAT_QARORLARI = ("go", "review")

#: Filtrda ruxsat etilgan AI qarorlari. `NAVBAT_QARORLARI` dan
#: FARQ QILADI: u "navbatga NIMA YOZILADI" ni, bu esa "navbatdan
#: NIMANI so'rash mumkin" ni bildiradi.
DECISION_FILTRLARI = ("go", "review", "no_go")


SQL_UPSERT = """
INSERT INTO tender_routing
    (company_id, tender_id, ai_qaror, ai_ball, ai_manba, ai_sabab)
VALUES (%(c)s, %(t)s, %(q)s, %(b)s, %(m)s, %(s)s)
ON CONFLICT (company_id, tender_id) DO UPDATE SET
    ai_qaror = EXCLUDED.ai_qaror,
    ai_ball  = EXCLUDED.ai_ball,
    ai_manba = EXCLUDED.ai_manba,
    ai_sabab = EXCLUDED.ai_sabab,

    -- ESKIRGAN QAROR BELGILANADI.
    --
    -- Broker "olindi" deb qaror beradi. Ertasiga hujjat qayta
    -- ajratiladi, yangi sertifikat talabi topiladi, `ai_qaror` `go`
    -- dan `no_go` ga o'tadi — va broker BUNDAN XABAR TOPMAYDI.
    -- Uning qarori eskirgan tahlilga asoslangan bo'lib qolaveradi.
    --
    -- Shart IKKI qismli: inson allaqachon qaror bergan BO'LSIN va
    -- QAROR HAQIQATAN o'zgargan bo'lsin. `ai_sabab` o'zgarishi
    -- yetarli emas — matn tahriri brokerni bezovta qilmasin.
    ai_ozgardi = (tender_routing.inson_qaror IS NOT NULL
                  AND tender_routing.ai_qaror
                      IS DISTINCT FROM EXCLUDED.ai_qaror),
    -- FAQAT BIR MARTA YOZILADI (`ai_qaror_eski IS NULL` sharti).
    --
    -- NUQSON EDI: shartsiz yozilganda IKKINCHI o'zgarish
    -- birinchisini USTIGA yozardi va inson HAQIQATAN ko'rgan qaror
    -- YO'QOLARDI:
    --     1-o'zgarish: inson `go` ni ko'rgan, AI -> review
    --                  ai_qaror_eski = 'go'        TO'G'RI
    --     2-o'zgarish: AI -> no_go
    --                  ai_qaror_eski = 'review'    ASL YO'QOLDI
    --
    -- Kelishuv o'lchovi (`v_routing_kelishuv`) aynan shu ustunga
    -- tayanadi, ya'ni nuqson tarixiy haqiqatni qayta yozardi.
    -- Hozircha tishlamagan (`ai_ozgardi` = 0 qator), lekin u
    -- yashirin edi va o'z-o'zidan tuzalmasdi.
    ai_qaror_eski = CASE
        WHEN tender_routing.inson_qaror IS NOT NULL
             AND tender_routing.ai_qaror
                 IS DISTINCT FROM EXCLUDED.ai_qaror
             AND tender_routing.ai_qaror_eski IS NULL
        THEN tender_routing.ai_qaror
        ELSE tender_routing.ai_qaror_eski END
-- FAQAT AI qarori HAQIQATAN o'zgarganda yozamiz. Aks holda har
-- yurish `updated_at` ni surib, navbatni "yangi" qilib ko'rsatardi.
WHERE tender_routing.ai_qaror IS DISTINCT FROM EXCLUDED.ai_qaror
   OR tender_routing.ai_sabab IS DISTINCT FROM EXCLUDED.ai_sabab
RETURNING id, ai_qaror, inson_qaror, ai_ozgardi
"""

#: NAVBAT NOMZODLARI — "qaysi tenderni brokerga tavsiya qilish MUMKIN".
#:
#: O'LCHANGAN NUQSON (2026-09-03). Nomzodlar `v_requirement_review`
#: dan olinardi. O'sha ko'rinishning TIRIK ta'rifi
#: (`schema_patch_requirement_8.sql`, migratsiya 0055) esa bu:
#:
#:     FROM tender_requirement WHERE review_status = 'pending_review'
#:
#: Ya'ni u "brokerga nomzod" ro'yxati EMAS, "inson hali KO'RMAGAN
#: talablar" ro'yxati. Ikkisi bir joyga qo'shib yuborilgan edi va
#: bu IKKITA aniq oqibat berdi:
#:
#: 1. REYESTR TALABI NOMZOD BO'LMAYDI. `source='api'` qatorlari
#:    `review_status='extracted'` bilan yoziladi — ular ko'rikka
#:    muhtoj emas, chunki reyestrdan keladi. Natijada FAQAT reyestr
#:    talabi bor tender navbatga HECH QACHON tushmaydi.
#:    O'LCHANDI: talabi bor 584 ta ochiq tenderdan 100 tasi.
#:
#: 2. KO'RIKNI TUGATISH TENDERNI NAVBATDAN CHIQARADI. Talablar
#:    tasdiqlangach `pending_review` qolmaydi, tender ko'rinishdan
#:    yo'qoladi va `yonaltir_hammasi` uni BOSHQA QAYTA BAHOLAMAYDI.
#:    Ya'ni inson halqasi ishlay boshlagan zahoti tenderlar
#:    yo'naltirishdan JIMGINA tusha boshlaydi. Bugun ko'rilgan
#:    qator atigi 2 ta, shuning uchun bu hali KO'RINMAGAN edi.
#:
#: To'g'ri chegara: "malaka tekshiruvi uchun DALIL bormi", ya'ni
#: tenderning talabi ajratilganmi. Ko'rik HOLATI bunga aloqasiz —
#: u dalil sifatini oshiradi, dalilni yo'q qilmaydi.
#:
#: Talabi UMUMAN yo'q tender ataylab kirmaydi: `qualification.check`
#: unda hech narsa o'lchamaydi va natija `olchandi=0` bo'lardi —
#: "o'lchanmagan" ni "yomon" ga aylantirish bu loyihada eng qimmat
#: xato sinfi.
SQL_NOMZOD_SONI = """
SELECT count(DISTINCT r.tender_id)
FROM tender_requirement r
JOIN tender t ON t.id = r.tender_id
WHERE r.company_id = %(c)s
  AND (t.close_at IS NULL OR t.close_at > now())
"""

SQL_NOMZODLAR = """
SELECT DISTINCT r.tender_id
FROM tender_requirement r
JOIN tender t ON t.id = r.tender_id
WHERE r.company_id = %(c)s
  AND (t.close_at IS NULL OR t.close_at > now())
ORDER BY r.tender_id
LIMIT %(n)s
"""

#: Navbat tartibi — filtrdan MUSTAQIL. Ikki joyda (ro'yxat va
#: sanoq) bir xil `WHERE` ishlatiladi, `ORDER BY` esa faqat
#: ro'yxatda.
SQL_NAVBAT_TARTIB = """
ORDER BY
    -- ESKIRGAN QAROR ENG TEPADA. Broker allaqachon qaror bergan,
    -- lekin tahlil o'zgargan — bu eng shoshilinch holat, chunki
    -- u YOLG'ON ISHONCH bilan yuribdi.
    CASE WHEN v.ai_ozgardi THEN 0 ELSE 1 END,
    -- Muddati yaqin ustun, lekin AI 'go' deganlari oldinda.
    CASE WHEN v.ai_qaror = 'go' THEN 0 ELSE 1 END,
    v.close_at NULLS LAST
"""


def _navbat_where(holat: Optional[str], qaror: Optional[str],
                  region: Optional[str], q: Optional[str],
                  eskirgan: bool,
                  katalog_ids: Optional[List[int]]
                  ) -> Tuple[str, Dict[str, Any]]:
    """Navbat filtri — `WHERE` bo'lagi va parametrlari.

    QIDIRUV VA HUDUD `api/queries.py` DAN OLINADI, bu yerda QAYTA
    YOZILMAYDI. Sabab tajribadan: hudud qoidasi ikki joyda yozilgani
    uchun "Sizga mos" va broker navbati boshqa-boshqa javob berardi
    (2026-09-03). Qidiruvda bu undan ham sezilarli bo'lardi —
    `translit.variants()` lotin/kirill/o'zbek shakllarini
    kengaytiradi va uni takrorlash "bosh ro'yxatda topiladi,
    navbatda topilmaydi" holatini yasardi.

    `tender t` JOIN qilinadi: `build_text_search` aynan shu
    taxallusni kutadi.
    """
    from api import queries

    clauses = ["v.company_id = %(c)s"]
    params: Dict[str, Any] = {}

    if holat is not None:
        if holat not in HOLATLAR:
            raise xatolar.Xato("INVALID_ENUM",
                               {"maydon": "holat", "qiymat": holat})
        clauses.append("v.holat = %(holat)s")
        params["holat"] = holat
    if qaror is not None:
        # `no_go` ham qabul qilinadi: u `--barchasi` bilan yozilgan
        # bo'lsa navbatda turadi va broker uni ko'ra olishi kerak.
        if qaror not in DECISION_FILTRLARI:
            raise xatolar.Xato("INVALID_ENUM",
                               {"maydon": "qaror", "qiymat": qaror})
        clauses.append("v.ai_qaror = %(qaror)s")
        params["qaror"] = qaror
    if eskirgan:
        clauses.append("v.ai_ozgardi")
    if katalog_ids is not None:
        # "SIZGA MOS" — ta'rif `kodlash.mos_tender_idlari()` da,
        # bu yerda TAKRORLANMAYDI.
        #
        # BO'SH RO'YXAT "filtr yo'q" DEGANI EMAS: katalog kodlanmagan
        # bo'lsa natija ham BO'SH bo'lishi kerak. `::bigint[]` sharti
        # aynan shuning uchun — bo'sh massiv bilan `= ANY` FALSE
        # beradi, castsiz esa psycopg2 turini aniqlay olmasdi.
        clauses.append("v.tender_id = ANY(%(katalog_ids)s::bigint[])")
        params["katalog_ids"] = katalog_ids
    if region:
        # Ierarxik prefiks — bosh ro'yxatdagi bilan AYNI qoida.
        clauses.append("(t.area_path = %(region)s"
                       " OR t.area_path LIKE %(region)s || '.%%')")
        params["region"] = region
    if q:
        clause, q_params = queries.build_text_search(q)
        if clause:
            clauses.append(clause)
            params.update(q_params)
    return "WHERE " + " AND ".join(clauses), params


SQL_NAVBAT_FROM = """
FROM v_routing_queue v
JOIN tender t ON t.id = v.tender_id
"""


def _ball(natija: Dict[str, Any]) -> float:
    """Malaka natijasidan 0..1 ball.

    O'LCHANMAGAN MEZON BALLNI KO'TARMAYDI. Maxraj — o'lchangan
    mezonlar soni, jami mezon emas: aks holda hech narsa
    o'lchanmagan tender ham "yomon emas" degan ball olardi.
    """
    olchandi = natija["olchandi"]
    if not olchandi:
        return 0.0
    return round(natija["ok"] / olchandi, 3)


def yonaltir(tender_id: int, company_id: int,
             barchasi: bool = False) -> Optional[Dict[str, Any]]:
    """Bitta tenderni baholab navbatga qo'yadi. MODEL CHAQIRILMAYDI.

    `barchasi=False` (odatiy) — faqat `go` va `review` yoziladi.
    `no_go` larni ham yozish navbatni foydasiz qilardi.
    """
    natija = qualification.check(tender_id, company_id)
    if not barchasi and natija["decision"] not in NAVBAT_QARORLARI:
        return None

    to_siq = [m["label"] for m in natija["criteria"]
              if m["status"] in ("fail", "risk")]
    # QAMROV KO'RINSIN. `3/3 mezon o'tdi` va `ball=1.000` "mukammal"
    # deb o'qiladi, holbuki 7 mezondan 4 tasi UMUMAN o'lchanmagan.
    # O'lchanmagan mezon ballni ko'tarmaydi (maxraj `olchandi`), lekin
    # matn buni aytmasa broker noto'g'ri xulosa qilardi.
    olchanmadi = natija["jami_mezon"] - natija["olchandi"]
    sabab = (f"{natija['ok']}/{natija['olchandi']} mezon o'tdi"
             + (f", {olchanmadi} ta O'LCHANMADI" if olchanmadi else "")
             + (f"; e'tibor: {', '.join(to_siq)}" if to_siq else ""))
    # SINOV MA'LUMOTI yorlig'i sababda ham ko'rinsin — broker qaysi
    # asosda tavsiya kelganini bilsin.
    if natija["is_sample"]:
        sabab = "[SINOV PROFILI] " + sabab

    r = db.execute_returning(SQL_UPSERT, {
        "c": company_id, "t": tender_id,
        "q": natija["decision"], "b": _ball(natija),
        "m": "malaka", "s": sabab[:2000]})

    # `ON CONFLICT ... WHERE` sharti bajarilmasa `RETURNING` HECH NARSA
    # qaytarmaydi — ya'ni "o'zgarmadi" va "yozilmadi" bir xil ko'rinadi.
    # Chaqiruvchi shunda `routing_id = None` olardi va yozuvga umuman
    # murojaat qila olmasdi. ID DOIM qaytariladi; `ozgardi` esa
    # ALOHIDA bayroq.
    rid = (r or {}).get("id")
    if rid is None:
        rid = db.scalar("""SELECT id FROM tender_routing
                           WHERE company_id = %(c)s AND tender_id = %(t)s""",
                        {"c": company_id, "t": tender_id})
    return {"routing_id": rid, "ozgardi": bool(r),
            # INSON QARORI ESKIRDIMI — chaqiruvchi buni ko'rsin.
            "inson_qarori_eskirdi": bool((r or {}).get("ai_ozgardi")),
            **natija}


def yonaltir_hammasi(company_id: int, limit: int = 2000,
                     barchasi: bool = False) -> Dict[str, Any]:
    """Nomzod tenderlarning HAMMASINI baholaydi.

    NOMZOD = talabi ajratilgan ochiq tender (`SQL_NOMZODLAR` dagi
    izohga qarang). Ilgari bu "talabi hali ko'rilmagan tender" edi
    va u ikkita tenderni navbatdan chiqarardi.

    MUSBAT TASDIQ: nechta baholandi va nechtasi navbatga tushdi —
    ikkalasi ham qaytariladi. "Xato chiqmadi" yetarli emas.
    """
    # JIMGINA KESISH BO'LMASIN. Standart `limit` bugungi ma'lumot
    # hajmiga (500) TENG chiqdi — korpus 600 ga o'ssa 100 tasi
    # tushib qolardi va jurnal "baholandi 500" deb muvaffaqiyat
    # ko'rsatardi. Jami son ALOHIDA o'lchanadi va farq aytiladi.
    #
    # 2026-09-03: bu KUTILGAN holat RO'Y BERDI. Nomzod ta'rifi
    # to'g'rilangach ularning soni 484 dan 584 ga chiqdi, ya'ni
    # eski standart 500 endi 84 tasini kesardi. Standart 2000 ga
    # ko'tarildi (`run_etl.py` allaqachon shuni ishlatardi va
    # HTTP chegarasi ham 2000 edi — ya'ni uchta joyda uch xil
    # raqam turgan edi).
    jami = db.scalar(SQL_NOMZOD_SONI, {"c": company_id}) or 0
    ids = [r["tender_id"] for r in db.query(
        SQL_NOMZODLAR, {"c": company_id, "n": limit})]
    kesildi = max(0, int(jami) - len(ids))

    baholandi = qoshildi = ozgardi = eskirdi = 0
    qarorlar: Dict[str, int] = {}
    for tid in ids:
        out = yonaltir(tid, company_id, barchasi=barchasi)
        baholandi += 1
        if out is None:
            qarorlar["no_go"] = qarorlar.get("no_go", 0) + 1
            continue
        qarorlar[out["decision"]] = qarorlar.get(out["decision"], 0) + 1
        qoshildi += 1
        if out["ozgardi"]:
            ozgardi += 1
        if out["inson_qarori_eskirdi"]:
            eskirdi += 1
    return {"baholandi": baholandi, "navbatga_tushdi": qoshildi,
            "yangilandi": ozgardi, "qarorlar": qarorlar,
            # BROKER QARORI ESKIRGANLARI — eng shoshilinch raqam.
            "inson_qarori_eskirdi": eskirdi,
            # KESILGANI AYTILADI. Nol bo'lmasa — qamrov to'liq emas.
            "jami_nomzod": int(jami), "kesildi": kesildi,
            "navbat_hajmi": db.scalar(
                "SELECT count(*) FROM v_routing_queue WHERE company_id=%(c)s",
                {"c": company_id}) or 0}


def navbat(company_id: int, holat: Optional[str] = None,
           limit: int = 100, q: Optional[str] = None,
           qaror: Optional[str] = None, region: Optional[str] = None,
           eskirgan: bool = False,
           katalog: bool = False) -> Tuple[List[dict], int]:
    """Brokerga ko'rsatiladigan navbat — faqat OCHIQ tenderlar.

    QATORLAR **va** MOS KELGANLARNING JAMI SONI qaytariladi.

    NEGA JAMI ALOHIDA (2026-09-03): `limit` 100, navbat esa 188.
    Faqat qatorlarni qaytarsak interfeys "100 ta topildi" derdi va
    filtr natijasi JIMGINA kesilardi — foydalanuvchi qidirgani
    ro'yxatda yo'q bo'lsa buni "topilmadi" deb o'qirdi. Bu loyihada
    aynan shu sinf ("kesilgani aytilmaydi") bir necha marta
    takrorlangan.

    `erp_ish` HAR TENDER uchun alohida hisoblanadi.

    NEGA: ko'rinishdagi `erp_bor` — "ERP integratsiyasi UMUMAN
    mavjudmi" degan GLOBAL bayroq. Interfeys uni "bu tender ERP da
    bor" deb o'qigan va ERP o'rnatilgan muhitda HAR qatorga yorliq
    qo'ygan edi (brauzerda ko'rindi). Broker "ish allaqachon
    boshlangan" deb o'ylab tenderni ikkinchi marta ochmasdi.
    """
    # KATALOG FILTRI — id lar YAGONA manbadan. Navbat allaqachon
    # faqat ochiq tenderlardan iborat (`v_routing_queue`), shuning
    # uchun `only_open=True`.
    katalog_ids = None
    if katalog:
        from api import kodlash
        katalog_ids = sorted(kodlash.mos_tender_idlari(company_id))
    where, params = _navbat_where(holat, qaror, region, q, eskirgan,
                                  katalog_ids)
    params["c"] = company_id
    jami = db.scalar(f"SELECT count(*) {SQL_NAVBAT_FROM} {where}",
                     params) or 0
    qatorlar = db.query(
        f"SELECT v.* {SQL_NAVBAT_FROM} {where} {SQL_NAVBAT_TARTIB} "
        f"LIMIT %(limit)s", {**params, "limit": limit})

    # ERP FAQAT O'QILADI va u BO'LMASLIGI MUMKIN — bu xato emas.
    erp_ish: set = set()
    try:
        from api import erp_status
        if qatorlar and erp_status.ready():
            erp_ish = {r["tender_id"] for r in db.query(
                """SELECT DISTINCT tender_id FROM erp.v_tender_status
                   WHERE tender_id = ANY(%(ids)s)""",
                {"ids": [x["tender_id"] for x in qatorlar]})}
    except Exception:                                       # noqa: BLE001
        erp_ish = set()          # ERP yo'q yoki yetib bo'lmadi

    for x in qatorlar:
        x["erp_ish"] = x["tender_id"] in erp_ish
    return qatorlar, int(jami)


def ochildi(routing_id: int, company_id: int,
            broker: Optional[str] = None) -> Optional[dict]:
    """Broker ochdi — vaqt o'lchovi shu yerdan boshlanadi.

    `yopildi` holatini ORQAGA QAYTARMAYDI: qaror berilgan yozuv
    qayta ochilsa hisobot buzilardi.
    """
    return db.execute_returning("""
        UPDATE tender_routing
           SET holat = 'korilmoqda',
               broker_nomi = COALESCE(%(b)s, broker_nomi)
         WHERE id = %(id)s AND company_id = %(c)s
           AND holat = 'yangi'
        RETURNING id, holat""",
        {"id": routing_id, "c": company_id, "b": broker})


def qaror(routing_id: int, company_id: int, inson_qaror: str,
          izoh: Optional[str] = None, *,
          actor_id: Optional[int] = None,
          ishonch: Optional[str] = None,
          broker_nomi: Optional[str] = None) -> Optional[dict]:
    """Broker qarori. AI qarori TEGILMAYDI — u dalil bo'lib qoladi.

    AKTOR SERVERDA ANIQLANADI, MIJOZDAN OLINMAYDI. Ilgari imzo
    `broker: Optional[str]` edi va u to'g'ridan-to'g'ri
    `body.broker` dan kelardi — ya'ni qarorni KIM qo'yganini
    mijozning o'zi yozardi va uni hech narsa tekshirmasdi.
    O'lchandi (2026-08-31): 310 qatordan 30 tasida inson qarori bor,
    `broker_nomi` esa 0 tasida yozilgan — ya'ni yolg'on yozuv hali
    yo'q edi, lekin yo'l ochiq edi.

    Endi `broker_nomi` SERVER aniqlagan aktorning ismidan keladi
    (`api/aktor.py:aniqla()`), `ishonch` esa uning qanchalik
    ishonchli ekanini yozadi.

    YANGI PARAMETRLAR FAQAT KALIT SO'ZLI (`*`). O'LCHANGAN SABAB:
    eski imzoda 5-pozitsiya `broker` (matn) edi va
    `qualification_test.py:323` uni POZITSION uzatardi. `actor_id`
    o'sha o'ringa tushganda matn JIMGINA aktor id sifatida
    bog'lanardi. Kalit so'zli parametr bunday xatoni chaqiruv
    joyida BALAND OVOZDA yiqitadi.
    """
    if inson_qaror not in INSON_QARORLAR:
        raise xatolar.Xato("INVALID_ENUM",
                           {"maydon": "inson_qaror", "qiymat": inson_qaror})
    if ishonch not in ("erp_sessiya", "aktor_elon", "kompaniya_sessiyasi"):
        raise xatolar.Xato("TRUST_LEVEL_INVALID", {"ishonch": ishonch})
    if ishonch in ("erp_sessiya", "aktor_elon") and not actor_id:
        raise xatolar.Xato("ACTOR_REQUIRED_FOR_TRUST", {"ishonch": ishonch})
    return db.execute_returning("""
        UPDATE tender_routing
           SET inson_qaror = %(q)s,
               inson_izoh  = %(i)s,
               broker_nomi = COALESCE(%(b)s, broker_nomi),
               qaror_actor_id = %(actor_id)s,
               qaror_ishonch  = %(ishonch)s,
               qaror_vaqti = now(),
               holat       = 'yopildi',
               -- YANGI QAROR eski ogohlantirishni yopadi. Cheklov
               -- (`NOT ai_ozgardi OR ai_qaror_eski IS NOT NULL`)
               -- buzilmasligi uchun ikkalasi BIRGA tozalanadi.
               ai_ozgardi    = false,
               ai_qaror_eski = NULL
         WHERE id = %(id)s AND company_id = %(c)s
        RETURNING id, tender_id, ai_qaror, inson_qaror, holat,
                  ai_ozgardi""",
        {"id": routing_id, "c": company_id, "q": inson_qaror,
         "i": (izoh or "").strip()[:2000] or None, "b": broker_nomi,
         "actor_id": actor_id, "ishonch": ishonch})


#: Moslik foizi MA'NOLI bo'lishi uchun kerakli minimal qaror soni.
#:
#: NEGA KERAK — O'LCHANDI. Bazada BITTA sinov yozuvi qolgan edi va
#: interfeys "Moslik (1 qaror bo'yicha): no_go: 100%" deb ko'rsatdi.
#: Bitta kuzatuvdan foiz chiqarish statistika emas; u ishonch
#: uyg'otadigan, lekin asossiz raqam.
#:
#: 10 — pilot protokolidagi yopiq bosqich hajmi bilan bir xil:
#: shundan kam qaror bilan model xulqi haqida gapirib bo'lmaydi.
MOSLIK_MIN = 10


def moslik(company_id: int) -> Dict[str, Any]:
    """AI tavsiyasi bilan broker qarori necha foizda mos keldi.

    HISOBOT IKKI SHART BILAN KELADI:

      1. Qaror soni `MOSLIK_MIN` dan kam bo'lsa foiz BERILMAYDI —
         "hali o'lchanmagan" deyiladi. Bitta qarordan "100%"
         chiqarish eng zararli shakl: u haqiqiy o'lchov kabi
         ko'rinadi.
      2. Profil SINOV ma'lumotidan iborat bo'lsa yorliq qo'yiladi —
         raqam o'ylab topilgan qiymatlarni o'lchaydi.
    """
    qatorlar = db.query("""
        SELECT ai_manba, ai_qaror, jami, olindi, rad, moslik_foiz
        FROM v_routing_agreement WHERE company_id = %(c)s
        ORDER BY ai_manba, ai_qaror""", {"c": company_id})
    n_qaror = db.scalar("""SELECT count(*) FROM tender_routing
        WHERE company_id = %(c)s AND inson_qaror IS NOT NULL""",
        {"c": company_id}) or 0
    is_sample = bool(db.scalar(
        "SELECT is_sample FROM company_profile WHERE company_id = %(c)s",
        {"c": company_id}))
    # O'LCHOVSIZLIK XULOSA EMAS va BITTA KUZATUV HAM O'LCHOV EMAS.
    olchandi = int(n_qaror) >= MOSLIK_MIN
    izohlar = []
    if not olchandi:
        izohlar.append(
            f"Moslik hali O'LCHANMAGAN: {int(n_qaror)}/{MOSLIK_MIN} qaror. "
            "Kamroq qarordan foiz chiqarish asossiz.")
    if is_sample:
        izohlar.append(
            "SINOV PROFILI: raqamlar o'ylab topilgan qiymatlarga "
            "asoslangan, ulardan xulosa chiqarilmaydi.")

    return {
        # Foiz FAQAT yetarli qaror bo'lganda beriladi — aks holda
        # interfeys uni ko'rsatolmasin.
        "qatorlar": qatorlar if olchandi else [],
        "inson_qarorlari": int(n_qaror),
        "kerakli_qaror": MOSLIK_MIN,
        "is_sample": is_sample,
        "olchandi": olchandi,
        "izoh": " ".join(izohlar) or None,
    }
