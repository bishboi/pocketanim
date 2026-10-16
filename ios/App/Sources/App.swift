// The app's entry points. The Android app's are declared in its AndroidManifest.xml: LibraryActivity launches, and
// a lecture zip opened from elsewhere (ACTION_VIEW) is handed to it to import.
import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        true
    }

    func application(_ application: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
        configuration.delegateClass = SceneDelegate.self
        return configuration
    }
}

final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private let library = LibraryViewController()

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: windowScene)
        window.overrideUserInterfaceStyle = .dark
        window.backgroundColor = Ui.BG
        window.tintColor = Ui.ACCENT
        window.rootViewController = library
        window.makeKeyAndVisible()
        self.window = window
        if let url = connectionOptions.urlContexts.first?.url { open(url) }
    }

    /** A lecture zip shared to the app (Files, Safari's downloads, AirDrop): imported, then played. */
    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        if let url = URLContexts.first?.url { open(url) }
    }

    private func open(_ url: URL) {
        guard url.isFileURL else { return }
        // After the library has laid itself out, so its import has a screen to show on.
        DispatchQueue.main.async { [library] in library.importFrom(url) }
    }
}
