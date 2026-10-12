#!/usr/bin/env bash
# Every check of the harness, run at once.
#   scripts/check.sh          all of it: the Python tests on every core, the app's type check and checks (~2.5 min)
#   scripts/check.sh quick    the same without the slow tests that render whole lectures (~1 min)
#   scripts/check.sh quick tests/test_pictures_more.py   only these Python tests (and the app's checks)
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HERE/../.venv/bin/python"
MODE="${1:-full}"
[ "$MODE" = quick ] || [ "$MODE" = full ] || { echo "usage: $0 [quick|full] [pytest paths...]"; exit 2; }
shift || true
TESTS=("$@")
[ ${#TESTS[@]} -eq 0 ] && TESTS=(tests)
MARK=()
[ "$MODE" = quick ] && MARK=(-m "not slow")
LOG="$(mktemp -d)"

# The app's checks run beside the Python tests (a few seconds each).
(
  cd "$HERE/app" || exit 1
  status=0
  npx tsc --noEmit -p . > "$LOG/tsc.txt" 2>&1 || { echo "FAILED: tsc"; cat "$LOG/tsc.txt"; status=1; }
  for check in figures costs speed; do
    npm run -s "check:$check" > "$LOG/$check.txt" 2>&1 || { echo "FAILED: check:$check"; tail -20 "$LOG/$check.txt"; status=1; }
  done
  exit $status
) &
APP=$!

cd "$HERE/forge" || exit 1
"$PY" -m pytest -q --no-header -p no:cacheprovider -n auto --disable-warnings "${MARK[@]}" -rf "${TESTS[@]}"
PYTEST=$?
wait $APP
APPSTATUS=$?
[ $APPSTATUS -eq 0 ] && echo "app: tsc and checks ok"
rm -rf "$LOG"
exit $(( PYTEST || APPSTATUS ))
