// Ported from player/android/src/main/kotlin/com/pocketanim/android/AssetStorage.kt.
import Foundation
import PanimCore

/**
 * [Storage] over the library inside the app.
 *
 * For a first run before anything has been synced: the library ships inside the app so there is something to play
 * without a network. On Android the APK's assets needed a Storage of their own (they are compressed entries, not
 * files); an iOS bundle is a folder on disk, so the bundled library is read through the same folder storage an
 * imported one is (LibraryImport.DirStorage), and its files -- the narration included -- are read in place.
 */
enum AssetStorage {
    /** The folder `library` copied into the app at build time (ios.yml packs it as apk.yml does), if this build has one. */
    static func root(bundle: Bundle = .main, name: String = "library") -> URL? {
        guard let url = bundle.resourceURL?.appendingPathComponent(name, isDirectory: true),
              FileManager.default.fileExists(atPath: url.appendingPathComponent("library.json").path) else { return nil }
        return url
    }

    static func storage(bundle: Bundle = .main, name: String = "library") -> Storage? {
        root(bundle: bundle, name: name).map { LibraryImport.DirStorage($0) as Storage }
    }
}
