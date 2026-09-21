// Versions live here, declared once and applied by the modules.
//
// AGP resolves from Google's Maven, which some environments cannot reach --
// that is why build.sh exists alongside this. Where the SDK is available, this
// is the real build.
plugins {
    id("com.android.application") version "8.6.1" apply false
    id("com.android.library") version "8.6.1" apply false
    kotlin("android") version "2.0.21" apply false
    kotlin("jvm") version "2.0.21" apply false
}
