# pocketanim-player.apk

The phone player, built by `player/build-apk.sh` (no Android SDK needed: aapt2, dx, zipalign and apksigner
from Ubuntu's archive, the Kotlin toolchain from `player/build.sh --fetch`). Android 10 (API 29) or later.

- **Saved** lists the lectures saved from the web app (its Save button) in Supabase and plays the one you pick,
  downloaded into the app, offline afterwards. The first time, it asks for the project URL and anon key
  (Supabase: Project Settings → API); long-press Saved to change them. Build with `PANIM_SUPABASE_URL` and
  `PANIM_SUPABASE_ANON_KEY` set to ship them inside the APK instead.
- **Import** opens a lecture zip from the web app's "Download for the phone".
- The sample scenes are packed in.

Install: download the file on the phone and open it (allow installs from that app), or
`adb install -r pocketanim-player.apk`. It is signed with a debug key: uninstall an earlier build signed with a
different key (the CI one) first.
