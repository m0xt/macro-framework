#!/usr/bin/env bash
# ET-aware launchd gate for macro-framework production refreshes.
#
# launchd evaluates StartCalendarInterval in the Mac's local timezone. Prague and
# New York daylight-saving transitions do not move on the same dates, so the
# checked-in plists fire at both possible Prague hours and this gate runs the
# real refresh only when America/New_York is at the requested wall-clock time.

set -euo pipefail

MODE="${1:-}"
case "$MODE" in
    data)
        TARGET_HOUR=16
        TARGET_MINUTE=00
        REFRESH_ARGS=()
        ;;
    briefs)
        TARGET_HOUR=16
        TARGET_MINUTE=05
        REFRESH_ARGS=(--briefs-only)
        ;;
    *)
        echo "usage: $0 {data|briefs}" >&2
        exit 64
        ;;
esac

ET_WEEKDAY="${MACRO_REFRESH_ET_WEEKDAY:-$(TZ=America/New_York date +%u)}"
ET_HOUR="${MACRO_REFRESH_ET_HOUR:-$(TZ=America/New_York date +%H)}"
ET_MINUTE="${MACRO_REFRESH_ET_MINUTE:-$(TZ=America/New_York date +%M)}"
ET_STAMP="${MACRO_REFRESH_ET_STAMP:-$(TZ=America/New_York date '+%Y-%m-%d %H:%M %Z')}"

if [[ "$ET_WEEKDAY" =~ ^[1-5]$ && "$ET_HOUR" == "$TARGET_HOUR" && "$ET_MINUTE" == "$TARGET_MINUTE" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ "${MACRO_REFRESH_DRY_RUN:-0}" == "1" ]]; then
        echo "ET gate matched for $MODE at $ET_STAMP; would run scripts/refresh.sh ${REFRESH_ARGS[*]-}"
        exit 0
    fi
    exec /bin/bash "$SCRIPT_DIR/refresh.sh" "${REFRESH_ARGS[@]}"
fi

echo "ET gate skipped $MODE at $ET_STAMP"
