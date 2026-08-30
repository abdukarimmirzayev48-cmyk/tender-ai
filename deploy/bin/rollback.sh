#!/usr/bin/env bash
# =============================================================================
# Tender AI — ORQAGA QAYTARISH
# =============================================================================
#     rollback.sh <staging|production> [reliz-nomi]
#     rollback.sh production --royxat      # mavjud relizlar
#
# Reliz berilmasa — OLDINGISIGA qaytadi.
#
# BAZA MIGRATSIYASI QAYTARILMAYDI va bu ATAYLAB:
#
#   - Migratsiyalar QOSHIMCHA (additive): yangi ustun yoki jadval
#     eski kodga XALAQIT BERMAYDI. Eski kod ularni bilmaydi, xolos.
#   - Avtomatik `down` skript esa MALUMOT YOQOTISHNING eng qisqa
#     yoli bolardi va u aynan falokat paytida ishga tushardi.
#   - Migratsiya haqiqatan buzuvchi bolsa — ZAXIRADAN tiklanadi.
#     Bu yol har hafta MASHQ QILINADI (restore-test.sh), yani u
#     "nazariy imkoniyat" emas.
#
# Qaytarish ATOMAR: `current` simvolik havolasi almashtiriladi.
# =============================================================================
set -euo pipefail

MUHIT="${1:?foydalanish: rollback.sh <staging|production> [reliz|--royxat]}"
ILDIZ="/opt/tenderai/${MUHIT}"
RELIZLAR="${ILDIZ}/releases"
JORIY="${ILDIZ}/current"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

[ -d "$RELIZLAR" ] || { echo "Relizlar katalogi yoq: $RELIZLAR"; exit 1; }
HOZIRGI="$(readlink -f "$JORIY" 2>/dev/null || true)"

if [ "${2:-}" = "--royxat" ]; then
    echo "Relizlar (yangisidan eskisiga):"
    ( cd "$RELIZLAR" && ls -1dt */ | sed 's#/$##' ) | while read -r r; do
        belgi=" "
        [ "${RELIZLAR}/${r}" = "$HOZIRGI" ] && belgi="*"
        echo "  ${belgi} ${r}"
    done
    echo "  (* — hozirgi)"
    exit 0
fi

HEDEF="${2:-}"
if [ -z "$HEDEF" ]; then
    # Vaqt boyicha tartiblangan royxatda HOZIRGIDAN keyingisi.
    HEDEF="$(cd "$RELIZLAR" && ls -1dt */ | sed 's#/$##' \
        | awk -v h="$(basename "$HOZIRGI")" 'p==h {print; exit} {p=$0}')"
fi

[ -n "$HEDEF" ] || { echo "Qaytariladigan reliz topilmadi"; exit 1; }
[ -d "${RELIZLAR}/${HEDEF}" ] || { echo "Yoq: ${RELIZLAR}/${HEDEF}"; exit 1; }

log "hozirgi: $(basename "$HOZIRGI")  ->  hedef: $HEDEF"
ln -sfn "${RELIZLAR}/${HEDEF}" "$JORIY"
sudo systemctl restart "tenderai-api@${MUHIT}"

if "${RELIZLAR}/${HEDEF}/deploy/bin/health-check.sh" "$MUHIT"; then
    log "QAYTARILDI: $HEDEF"
else
    log "DIQQAT: qaytarildi, LEKIN sogliq tekshiruvi otmadi — qolda qarang"
    log "  journalctl -u tenderai-api@${MUHIT} -n 100"
    exit 1
fi
