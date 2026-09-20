plugins {
    id("com.android.application")
    kotlin("android")
}

android {
    namespace = "com.pocketanim.benchmark"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pocketanim.benchmark"
        // Lower than the library's own floor on purpose. §5 picks 29 as a
        // support decision; nothing in the renderer needs it, and the whole
        // point of this module is to run on the oldest device we can find.
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            // Measure what ships. A debug build has assertions and no
            // optimisation, and reports frame times that mean nothing.
            isMinifyEnabled = false
            isDebuggable = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }

    sourceSets["main"].kotlin.srcDir("src/main/kotlin")
    // `tools/build_library.py --out player/benchmark/src/main/assets/library`
    sourceSets["main"].assets.srcDir("src/main/assets")
}

dependencies {
    implementation(project(":core"))
    implementation(project(":android"))
}
