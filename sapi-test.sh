#!/usr/bin/env bash
# Launch Logos with SAPI traces. Save beside wine-bisect.sh.
# Usage: ./sapi-test.sh [AppImage|Wine directory|bin|build]
# Optional: SAPI_WINEDEBUG=... SAPI_DLLOVERRIDES=... ./sapi-test.sh
set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
die() { echo "error: $*" >&2; exit 1; }

CONF=${WINE_BISECT_CONF:-}
if [[ -z $CONF ]]; then
  for c in "$SCRIPT_DIR/wine-bisect.conf" "$HOME/wine-bisect-prefix/wine-bisect.conf" "${XDG_CONFIG_HOME:-$HOME/.config}/wine-bisect/wine-bisect.conf"; do
    if [[ -f $c ]]; then CONF=$c; break; fi
  done
fi
if [[ -n $CONF ]]; then
  # shellcheck disable=SC1090
  source "$CONF"
fi
if [[ -d $SCRIPT_DIR/data/wine64_bottle ]]; then : "${INSTALL_DIR:=$SCRIPT_DIR}"; fi
: "${INSTALL_DIR:=$HOME/wine-bisect-prefix}"
: "${WORK_DIR:=${XDG_CACHE_HOME:-$HOME/.cache}/wine-bisect}"
: "${BUILD_DIR:=$WORK_DIR/build}"
: "${PRISTINE_PREFIX:=$INSTALL_DIR/data/wine64_bottle}"
: "${SAPI_WINE:=$HOME/akousousin/wine-akousousin-piper-11.21-logos-x86_64.AppImage}"
: "${SAPI_WINEDEBUG:=-all,+sapi,+winhttp,+loaddll,+timestamp,+pid}"
extra=${SAPI_DLLOVERRIDES-${WINEDLLOVERRIDES-${PRINT_DLLOVERRIDES-}}}
overrides="winemenubuilder.exe=d${extra:+;$extra};sapi=b"

# Pick Wine, retaining the template's bin/build/directory options.
target=${1:-$SAPI_WINE}
[[ $target != build ]] || target=$BUILD_DIR
[[ $target != bin ]] || target=$INSTALL_DIR/bin
target=$(readlink -e "$target") || die 'Wine target not found'
WINE='' server=''
if [[ -f $target ]]; then
  [[ -x $target ]] || die "Run chmod +x \"$target\" first"
  WINE=$target
elif [[ -x $target/wine && -x $target/server/wineserver ]]; then
  WINE=$target/wine; server=$target/server/wineserver
else
  for d in "$target/bin" "$target"; do
    if [[ -x $d/wine64 ]]; then WINE=$d/wine64;
    elif [[ -x $d/wine ]]; then WINE=$d/wine;
    else continue; fi
    [[ ! -x $d/wineserver ]] || server=$d/wineserver
    break
  done
fi
[[ -n $WINE ]] || die "No usable Wine at $target"
# Akousousin AppRun supplies its own server; do not invoke it as wineserver -w.
if [[ -n $server && $(readlink -f "$server") == "$(readlink -f "$WINE")" ]]; then server=''; fi
export WINEPREFIX=$PRISTINE_PREFIX
[[ -d $WINEPREFIX/drive_c && -f $WINEPREFIX/system.reg ]] || die "No existing prefix at $WINEPREFIX"
shopt -s nullglob
exes=("$WINEPREFIX"/drive_c/users/*/AppData/Local/Logos/Logos.exe)
[[ ${#exes[@]} -gt 0 ]] || die "Logos.exe not found in $WINEPREFIX"
exe=${exes[0]}

mkdir -p "$WORK_DIR/logs"
exec 9>>"$WORK_DIR/.lock"
flock -n 9 || die 'A bisect or diagnostic run is already in progress'
logos_running() {
  local pid
  while IFS= read -r pid; do
    if grep -zFxq "WINEPREFIX=$WINEPREFIX" "/proc/$pid/environ" 2>/dev/null; then return 0; fi
  done < <(pgrep -u "$(id -u)" -f 'Logos[.]exe' || true)
  return 1
}
if logos_running; then die 'Logos is already running in this prefix; close it first'; fi

STAMP=$(date +%Y%m%d-%H%M%S)
OUT=$WORK_DIR/logs/sapi-$STAMP
[[ ! -e $OUT ]] || OUT=$OUT-$$
mkdir -p "$OUT/logos-logs"
touch "$OUT/start.marker"
printf 'Wine: %s\nPrefix: %s\nWINEDEBUG: %s\nDLL overrides: %s\n' "$WINE" "$WINEPREFIX" "$SAPI_WINEDEBUG" "$overrides" >"$OUT/run-info.txt"
launch=(env -u WINESERVER -u WINELOADER APPIMAGE_EXTRACT_AND_RUN=1 "WINEDEBUG=$SAPI_WINEDEBUG" "WINEDLLOVERRIDES=$overrides")
[[ -z $server ]] || launch+=("WINESERVER=$server")
echo "Log: $OUT/wine.log"
echo 'Try Read Aloud, then close Logos to collect the logs.'
status=0
(cd "$(dirname "$exe")" && exec "${launch[@]}" "$WINE" "$exe") >"$OUT/wine.log" 2>&1 || status=$?
printf 'Logos/Wine exit status: %s\n' "$status" >>"$OUT/run-info.txt"
# The initial Logos.exe is a bootstrapper and can exit while System/Logos.exe
# is still running. Do not summarize or archive its inherited log prematurely.
if logos_running; then echo 'Waiting for the Logos window to close...'; fi
while logos_running; do sleep 1; done
if [[ -n $server ]]; then
  "${launch[@]}" timeout 10s "$server" -w >"$OUT/wineserver-wait.log" 2>&1 || true
fi

# The marker exists, and --parents avoids overwriting identically named logs.
find "$(dirname "$exe")" "$WINEPREFIX/drive_c/users" -maxdepth 5 -type f -iname '*.log' \
  -newer "$OUT/start.marker" -exec cp --parents -t "$OUT/logos-logs" -- {} + 2>"$OUT/collection-errors.log" || true
{
  cat "$OUT/run-info.txt"
  echo; echo 'Trace counts:'
  awk '/:trace:sapi:/{s++} /:trace:winhttp:/{h++} END{printf "SAPI: %d\nWinHTTP: %d\n",s,h}' "$OUT/wine.log"
  echo; echo 'Recent speech diagnostics:'
  { grep -iE ':sapi:.*(EnumValues|EnumKeys|GetDefaultTokenId|GetStringValue|Speak|SetVoice|piper)|:(err|warn):sapi:|:winhttp:|speak failed' "$OUT/wine.log" || true; } | tail -100
} >"$OUT/digest.txt"
tar -C "$WORK_DIR/logs" -czf "$OUT.tar.gz" "$(basename "$OUT")"
echo "Done. Send: $OUT.tar.gz"
cat "$OUT/digest.txt"
exit "$status"
