plugins {
    id("com.android.application")
    kotlin("android")
}

android {
    namespace = "com.pocketanim.player"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pocketanim.player"
        // §5 picks 29 as the support decision. The benchmark goes lower to
        // reach the oldest phone it can; the player does not, because AudioTrack
        // position reporting is what the clock depends on and it is only
        // dependable from 29.
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
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
    // `tools/build_library.py --out player/app/src/main/assets/library`
    sourceSets["main"].assets.srcDir("src/main/assets")
}

dependencies {
    implementation(project(":core"))
    implementation(project(":android"))
}
