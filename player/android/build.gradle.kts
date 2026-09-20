plugins {
    id("com.android.library")
    kotlin("android")
}

android {
    namespace = "com.pocketanim.android"
    compileSdk = 34

    defaultConfig {
        // §5 picks 29 as the *support* floor, which is a product decision
        // about which devices to ship to. Technically the renderer needs 21,
        // AudioTrack.Builder 23 and MediaCodec.getInputBuffer 21; 24 is set
        // here so the benchmark can run on an older phone than we intend to
        // support, which is exactly the device whose numbers matter most.
        // getTimestamp is less dependable below 29 -- that affects lip-sync,
        // not whether frames arrive.
        minSdk = 24
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
