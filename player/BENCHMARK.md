# Running the device gate

This answers [#6](https://github.com/bishboi/pocketanim/issues/6): **can a
floor-segment phone render these scenes live at 30 fps?** It is the one
measurement that can invalidate the architecture, because there is no MP4
fallback to retreat to.

---

## The short way: download the APK from CI

The environment this project is developed in cannot reach `dl.google.com`, so it
has no Android SDK. GitHub's runners do, so `.github/workflows/apk.yml` builds
the APK there on every push to `player/` and attaches it to the run.

1. Open the [**apk** workflow runs](https://github.com/bishboi/pocketanim/actions/workflows/apk.yml)
   and pick the newest green one.
2. Download the `pocketanim-benchmark-<sha>` artifact — it is a zip containing
   `benchmark-release.apk`.
3. Install and run:

```bash
unzip pocketanim-benchmark-*.zip
adb install -r benchmark-release.apk
adb shell am start -n com.pocketanim.benchmark/.BenchmarkActivity
adb logcat -s panim:I
```

**No adb?** Copy the APK to the phone, allow installs from your file manager,
and tap it. Results render on screen as well as to logcat — a screenshot of the
final table is a perfectly good report.

With adb, the machine-readable copy is worth having:

```bash
adb shell run-as com.pocketanim.benchmark cat files/benchmark.json > device.json
```

The APK carries the **ten tier-1 scenes** (~2 MB of assets). `PlotGeometry` is
absent: it is the one scene that cannot be expressed as a program, and its
365 kB sampled container is not versioned. Nothing is lost for this measurement
— the gate is about whether live rendering keeps up, and the tier-3 path is a
fallback rather than the thing being tested.

---

## The long way: build it yourself

Worth doing if you want to change scenes or iterate quickly.

## 1. Get the toolchain

You need a JDK 17+ and the Android SDK. Either is fine:

**Android Studio** — install it, open `player/` as a project, let it sync. It
will fetch the SDK and the Gradle plugin itself.

**Command line only:**

```bash
# cmdline-tools from https://developer.android.com/studio#command-line-tools-only
export ANDROID_HOME="$HOME/Android/Sdk"
mkdir -p "$ANDROID_HOME/cmdline-tools"
unzip commandlinetools-*.zip -d "$ANDROID_HOME/cmdline-tools"
mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools"

sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

## 2. Put the library in the app

The scenes ship inside the APK, so a run needs no network and nothing can
perturb it mid-measurement.

```bash
python -m tools.build_library --out player/benchmark/src/main/assets/library
```

That writes ~1.9 MB: eleven scenes, of which ten are tier-1 programs totalling
under 4 kB, plus the shared geometry they reference.

## 3. Build and install

```bash
cd player
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew :benchmark:assembleRelease

adb devices                                   # confirm the phone is listed
adb install -r benchmark/build/outputs/apk/release/benchmark-release.apk
```

Build **release**, not debug. A debug build has assertions on and optimisation
off, and reports frame times that mean nothing.

Enable *Developer options → USB debugging* on the phone first.

## 4. Run it

```bash
adb shell am start -n com.pocketanim.benchmark/.BenchmarkActivity
adb logcat -c && adb logcat -s panim:I
```

Results appear on screen and in logcat as they go. Let it finish — it runs every
scene three times over (warm-up, unpaced, paced) and takes a few minutes.

Then pull the machine-readable copy:

```bash
adb shell run-as com.pocketanim.benchmark cat files/benchmark.json > device.json
```

Send me `device.json` and I can compare it against the desktop reference
directly.

**Useful variations:**

```bash
# One scene, or a few. The interesting extremes are MolecularStructure
# (5,120 draw calls/frame) and CartopyMap (62,054 path verbs/frame).
adb shell am start -n com.pocketanim.benchmark/.BenchmarkActivity \
  --es scenes "MolecularStructure CartopyMap"

# A library pushed to the device instead of the one baked into the APK,
# so scenes can be swapped without rebuilding.
adb push library /sdcard/panim-library
adb shell am start -n com.pocketanim.benchmark/.BenchmarkActivity \
  --es library /sdcard/panim-library
```

---

## What the output means

```
scene                verdict  p50    p95    p99 ms   late n/N (%)   geom   draws  maxpath
MolecularStructure   FAIL     41.2   58.9   72.1     201/271 (74%)  18.30  5120   10
```

- **p95 and p99, not the mean.** Dropping one frame in fifty is invisible; the
  same mean with a fat tail is a visible stutter every second. The budget is
  33.3 ms at 30 fps.
- **late n/N** is the verdict: frames not presented by the time the next was
  due. `PASS` under 1%, `MARGINAL` under 5%, `FAIL` above.
- **geom** is the same frame with rasterisation removed — decode, transform,
  project, depth sort, shade. If `geom` is most of `p50`, the maths is the
  problem. If it is a sliver, the rasteriser is, and then `draws` is the number
  to look at.
- **draws** is `drawPath` calls per frame. On desktop, MolecularStructure issues
  5,120 — 154,000/second at 30 fps. [flutter/flutter#192147](https://github.com/flutter/flutter/issues/192147)
  measured per-draw CPU overhead making Impeller 2–3× slower than Skia on an
  Adreno 610, so this is the number most likely to decide the result.
- **maxpath** is the largest single path. Past Skia's 16,384-verb
  `kMaxGPUPathRendererVerbs` the path rasterises on the CPU. The corpus peaks at
  10,298, so this should stay well clear — if it does not, something regressed.

## A desktop reference to compare against

The identical procedure runs here, against Java2D rather than Skia:

```bash
./player/build.sh --fetch          # once
python -m tools.build_library --out library
java -cp player/build/classes/core:player/build/classes/desktop:player/build/classes/kotlin-stdlib.jar \
  com.pocketanim.desktop.VerifyKt library devicebench
```

Same warm-up, same three passes, same percentiles. It is a reference, not a
prediction — Java2D is not Skia and a desktop CPU is not a phone SoC. What
transfers is the *shape*: which scenes are expensive, and how much of their cost
is geometry rather than rasterisation.

## If it fails

A `FAIL` is a result, not a setback — it is precisely what this gate exists to
find, and finding it now is far cheaper than after the format is frozen. The
responses, in the order they should be considered:

1. **Which scenes fail?** If only MolecularStructure and CartopyMap do, the
   corpus was built to include the two hardest cases on purpose and eight
   ordinary scenes are fine.
2. **Is it draws or geometry?** The `geom` column decides. Draw-bound points at
   the depth-tested layer §3.6 defers, or interpolated vertex colours so a solid
   is one draw rather than 144 — batching by colour does *not* help, which was
   measured (§11).
3. **Render-to-cache on first open** — the fallback #6 names. Trades instant
   start and device storage for feasibility, and needs no format change.

## Please also record

The numbers are worth little without the device attached to them. The activity
logs model, SoC, Android version and core count on its first line — keep that
line with the results. Also worth noting: whether the phone was plugged in
(thermal and governor behaviour differ), and whether you ran it twice, since a
hot phone throttles and the second run is often the honest one.
