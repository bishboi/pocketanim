// swift-tools-version:5.9
//
// The iOS player's platform-neutral parts, as a Swift package. PanimCore and the Ogg demuxer in PanimAudio
// build on Linux too, so they can be checked against the Kotlin core (PanimVerify vs player/desktop Verify);
// everything that needs UIKit, CoreGraphics or AudioToolbox sits behind `#if canImport(...)`.
// The app itself is ios/App, generated into an Xcode project by XcodeGen (ios/project.yml).
import PackageDescription

let package = Package(
    name: "Panim",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "PanimCore", targets: ["PanimCore"]),
        .library(name: "PanimAudio", targets: ["PanimAudio"]),
    ],
    targets: [
        .target(name: "PanimCore"),
        .target(name: "PanimAudio"),
        .executableTarget(name: "PanimVerify", dependencies: ["PanimCore"]),
        .testTarget(name: "PanimCoreTests", dependencies: ["PanimCore"]),
        .testTarget(name: "PanimAudioTests", dependencies: ["PanimAudio"]),
    ]
)
