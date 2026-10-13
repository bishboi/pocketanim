#!/usr/bin/env bash
#
# Drive the player on an emulator and keep what it showed: screenshots of each screen, a screen recording, the log.
# Run by the player-ui workflow against an emulator, with tools.mock_saved_lectures serving
# player/fixtures/streamed-lecture as two saved lectures at http://10.0.2.2:8787 (the host, from the emulator).
#
#   bash player/ui-test.sh <apk> <out dir>
#
# It fails when the app crashes, when the picture does not move while playing, or when a screen it expects does
# not come up. The screenshots are for a person to look at: they are the review.
set -uo pipefail

APK="$1"
OUT="$2"
PKG=com.pocketanim.player
mkdir -p "$OUT"
FAILED=0

REPORT=""
log() { echo "== $*"; REPORT="$REPORT== $*"$'\n'; }
fail() { echo "FAIL: $*"; REPORT="$REPORT FAIL: $*"$'\n'; FAILED=1; }
report() {
  log "done (failed=$FAILED)"
  [ -f "$OUT/logcat.txt" ] || adb logcat -d > "$OUT/logcat.txt" 2>/dev/null || touch "$OUT/logcat.txt"
  # As annotations too, which GitHub's API returns (the run's log and artifact are served from elsewhere): what each
  # step found, the crash if there was one, and the app's own errors and warnings.
  annotate() { python3 -c 'import sys; t=sys.stdin.read()[:60000]; print(t.replace("%","%25").replace("\r","").replace("\n","%0A"), end="")'; }
  echo "::notice title=player-ui steps::$(printf '%s' "$REPORT" | annotate)"
  if grep -q "FATAL EXCEPTION" "$OUT/logcat.txt"; then
    echo "::error title=player-ui crash::$(grep -A 40 "FATAL EXCEPTION" "$OUT/logcat.txt" | head -60 | annotate)"
  fi
  PID_LINES=$(grep -E " [EW] (AndroidRuntime|pocketanim|panim|PlayerActivity|LibraryActivity|MediaExtractor|AudioTrack|NuMediaExtractor)" "$OUT/logcat.txt" | tail -60)
  [ -n "$PID_LINES" ] && echo "::notice title=player-ui log::$(printf '%s' "$PID_LINES" | annotate)"
}
trap report EXIT

shot() { adb exec-out screencap -p > "$OUT/$1.png"; log "screenshot $1"; }

# The centre of the first view whose text or description contains $1, from a UI dump ("x y"), or nothing.
find_view() {
  # A dump that fails (the screen never idle while the picture plays) must not leave the last one to be read.
  rm -f "$OUT/ui.xml"
  for _ in 1 2 3; do
    adb shell rm -f /sdcard/ui.xml
    adb shell uiautomator dump /sdcard/ui.xml 2>&1 | grep -q "dumped to" && \
      adb pull /sdcard/ui.xml "$OUT/ui.xml" > /dev/null 2>&1 && break
    sleep 1
  done
  python3 - "$OUT/ui.xml" "$1" <<'PY'
import re, sys, xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
except Exception:
    sys.exit(0)
for node in root.iter("node"):
    if sys.argv[2] in node.get("text", "") or sys.argv[2] in node.get("content-desc", ""):
        x0, y0, x1, y1 = map(int, re.findall(r"\d+", node.get("bounds", "")))
        print((x0 + x1) // 2, (y0 + y1) // 2)
        break
PY
}

# What the screen says: its texts and descriptions, in reading order, into the report.
screen_text() {
  rm -f "$OUT/ui-$1.xml"
  adb shell rm -f /sdcard/ui.xml
  adb shell uiautomator dump /sdcard/ui.xml 2>&1 | grep -q "dumped to" && \
    adb pull /sdcard/ui.xml "$OUT/ui-$1.xml" > /dev/null 2>&1
  local said
  said=$(python3 - "$OUT/ui-$1.xml" <<'PY'
import sys, xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
except Exception:
    print("(no UI dump)")
    sys.exit(0)
bits = []
for node in root.iter("node"):
    t = node.get("text") or ""
    d = node.get("content-desc") or ""
    if t or d:
        bits.append(t if t else "[" + d + "]")
print(" | ".join(bits)[:1500])
PY
)
  log "$1 shows: $said"
}

tap_view() {
  local at
  at=$(find_view "$1")
  if [ -z "$at" ]; then
    fail "no view showing \"$1\""
    cp "$OUT/ui.xml" "$OUT/ui-missing-$(echo "$1" | tr -c 'A-Za-z0-9' '_').xml" 2>/dev/null || true
    return 1
  fi
  adb shell input tap $at
  log "tapped \"$1\" at $at"
}

size=$(adb shell wm size | grep -oE '[0-9]+x[0-9]+' | tail -1)
W=${size%x*}
H=${size#*x}
log "screen ${W}x${H}"

# Steady screens: no window animations, upright, and the log empty before the app starts.
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 0
adb logcat -c

adb install -r "$APK" || { fail "install"; exit 1; }
adb shell screenrecord --time-limit 170 /sdcard/run.mp4 &
RECORDER=$!

log "the library"
adb shell am start -W -n $PKG/.LibraryActivity
sleep 8
shot 01-library-saved
screen_text 01-library-saved

log "a saved lecture, streamed"
tap_view "Part 1 of the series" || adb shell input tap $((W / 2)) $((H / 4))
sleep 1.5
shot 02-player-opening
sleep 5
shot 03-player-playing
screen_text 03-player-playing
sleep 3
shot 04-player-playing-later
# The picture moved between the two: it is playing, not stuck on a frame.
python3 - "$OUT/03-player-playing.png" "$OUT/04-player-playing-later.png" <<'PY' || fail "the picture did not change while playing"
import hashlib, sys
a, b = (hashlib.md5(open(p, "rb").read()).hexdigest() for p in sys.argv[1:3])
sys.exit(0 if a != b else 1)
PY

log "the controls"
adb shell input tap $((W / 2)) $((W * 9 / 32))
sleep 0.8
shot 05-player-controls
screen_text 05-player-controls
tap_view "Playback speed" && sleep 1 && shot 06-speed && { tap_view "1.5×" || adb shell input keyevent KEYCODE_BACK; }
sleep 1
adb shell input tap $((W / 2)) $((W * 9 / 32))
sleep 0.8
tap_view "Chapters" && sleep 1 && shot 07-chapters && { tap_view "A formula map" || adb shell input keyevent KEYCODE_BACK; }
sleep 2
shot 08-after-chapter-jump

log "the whole screen"
adb shell settings put system user_rotation 1
sleep 3
shot 09-landscape
screen_text 09-landscape
adb shell input tap $((H / 2)) $((W / 4))
sleep 0.8
shot 10-landscape-controls
log "double tap to go back ten seconds"
adb shell input tap $((H / 6)) $((W / 2)); sleep 0.08; adb shell input tap $((H / 6)) $((W / 2))
sleep 0.4
shot 11-double-tap-back

log "the end of the lecture"
sleep 32
shot 12-end-card
screen_text 12-end-card
adb shell settings put system user_rotation 0
sleep 2
shot 13-end-card-portrait

log "back to the library"
adb shell input keyevent KEYCODE_BACK
sleep 2
shot 14-library-after
screen_text 14-library-after
tap_view "On this phone" && sleep 1.5 && shot 15-on-this-phone
tap_view "Samples" && sleep 1.5 && shot 16-samples
screen_text 16-samples
tap_view "Hello Pocketanim" && sleep 4 && shot 17-sample-playing
screen_text 17-sample-playing

log "what the system says"
adb shell dumpsys audio > "$OUT/dumpsys-audio.txt" 2>&1
adb shell dumpsys activity top > "$OUT/activity-top.txt" 2>&1
kill $RECORDER 2>/dev/null
sleep 2
adb pull /sdcard/run.mp4 "$OUT/run.mp4" > /dev/null 2>&1 || true
adb logcat -d > "$OUT/logcat.txt"
if grep -q "FATAL EXCEPTION" "$OUT/logcat.txt"; then
  fail "the app crashed"
  grep -A 30 "FATAL EXCEPTION" "$OUT/logcat.txt" | head -60
fi
grep -iE "pocketanim|panim" "$OUT/logcat.txt" | tail -80 > "$OUT/logcat-app.txt" || true

exit $FAILED
