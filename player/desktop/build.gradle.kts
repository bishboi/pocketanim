// Verification harness, not shipped. Backs the core's PathSink with Java2D so
// the shipping renderer can be executed and compared against the oracle.
plugins {
    kotlin("jvm")
    application
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":core"))
}

application {
    mainClass.set("com.pocketanim.desktop.VerifyKt")
}
