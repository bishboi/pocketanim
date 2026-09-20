#!/usr/bin/env bash
#
# Build the player without an Android SDK.
#
# dl.google.com is blocked by this environment's network policy, so the usual
# `sdkmanager`/AGP route is unavailable. Maven Central is reachable, which is
# enough: the Kotlin compiler comes from there, and so does a real Android
# framework jar (Robolectric publishes AOSP's android.jar contents as
# org.robolectric:android-all). That is sufficient to *compile* the Android
# layer against the real android.* API -- not to run it.
#
# The gradle files alongside this script are the build anyone with an SDK
# should use. This exists so the code can be compiled and the core can be run
# and checked here, rather than shipped unverified.
#
#   ./player/build.sh          # core + desktop, and android if the jar is cached
#   ./player/build.sh --fetch  # download the toolchain first (~200 MB)
set -euo pipefail

cd "$(dirname "$0")/.."
CACHE="${PANIM_TOOLCHAIN:-$HOME/.cache/pocketanim-toolchain}"
OUT="player/build/classes"
KOTLIN=2.0.21
ANDROID_ALL=14-robolectric-10818077

fetch() {
  mkdir -p "$CACHE"
  local base=https://repo1.maven.org/maven2
  local artifacts=(
    "org/jetbrains/kotlin/kotlin-compiler-embeddable/$KOTLIN/kotlin-compiler-embeddable-$KOTLIN.jar"
    "org/jetbrains/kotlin/kotlin-stdlib/$KOTLIN/kotlin-stdlib-$KOTLIN.jar"
    "org/jetbrains/kotlin/kotlin-reflect/$KOTLIN/kotlin-reflect-$KOTLIN.jar"
    "org/jetbrains/kotlin/kotlin-script-runtime/$KOTLIN/kotlin-script-runtime-$KOTLIN.jar"
    "org/jetbrains/kotlin/kotlin-daemon-embeddable/$KOTLIN/kotlin-daemon-embeddable-$KOTLIN.jar"
    "org/jetbrains/annotations/24.1.0/annotations-24.1.0.jar"
    "org/jetbrains/kotlinx/kotlinx-coroutines-core-jvm/1.8.1/kotlinx-coroutines-core-jvm-1.8.1.jar"
    "org/jetbrains/intellij/deps/trove4j/1.0.20200330/trove4j-1.0.20200330.jar"
    "org/robolectric/android-all/$ANDROID_ALL/android-all-$ANDROID_ALL.jar"
  )
  for a in "${artifacts[@]}"; do
    local f="$CACHE/$(basename "$a")"
    [ -f "$f" ] || { echo "fetching $(basename "$a")"; curl -sSfL -o "$f" "$base/$a"; }
  done
}

if [ "${1:-}" = "--fetch" ]; then fetch; fi

STDLIB="$CACHE/kotlin-stdlib-$KOTLIN.jar"
ANDROID_JAR="$CACHE/android-all-$ANDROID_ALL.jar"

if [ ! -f "$STDLIB" ]; then
  echo "toolchain missing -- run: $0 --fetch" >&2
  echo "(looked in $CACHE; override with PANIM_TOOLCHAIN)" >&2
  exit 1
fi

# Built by hand rather than `ls | grep`: under `set -o pipefail` an empty cache
# kills the script before the check above can explain why.
COMPILER_CP=""
for jar in "$CACHE"/*.jar; do
  case "$jar" in
    *android-all*) continue ;;
  esac
  COMPILER_CP="$COMPILER_CP$jar:"
done

# Filter the noise but keep the exit status: piping through grep discards it,
# and a build script that reports success on a failed compile is worse than no
# build script at all.
kotlinc() {
  local log status
  log=$(java -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib "$@" 2>&1)
  status=$?
  printf '%s\n' "$log" | grep -viE '^warning:|Picked up JAVA_TOOL_OPTIONS' || true
  if [ $status -ne 0 ] || printf '%s' "$log" | grep -q 'error:'; then
    echo "compile failed" >&2
    exit 1
  fi
}

rm -rf "$OUT"
mkdir -p "$OUT"
cp "$STDLIB" "$OUT/kotlin-stdlib.jar"

echo "compiling core"
kotlinc -classpath "$STDLIB" player/core/src/main/kotlin -d "$OUT/core"

echo "compiling desktop harness"
kotlinc -classpath "$STDLIB:$OUT/core" player/desktop/src/main/kotlin -d "$OUT/desktop"

if [ -f "$ANDROID_JAR" ]; then
  echo "compiling android layer"
  kotlinc -classpath "$STDLIB:$ANDROID_JAR:$OUT/core" player/android/src/main/kotlin -d "$OUT/android"
else
  echo "skipping android layer (no framework jar; run $0 --fetch)" >&2
fi

echo "built into $OUT"
