#!/usr/bin/env bash
# Clear everything the harness has cached or kept from earlier runs, so the next lecture is made from scratch.
#
#   harness/scripts/clear_all.sh                 # this machine's caches and history (asks first)
#   harness/scripts/clear_all.sh --supabase      # ...and the generation history kept in Supabase
#   harness/scripts/clear_all.sh --supabase --saved   # ...and the SAVED lectures the phone lists (cannot be undone)
#   harness/scripts/clear_all.sh --dry-run       # only show what would go
#   harness/scripts/clear_all.sh --yes           # do not ask
#
# On this machine it removes: pictures made by the image model, SVG drawings, PDF and YouTube sources, geocoded
# places, icons, the SVG lab's runs (harness/lecture/.cache); Manim's text and LaTeX renders (harness/.cache);
# Forge jobs and its cache; the web app's finished builds (.jobs), narration (.voice) and Next.js build cache
# (.next); rendered videos (media/, corpus/renders); Python bytecode and pytest caches.
#
# It keeps what was downloaded once and is not history: the Python venv, node_modules, voice weights
# (harness/models), the gazetteer, icon and illustration libraries, TinyTeX, and .env files.
#
# The web page's own history (lecture versions and settings kept in the browser) is cleared by opening
# http://localhost:3000/reset in that browser.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUPABASE=0 SAVED=0 DRY=0 YES=0
for arg in "$@"; do
  case "$arg" in
    --supabase) SUPABASE=1 ;;
    --saved) SUPABASE=1 SAVED=1 ;;
    --dry-run) DRY=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

TARGETS=(
  "harness/lecture/.cache"
  "harness/.cache"
  "harness/forge/jobs"
  "harness/forge/cache"
  "harness/app/.jobs"
  "harness/app/.voice"
  "harness/app/.next"
  "media"
  "corpus/renders"
)

echo "Clearing caches and history in $REPO"
found=()
for t in "${TARGETS[@]}"; do
  if [ -e "$REPO/$t" ]; then
    found+=("$t")
    printf '  %-28s %s\n' "$t" "$(du -sh "$REPO/$t" 2>/dev/null | cut -f1)"
  fi
done
pycache_count=$(find "$REPO" \( -name node_modules -o -name .venv -o -name .git \) -prune -o \
  \( -name __pycache__ -o -name .pytest_cache \) -type d -print 2>/dev/null | wc -l | tr -d ' ')
echo "  __pycache__ / .pytest_cache  $pycache_count folders"
[ "$SUPABASE" = 1 ] && echo "  Supabase: generation history (generations, media, scenes, programs; bucket 'media')"
[ "$SAVED" = 1 ] && echo "  Supabase: SAVED lectures (projects, scenes, builds, assets; bucket 'lectures')"

if [ "$DRY" = 1 ]; then
  echo "(dry run: nothing removed)"
  exit 0
fi
if [ "$YES" != 1 ]; then
  read -r -p "Remove all of this? [y/N] " answer
  case "$answer" in y|Y|yes|YES) ;; *) echo "Nothing removed."; exit 1 ;; esac
fi

for t in "${found[@]}"; do
  rm -rf -- "${REPO:?}/$t"
done
find "$REPO" \( -name node_modules -o -name .venv -o -name .git \) -prune -o \
  \( -name __pycache__ -o -name .pytest_cache \) -type d -print0 2>/dev/null | xargs -0 rm -rf --
echo "Local caches and history cleared."

if [ "$SUPABASE" = 1 ]; then
  (cd "$REPO/harness/app" && node scripts/clear-supabase.mjs $([ "$SAVED" = 1 ] && echo --saved))
fi

echo "To clear the web page's history too, open http://localhost:3000/reset in the browser you use."
