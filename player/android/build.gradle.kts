plugins {
    id("com.android.library")
    kotlin("android")
}

android {
    namespace = "com.pocketanim.android"
    compileSdk = 34

    defaultConfig {
        // SurfaceView, AudioTrack.Builder and AudioTimestamp are all present
        // well before this, but 29 is where getTimestamp is dependable enough
        // to be the master clock.
        minSdk = 29
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    sourceSets["main"].kotlin.srcDir("src/main/kotlin")
}

dependencies {
    implementation(project(":core"))
}
