#!/usr/bin/env bash
#
# The iOS port's core against the Android player's: the same scenes through both, their text diffed.
#
# PanimVerify (ios/Sources/PanimVerify, Swift, over PanimCore) and the Kotlin desktop Verify (player/desktop, over
# player/core) each print, for one scene,
#   dump    the canonical dump: header, quantisation box, atlas, records, then one frame's instances in full;
#   trace   every PathSink call the renderer makes for a list of frames (moveTo/lineTo/cubicTo/closeSubpath,
#           fill/stroke/fillAndStroke with colour and width, strokeStyle, drawImage), floats to four places, and
#           each frame's content key;
#   library a library's integrity check and per-scene table, as the phone opens it through its manifest.
# Any byte of difference between the two is a failure: the port must decode, interpret and draw exactly as the
# player it was ported from does.
#
# What it runs them on:
#   - every program in dsl/generated (2D, 3D, surfaces, text, morphs, lags), dumped and traced, some also in a
#     shuffled frame order (seeking back and forth through the checkpoints) and with each renderer option set;
#   - ios/scripts/crosscheck/Exercise.panim and Exercise3D.panim: the verbs, raster pictures, drifts and 3D paths
#     (zoom moves, spins about phi, a surface using every function) no corpus program reaches;
#   - every sampled asset (version 1) in dsl/generated/assets and in the fixture library, and the glyph atlases;
#   - player/fixtures/streamed-lecture, a packed phone library (clips, chapters), opened through its manifest;
#   - a library packed here by tools.build_library from dsl/generated: version 2 (compact) shapes in one
#     assets.pack, opened through the manifest, and each packed shape on its own.
#
#   ios/scripts/crosscheck.sh                    # builds both sides first
#   CROSSCHECK_NO_BUILD=1 ios/scripts/crosscheck.sh
#   CROSSCHECK_OUT=/some/dir ios/scripts/crosscheck.sh   # keep the outputs (default: a temporary directory)
#   CROSSCHECK_VERBOSE=1 ...                             # list every check, not only the ones that differ
#   CROSSCHECK_JOBS=N ...                                # checks run at once (default: the processor count)
#
# Exits nonzero when anything differs, or either side fails where the other does not.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
OUT="${CROSSCHECK_OUT:-$(mktemp -d)}"
mkdir -p "$OUT"
SCRATCH="${PANIM_SWIFT_SCRATCH:-.build-crosscheck}"
PYTHON="${PANIM_PYTHON:-$REPO/.venv/bin/python}"

if ! command -v swift >/dev/null 2>&1 || [ "$(uname)" = Linux ]; then
  # shellcheck source=/dev/null
  source "$REPO/ios/scripts/linux-swift.sh"
fi

if [ "${CROSSCHECK_NO_BUILD:-0}" != 1 ]; then
  echo "building the Kotlin player (player/build.sh)"
  bash "$REPO/player/build.sh" >"$OUT/build-kotlin.log" 2>&1 || { cat "$OUT/build-kotlin.log"; exit 1; }
  echo "building PanimVerify (release)"
  (cd "$REPO/ios" && swift build -c release --scratch-path "$SCRATCH" --product PanimVerify) \
    >"$OUT/build-swift.log" 2>&1 || { cat "$OUT/build-swift.log"; exit 1; }
fi

CLASSES="$REPO/player/build/classes"
KOTLIN=(java -cp "$CLASSES/core:$CLASSES/desktop:$CLASSES/kotlin-stdlib.jar" com.pocketanim.desktop.VerifyKt)
SWIFT=("$REPO/ios/$SCRATCH/release/PanimVerify")

JOBS="${CROSSCHECK_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
RESULTS="$OUT/results"
rm -rf "$RESULTS"
mkdir -p "$RESULTS"
TAGS=()
SECTIONS=()
CURRENT_SECTION=""

# run_check <tag> <label> <verify args...>: both sides, stdout and exit status compared; the verdict (its first
# line the Kotlin side's line count) into $RESULTS/<tag>.
run_check() {
  local tag="$1" label="$2"
  shift 2
  local k="$OUT/$tag.kotlin" s="$OUT/$tag.swift" ks=0 ss=0 n
  "${KOTLIN[@]}" "$@" >"$k" 2>"$k.err" || ks=$?
  "${SWIFT[@]}" "$@" >"$s" 2>"$s.err" || ss=$?
  n=$(wc -l <"$k" | tr -d ' ')
  {
    echo "$n"
    if [ "$ks" != "$ss" ]; then
      echo "FAIL $label: exit $ks (Kotlin) vs $ss (Swift)"
      { tail -n 3 "$k.err"; tail -n 3 "$s.err"; } | grep -v JAVA_TOOL_OPTIONS | sed 's/^/     /' || true
    elif ! cmp -s "$k" "$s"; then
      echo "DIFF $label ($( (diff "$k" "$s" || true) | grep -c '^[<>]' || true) line(s) differ, of $n)"
      (diff "$k" "$s" || true) | head -n 8 | sed 's/^/     /'
    else
      echo "ok   $label ($n lines$([ "$ks" = 0 ] || echo ", both exit $ks"))"
    fi
  } >"$RESULTS/$tag"
}

# check <label> <verify args...>: queued, at most $JOBS at once.
check() {
  local label="$1"
  shift
  local tag
  tag="$(printf '%04d-%s' "${#TAGS[@]}" "$label" | tr -c 'A-Za-z0-9._-' '_')"
  TAGS+=("$tag")
  SECTIONS+=("$CURRENT_SECTION")
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 0.05; done
  run_check "$tag" "$label" "$@" &
}

# Frame count of a scene, from its dump header (the frames field of H).
frame_count() {
  "${SWIFT[@]}" "$1" dump 0 | awk '/^H /{print $3; exit}'
}

# A shuffled list of frames (a fixed seed), then the same backwards: seeking about rather than playing on.
shuffled() {
  python3 -c "import random,sys; n=int(sys.argv[1]); r=random.Random(7); f=r.sample(range(n), min(n, 40)); print(','.join(map(str, f + f[::-1][:10] + [0, n - 1, n // 2])))" "$1"
}

section() {
  CURRENT_SECTION="$1"
  echo "-- $1"
}

# ---- programs --------------------------------------------------------------------------------------------------
section "programs (dsl/generated/*.panim): dump, trace"
for program in dsl/generated/*.panim; do
  name="$(basename "$program" .panim)"
  check "dump $name" "$program" dump
  check "dump $name @0" "$program" dump 0
  check "trace $name" "$program" trace every:7
done

section "programs: frames sought out of order"
for name in HelloPocketanim LongLesson LectureEngine CodeWalkthrough ThreeDCamera SurfaceOrbit; do
  program="dsl/generated/$name.panim"
  check "trace $name shuffled" "$program" trace "$(shuffled "$(frame_count "$program")")"
done

section "programs: every renderer option set"
for name in CartopyMap MolecularStructure LectureEngine ConcurrentPlay; do
  for options in default all no-lines no-cull no-merge no-backface bevel no-merge-fade no-lod lod-1px; do
    check "trace $name $options" "dsl/generated/$name.panim" trace every:23 "$options"
  done
done

# ---- the exercise program ---------------------------------------------------------------------------------------
section "Exercise.panim, Exercise3D.panim (verbs, pictures, drifts, 3D paths the corpus does not use)"
EX="$OUT/exercise"
rm -rf "$EX"
mkdir -p "$EX/images"
cp "$REPO/ios/scripts/crosscheck/Exercise.panim" "$EX/"
ln -s "$REPO/dsl/generated/assets" "$EX/assets"
ln -s "$REPO/dsl/generated/library.atlas" "$EX/library.atlas"
printf '\x89PNG\r\n\x1a\n' >"$EX/images/pic.png"
check "dump Exercise" "$EX/Exercise.panim" dump
check "dump Exercise @40" "$EX/Exercise.panim" dump 40
check "trace Exercise" "$EX/Exercise.panim" trace every:2
check "trace Exercise shuffled" "$EX/Exercise.panim" trace "$(shuffled "$(frame_count "$EX/Exercise.panim")")"
check "trace Exercise default" "$EX/Exercise.panim" trace every:5 default
cp "$REPO/ios/scripts/crosscheck/Exercise3D.panim" "$EX/"
check "dump Exercise3D" "$EX/Exercise3D.panim" dump
check "trace Exercise3D" "$EX/Exercise3D.panim" trace every:2
check "trace Exercise3D shuffled" "$EX/Exercise3D.panim" trace "$(shuffled "$(frame_count "$EX/Exercise3D.panim")")"
for options in default no-backface bevel no-lines; do
  check "trace Exercise3D $options" "$EX/Exercise3D.panim" trace every:6 "$options"
done

# ---- sampled assets (version 1) -------------------------------------------------------------------------------
section "sampled assets, version 1 (dsl/generated, the fixture library) and glyph atlases"
for asset in dsl/generated/assets/*.panm player/fixtures/streamed-lecture/assets/*.panm; do
  check "dump $asset" "$asset" dump
done
check "dump dsl/generated/library.atlas" dsl/generated/library.atlas dump
check "dump fixture library.atlas" player/fixtures/streamed-lecture/library.atlas dump

# ---- the fixture library ----------------------------------------------------------------------------------------
section "player/fixtures/streamed-lecture (a packed phone library)"
LIB=player/fixtures/streamed-lecture
check "library streamed-lecture" "$LIB" library
check "dump streamed-lecture" "$LIB" dump
check "dump streamed-lecture @1000" "$LIB" dump 1000
check "trace streamed-lecture" "$LIB" trace every:9
check "trace streamed-lecture shuffled" "$LIB" trace "$(shuffled "$(frame_count "$LIB")")"

# ---- a version 2 library ----------------------------------------------------------------------------------------
section "a library packed by tools.build_library (version 2 shapes in assets.pack)"
V2="$OUT/library-v2"
rm -rf "$V2"
"$PYTHON" -m tools.build_library --source dsl/generated --out "$V2" >"$OUT/build-library.log" 2>&1 \
  || { cat "$OUT/build-library.log"; exit 1; }
check "library v2" "$V2" library
for program in "$V2"/scenes/*.panim; do
  name="$(basename "$program" .panim)"
  check "dump v2 $name" "$V2#$name" dump
  check "trace v2 $name" "$V2#$name" trace every:11
done
# Each packed shape on its own, so the compact decoder is compared field for field (point elision, rounding
# shift, flat scenes, the delta-coded instances).
mkdir -p "$V2-shapes"
python3 - "$V2" "$V2-shapes" <<'PY'
import json, sys
root, out = sys.argv[1], sys.argv[2]
manifest = json.load(open(f"{root}/library.json"))
pack = manifest["asset_pack"]
data = open(f"{root}/{pack['path']}", "rb").read()
for shape, (offset, length) in pack["index"].items():
    open(f"{out}/{shape}.panm", "wb").write(data[offset:offset + length])
PY
versions=$(python3 -c "import glob,struct,collections; print(dict(collections.Counter(struct.unpack('<IH', open(p,'rb').read(6))[1] for p in glob.glob('$V2-shapes/*.panm'))))")
echo "   packed shapes by container version: $versions"
for asset in "$V2-shapes"/*.panm; do
  check "dump v2 shape $(basename "$asset")" "$asset" dump
done

# ---- summary ---------------------------------------------------------------------------------------------------
wait
checks=0
failures=0
lines=0
FAILED=()
echo
for i in "${!TAGS[@]}"; do
  result="$RESULTS/${TAGS[$i]}"
  n=$(head -n 1 "$result")
  checks=$((checks + 1))
  lines=$((lines + n))
  if sed -n 2p "$result" | grep -q '^ok '; then
    [ "${CROSSCHECK_VERBOSE:-0}" = 1 ] && sed -n 2p "$result"
  else
    failures=$((failures + 1))
    FAILED+=("$(sed -n 2p "$result" | cut -c6-)")
    tail -n +2 "$result"
  fi
done

echo "summary by section:"
previous=""
for i in "${!TAGS[@]}"; do
  section_name="${SECTIONS[$i]}"
  [ "$section_name" = "$previous" ] && continue
  previous="$section_name"
  total=0
  bad=0
  count=0
  for j in "${!TAGS[@]}"; do
    [ "${SECTIONS[$j]}" = "$section_name" ] || continue
    count=$((count + 1))
    total=$((total + $(head -n 1 "$RESULTS/${TAGS[$j]}")))
    sed -n 2p "$RESULTS/${TAGS[$j]}" | grep -q '^ok ' || bad=$((bad + 1))
  done
  printf '  %-72s %4d checks %10d lines  %s\n' "$section_name" "$count" "$total" \
    "$([ "$bad" = 0 ] && echo identical || echo "$bad DIFFERENT")"
done
echo "crosscheck: $checks checks, $lines lines of Kotlin output compared, $failures differing"
echo "outputs in $OUT"
if [ "$failures" -gt 0 ]; then
  printf '  failed: %s\n' "${FAILED[@]}"
  exit 1
fi
echo "OK: the Swift core and the Kotlin core agree byte for byte"
