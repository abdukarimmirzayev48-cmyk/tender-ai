#!/usr/bin/env bash
# =============================================================================
# Tender AI — baza zaxirasi
# =============================================================================
#     backup.sh <staging|production>
#
# `pg_dump` MAXSUS formatda (`-Fc`): u siqilgan, parallel tiklanadi
# va TANLAB tiklashga imkon beradi (bitta jadval). Oddiy SQL matni
# 134 MB hujjat matni bilan ulkan bolardi.
#
# ZAXIRA O'ZI YETARLI EMAS. Uchta narsa qilinadi:
#   1. dump olinadi;
#   2. DARHOL `pg_restore --list` bilan OCHILISHI tekshiriladi —
#      buzuq faylni haftalab saqlab yurmaslik uchun;
#   3. SHA-256 yoziladi — keyinchalik fayl ozgarganini bilish uchun.
#
# HAQIQIY TIKLASH MASHQI alohida: `restore-test.sh` (haftalik).
# =============================================================================
set -euo pipefail

MUHIT="${1:?foydalanish: backup.sh <staging|production>}"
# MUHIT FAYLI YO'LI ALMASHTIRILISHI MUMKIN — `TENDERAI_ENVFILE`.
#
# NEGA (o'lchangan 2026-09-01, B-1): yo'l `/etc/tenderai/` ga
# QOTIRILGAN edi va u FAQAT tayyorlangan serverda mavjud. Natijada
# skriptlar HECH QACHON, HECH QAYERDA yurgizilmagan — ular faqat
# `deploy_test` da MATN sifatida tekshirilardi (114 tekshiruv,
# hammasi statik).
#
# "Yozilgan, lekin bir marta ham bajarilmagan skript" —
# joylashtirish kunidagi eng qimmat noma'lum. Endi mashq qilish
# mumkin: yo'l berilsa o'sha ishlatiladi.
#
# Standart qiymat O'ZGARMADI — serverdagi xulq bir xil qoladi.
ENVFILE="${TENDERAI_ENVFILE:-/etc/tenderai/${MUHIT}.env}"
[ -f "$ENVFILE" ] || { echo "muhit fayli yoq: $ENVFILE"; exit 2; }

set -a
# shellcheck disable=SC1090
. "$ENVFILE"
set +a

: "${XT_DB_DSN:?XT_DB_DSN kerak}"
KATALOG="${BACKUP_DIR:-/var/backups/tenderai}/${MUHIT}"
KUN="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
FAYL="${KATALOG}/tenderai-${MUHIT}-${STAMP}.dump"

mkdir -p "$KATALOG"
log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

log "zaxira boshlandi -> $FAYL"
# `--no-owner --no-privileges`: tiklash BOSHQA rol bilan ham ishlasin
# (tiklash mashqi vaqtinchalik bazaga tiklaydi).
pg_dump "$XT_DB_DSN" \
    --format=custom \
    --compress=6 \
    --no-owner --no-privileges \
    --file="$FAYL"

HAJM="$(du -h "$FAYL" | cut -f1)"
log "olindi: $HAJM"

# --- OCHILISHI DARHOL TEKSHIRILADI ------------------------------------------
# Buzuq dump faqat tiklash paytida bilinardi — yani AYNAN eng yomon
# paytda. Bu tekshiruv arzon va u shu holatni oldini oladi.
if ! pg_restore --list "$FAYL" > /dev/null 2>&1; then
    log "XATO: dump OCHILMADI — fayl ochirildi"
    rm -f "$FAYL"
    exit 1
fi
JADVALLAR="$(pg_restore --list "$FAYL" | grep -c 'TABLE DATA' || true)"
log "ochildi: $JADVALLAR ta jadval malumoti"

# Bo'sh yoki shubhali kichik dump — signal.
if [ "$JADVALLAR" -lt 10 ]; then
    log "XATO: dump ichida atigi $JADVALLAR ta jadval — shubhali, ochirildi"
    rm -f "$FAYL"
    exit 1
fi

sha256sum "$FAYL" > "${FAYL}.sha256"
log "sha256 yozildi"

# --- ESKILARINI TOZALASH ----------------------------------------------------
# Faqat SHU muhitning fayllari va faqat kutilgan naqsh boyicha.
find "$KATALOG" -maxdepth 1 -name "tenderai-${MUHIT}-*.dump*" \
     -mtime "+${KUN}" -print -delete | while read -r f; do
    log "eski zaxira ochirildi: $(basename "$f")"
done

QOLGAN="$(find "$KATALOG" -maxdepth 1 -name '*.dump' | wc -l)"
log "TUGADI. Katalogda $QOLGAN ta zaxira."
