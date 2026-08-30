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

from typing import Any, Dict, List, Optional

from api import db, qualification

#: Broker qarorlari.
INSON_QARORLAR = ("olindi", "rad", "kutilsin")

#: Oqim holatlari.
HOLATLAR = ("yangi", "korilmoqda", "yopildi")

#: Qaysi AI qarori navbatga tushadi. `no_go` ATAYLAB YO'Q: brokerni
#: 139 ta rad etilgan tender bilan ko'mib tashlash navbatni
#: foydasiz qiladi. Lekin ular YO'QOLMAYDI — `--barchasi` bilan
#: yoziladi va interfeysda alohida filtr bo'ladi.
NAVBAT_QARORLARI = ("go", "review")


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
    ai_qaror_eski = CASE
        WHEN tender_routing.inson_qaror IS NOT NULL
             AND tender_routing.ai_qaror
                 IS DISTINCT FROM EXCLUDED.ai_qaror
        THEN tender_routing.ai_qaror
        ELSE tender_routing.ai_qaror_eski END
-- FAQAT AI qarori HAQIQATAN o'zgarganda yozamiz. Aks holda har
-- yurish `updated_at` ni surib, navbatni "yangi" qilib ko'rsatardi.
WHERE tender_routing.ai_qaror IS DISTINCT FROM EXCLUDED.ai_qaror
   OR tender_routing.ai_sabab IS DISTINCT FROM EXCLUDED.ai_sabab
RETURNING id, ai_qaror, inson_qaror, ai_ozgardi
"""

SQL_NAVBAT = """
SELECT * FROM v_routing_queue
WHERE company_id = %(c)s
  AND (%(holat)s IS NULL OR holat = %(holat)s)
ORDER BY
    -- ESKIRGAN QAROR ENG TEPADA. Broker allaqachon qaror bergan,
    -- lekin tahlil o'zgargan — bu eng shoshilinch holat, chunki
    -- u YOLG'ON ISHONCH bilan yuribdi.
    CASE WHEN ai_ozgardi THEN 0 ELSE 1 END,
    -- Muddati yaqin ustun, lekin AI 'go' deganlari oldinda.
    CASE WHEN ai_qaror = 'go' THEN 0 ELSE 1 END,
    close_at NULLS LAST
LIMIT %(limit)s
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


def yonaltir_hammasi(company_id: int, limit: int = 500,
                     barchasi: bool = False) -> Dict[str, Any]:
    """Navbatdagi barcha tenderlarni baholaydi.

    MUSBAT TASDIQ: nechta baholandi va nechtasi navbatga tushdi —
    ikkalasi ham qaytariladi. "Xato chiqmadi" yetarli emas.
    """
    # JIMGINA KESISH BO'LMASIN. Standart `limit` bugungi ma'lumot
    # hajmiga (500) TENG chiqdi — korpus 600 ga o'ssa 100 tasi
    # tushib qolardi va jurnal "baholandi 500" deb muvaffaqiyat
    # ko'rsatardi. Jami son ALOHIDA o'lchanadi va farq aytiladi.
    jami = db.scalar(
        """SELECT count(DISTINCT v.tender_id) FROM v_requirement_review v
           JOIN tender t ON t.id = v.tender_id
           WHERE v.company_id = %(c)s
             AND (t.close_at IS NULL OR t.close_at > now())""",
        {"c": company_id}) or 0
    ids = [r["tender_id"] for r in db.query(
        """SELECT DISTINCT v.tender_id FROM v_requirement_review v
           JOIN tender t ON t.id = v.tender_id
           WHERE v.company_id = %(c)s
             AND (t.close_at IS NULL OR t.close_at > now())
           ORDER BY v.tender_id LIMIT %(n)s""",
        {"c": company_id, "n": limit})]
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
           limit: int = 100) -> List[dict]:
    """Brokerga ko'rsatiladigan navbat — faqat OCHIQ tenderlar.

    `erp_ish` HAR TENDER uchun alohida hisoblanadi.

    NEGA: ko'rinishdagi `erp_bor` — "ERP integratsiyasi UMUMAN
    mavjudmi" degan GLOBAL bayroq. Interfeys uni "bu tender ERP da
    bor" deb o'qigan va ERP o'rnatilgan muhitda HAR qatorga yorliq
    qo'ygan edi (brauzerda ko'rindi). Broker "ish allaqachon
    boshlangan" deb o'ylab tenderni ikkinchi marta ochmasdi.
    """
    if holat is not None and holat not in HOLATLAR:
        raise ValueError(f"Noma'lum holat: {holat}")
    qatorlar = db.query(SQL_NAVBAT, {"c": company_id, "holat": holat,
                                     "limit": limit})

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
    return qatorlar


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
        raise ValueError(f"Noma'lum qaror: {inson_qaror}")
    if ishonch not in ("erp_sessiya", "aktor_elon", "kompaniya_sessiyasi"):
        raise ValueError(
            f"inson qarori uchun yaroqsiz ishonch darajasi: {ishonch}")
    if ishonch in ("erp_sessiya", "aktor_elon") and not actor_id:
        raise ValueError(f"`{ishonch}` darajasi aktor SHART qiladi")
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
