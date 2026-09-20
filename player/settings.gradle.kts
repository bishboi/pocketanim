// The build to use where an Android SDK is available. player/build.sh is the
// fallback for environments that cannot reach dl.google.com.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "pocketanim-player"
include(":core", ":android", ":desktop", ":benchmark")
