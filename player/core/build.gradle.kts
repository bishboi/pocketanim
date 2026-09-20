// Pure Kotlin on purpose: the renderer must be runnable off-device so it can be
// checked against the Cairo oracle. Adding an Android dependency here would
// end that, so keep this module free of them.
plugins {
    kotlin("jvm")
}

kotlin {
    jvmToolchain(17)
}
