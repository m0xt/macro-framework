#!/usr/bin/env bash
# ET-aware dry-runable gate for macro-framework refreshes.
#
# Hermes Desktop cron is the production source of truth and invokes the refresh
# path on UTC schedules. This helper remains for local/manual checks and legacy
# launchd use where a New York wall-clock guard is useful.

set -euo pipefail

MODE="${1:-}"
case "$MODE" in
    data)
        TARGET_WEEKDAY_REGEX='^[1-7]$'
        TARGET_HOUR=16
        TARGET_MINUTE=00
        REFRESH_ARGS=()
        ;;
    briefs)
        TARGET_WEEKDAY_REGEX='^1$'
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

if [[ "$ET_WEEKDAY" =~ $TARGET_WEEKDAY_REGEX && "$ET_HOUR" == "$TARGET_HOUR" && "$ET_MINUTE" == "$TARGET_MINUTE" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ "${MACRO_REFRESH_DRY_RUN:-0}" == "1" ]]; then
        echo "ET gate matched for $MODE at $ET_STAMP; would run scripts/refresh.sh ${REFRESH_ARGS[*]-}"
        exit 0
    fi
    exec /bin/bash "$SCRIPT_DIR/refresh.sh" ${REFRESH_ARGS[@]+"${REFRESH_ARGS[@]}"}
fi

echo "ET gate skipped $MODE at $ET_STAMP"
