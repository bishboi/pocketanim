#!/usr/bin/env bash
#
# Build the player APK without the Android SDK or Gradle.
#
# dl.google.com (and so maven.google.com, the SDK, AGP, d8 and Google's aapt2) is
# blocked where this project is developed; GitHub's runners build the APK with
# Gradle (.github/workflows/apk.yml). This makes the same app from parts that are
# reachable: the Kotlin compiler and the API 34 framework jar from Maven Central
# (build.sh --fetch), and aapt2, dx, zipalign and apksigner from Ubuntu's archive:
#
#   sudo apt-get install aapt dalvik-exchange zipalign apksigner
#   ./player/build.sh --fetch            # once: the Kotlin toolchain and android-all
#   ./player/build-apk.sh                # -> player/build/apk/pocketanim-player.apk
#
# The scene library is packed into the APK as the CI build does; the app also plays
# lectures imported from the web app or downloaded from Saved. Signed with a debug
# key kept in ~/.android (made on first use), enough to install by hand.
set -euo pipefail

cd "$(dirname "$0")/.."
CACHE="${PANIM_TOOLCHAIN:-$HOME/.cache/pocketanim-toolchain}"
KOTLIN=2.0.21
ANDROID_JAR="$CACHE/android-all-14-robolectric-10818077.jar"
STDLIB="$CACHE/kotlin-stdlib-$KOTLIN.jar"
OUT="player/build/apk"
WORK="$OUT/work"
PYTHON="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"

for tool in aapt2 dalvik-exchange zipalign apksigner keytool java; do
  command -v "$tool" > /dev/null || { echo "missing $tool (sudo apt-get install aapt dalvik-exchange zipalign apksigner)" >&2; exit 1; }
done
[ -f "$ANDROID_JAR" ] && [ -f "$STDLIB" ] || { echo "toolchain missing: run player/build.sh --fetch" >&2; exit 1; }

COMPILER_CP=""
for jar in "$CACHE"/*.jar; do
  case "$jar" in *android-all*) continue ;; esac
  COMPILER_CP="$COMPILER_CP$jar:"
done

rm -rf "$WORK"
mkdir -p "$WORK/classes" "$WORK/assets"

echo "packing the scene library"
"$PYTHON" -m tools.build_library --out "$WORK/assets/library" > "$WORK/library.log"

# The Supabase project Saved lists, when given (the anon key is public by design): otherwise the app asks
# for it the first time Saved is tapped.
if [ -n "${PANIM_SUPABASE_URL:-}" ] && [ -n "${PANIM_SUPABASE_ANON_KEY:-}" ]; then
  printf '{"url": "%s", "anon_key": "%s"}\n' "$PANIM_SUPABASE_URL" "$PANIM_SUPABASE_ANON_KEY" > "$WORK/assets/supabase.json"
fi

# Java 8 bytecode, lambdas as classes: dx reads class files up to version 52 and
# does not translate invokedynamic lambdas the way d8 does.
echo "compiling core, android layer and app"
set +e
log=$(java -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -jvm-target 1.8 \
  -Xlambdas=class -Xsam-conversions=class -Xstring-concat=inline \
  -classpath "$STDLIB:$ANDROID_JAR" -d "$WORK/classes" \
  player/core/src/main/kotlin player/android/src/main/kotlin player/app/src/main/kotlin 2>&1)
status=$?
set -e
printf '%s\n' "$log" | grep -viE '^warning:|Picked up JAVA_TOOL_OPTIONS' || true
if [ $status -ne 0 ] || printf '%s' "$log" | grep -q 'error:'; then echo "compile failed" >&2; exit 1; fi

# The standard library without its Java 9+ module descriptors, which dx cannot read.
mkdir -p "$WORK/stdlib"
(cd "$WORK/stdlib" && unzip -q "$STDLIB" -x 'META-INF/versions/*' 'META-INF/*.kotlin_module')

echo "dexing"
dalvik-exchange --dex --min-sdk-version=26 --output="$WORK/classes.dex" "$WORK/classes" "$WORK/stdlib"

echo "linking the manifest"
# The Gradle build supplies the package as the namespace; aapt2 needs it in the manifest, to resolve
# ".PlayerActivity" against.
sed 's|<manifest xmlns:android="http://schemas.android.com/apk/res/android">|<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.pocketanim.player">|' \
  player/app/src/main/AndroidManifest.xml > "$WORK/AndroidManifest.xml"
aapt2 link -o "$WORK/unsigned.apk" -I "$ANDROID_JAR" \
  --manifest "$WORK/AndroidManifest.xml" \
  --min-sdk-version 29 --target-sdk-version 34 --version-code 1 --version-name 1.0 \
  -A "$WORK/assets"
(cd "$WORK" && zip -q -j unsigned.apk classes.dex)

zipalign -f -p 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"

KEY="$HOME/.android/debug.keystore"
if [ ! -f "$KEY" ]; then
  mkdir -p "$(dirname "$KEY")"
  keytool -genkeypair -keystore "$KEY" -storepass android -keypass android -alias androiddebugkey \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US" > /dev/null
fi
apksigner sign --ks "$KEY" --ks-pass pass:android --key-pass pass:android \
  --min-sdk-version 29 --out "$OUT/pocketanim-player.apk" "$WORK/aligned.apk"
apksigner verify "$OUT/pocketanim-player.apk"
ls -lh "$OUT/pocketanim-player.apk"
