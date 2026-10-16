// Ported from player/app/src/main/kotlin/com/pocketanim/player/LibraryActivity.kt.
import PanimCore
import UIKit
import UniformTypeIdentifiers

/**
 * The library: what there is to watch, as cards with a still, its length, how far it was watched, and whether it
 * is on the phone or streams. Tap to play; hold for more (play from the start, keep for offline, remove).
 */
final class LibraryViewController: UIViewController, UIDocumentPickerDelegate {

    private enum Tab: CaseIterable {
        case SAVED, PHONE, SAMPLES
        var label: String {
            switch self {
            case .SAVED: return "Saved"
            case .PHONE: return "On this phone"
            case .SAMPLES: return "Samples"
            }
        }
    }

    private var tab = Tab.SAVED
    private let list = UIStackView()
    private let status = Ui.text(13.5, Ui.MUTED)
    private let spinner = UIActivityIndicatorView(style: .medium)
    private let tabs = UIStackView()
    private var refreshing = false

    private let stillMaker = DispatchQueue(label: "panim-stills", qos: .utility)
    private let stills: NSCache<NSString, UIImage> = {
        let cache = NSCache<NSString, UIImage>()
        cache.countLimit = 24
        return cache
    }()

    /** Lectures being kept for offline right now, with how far they have got. */
    private var keeping: [String: String] = [:]

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func viewDidLoad() {
        super.viewDidLoad()
        overrideUserInterfaceStyle = .dark
        build()
        if Lectures.project() == nil && Lectures.cachedCatalog().isEmpty {
            tab = Lectures.onPhone().isEmpty ? .SAMPLES : .PHONE
        } else {
            tab = .SAVED
        }
        show()
        if Lectures.project() != nil { refresh(quiet: true) }
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        // Back from the player: progress bars and "on the phone" may have changed.
        if isViewLoaded { show() }
    }

    // ---- layout -----------------------------------------------------------------------------------------------

    private func build() {
        view.backgroundColor = Ui.BG

        let mark = UIView()
        mark.backgroundColor = Ui.ACCENT
        mark.layer.cornerRadius = 6
        mark.widthAnchor.constraint(equalToConstant: 22).isActive = true
        mark.heightAnchor.constraint(equalToConstant: 22).isActive = true
        let name = Ui.text(21, Ui.TEXT, medium: true)
        name.text = "pocketanim"
        spinner.color = Ui.ACCENT
        spinner.hidesWhenStopped = true
        let header = UIStackView(arrangedSubviews: [
            mark, name, UIView(), spinner,
            Ui.iconButton(.IMPORT, description: "Import a lecture") { [weak self] in self?.pickZip() },
            Ui.iconButton(.REFRESH, description: "Refresh") { [weak self] in self?.refresh(quiet: false) },
            Ui.iconButton(.MORE, description: "Settings") { [weak self] in self?.configure() },
        ])
        header.alignment = .center
        header.spacing = 4
        header.setCustomSpacing(10, after: mark)
        header.setCustomSpacing(8, after: spinner)
        header.isLayoutMarginsRelativeArrangement = true
        header.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 14, leading: 18, bottom: 6, trailing: 8)

        tabs.axis = .horizontal
        tabs.spacing = 8
        tabs.isLayoutMarginsRelativeArrangement = true
        tabs.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 4, leading: 14, bottom: 8, trailing: 14)
        let tabScroll = UIScrollView()
        tabScroll.showsHorizontalScrollIndicator = false
        tabScroll.addSubview(tabs)
        tabs.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            tabs.topAnchor.constraint(equalTo: tabScroll.contentLayoutGuide.topAnchor),
            tabs.bottomAnchor.constraint(equalTo: tabScroll.contentLayoutGuide.bottomAnchor),
            tabs.leadingAnchor.constraint(equalTo: tabScroll.contentLayoutGuide.leadingAnchor),
            tabs.trailingAnchor.constraint(equalTo: tabScroll.contentLayoutGuide.trailingAnchor),
            tabs.heightAnchor.constraint(equalTo: tabScroll.frameLayoutGuide.heightAnchor),
        ])

        status.numberOfLines = 0
        status.isHidden = true
        let statusBox = UIStackView(arrangedSubviews: [status])
        statusBox.isLayoutMarginsRelativeArrangement = true
        statusBox.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 4, leading: 18, bottom: 8, trailing: 18)

        list.axis = .vertical
        list.isLayoutMarginsRelativeArrangement = true
        list.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 0, leading: 12, bottom: 24, trailing: 12)
        let scroll = UIScrollView()
        scroll.showsVerticalScrollIndicator = false
        scroll.alwaysBounceVertical = true
        scroll.addSubview(list)
        list.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            list.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor),
            list.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor),
            list.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor),
            list.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor),
            list.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor),
        ])

        let root = UIStackView(arrangedSubviews: [header, tabScroll, statusBox, scroll])
        root.axis = .vertical
        root.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(root)
        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            root.topAnchor.constraint(equalTo: guide.topAnchor),
            root.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            root.leadingAnchor.constraint(equalTo: guide.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: guide.trailingAnchor),
            tabScroll.heightAnchor.constraint(equalToConstant: 48),
        ])
    }

    private func drawTabs() {
        tabs.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for t in Tab.allCases {
            let selected = t == tab
            let button = UIButton(type: .custom)
            button.setTitle(t.label, for: .normal)
            button.setTitleColor(selected ? Ui.BG : Ui.TEXT, for: .normal)
            button.titleLabel?.font = Ui.medium(14)
            button.backgroundColor = selected ? Ui.ACCENT : Ui.SURFACE_HIGH
            button.contentEdgeInsets = UIEdgeInsets(top: 8, left: 16, bottom: 8, right: 16)
            button.layer.cornerRadius = 18
            button.addAction(UIAction { [weak self] _ in
                self?.tab = t
                self?.show()
            }, for: .touchUpInside)
            tabs.addArrangedSubview(button)
        }
    }

    /** Fill the list for the current tab. */
    private func show() {
        drawTabs()
        list.arrangedSubviews.forEach { $0.removeFromSuperview() }
        status.isHidden = true
        switch tab {
        case .SAVED:
            let project = Lectures.project()
            let saved = Lectures.saved()
            if project == nil {
                say("Lectures you save in the web app appear here. Tap ⋮ to say which Supabase project they are " +
                    "saved to.")
            } else if let project = project, saved.isEmpty && !refreshing {
                let host = project.url.replacingOccurrences(of: "https://", with: "")
                say("No saved lectures yet in \(host). In the web app, Save after a build, then refresh here.")
            }
            var series: String?
            for lecture in saved {
                guard case .saved(let entry, _) = lecture else { continue }
                if entry.series != series {
                    series = entry.series
                    let label = Ui.text(13, Ui.MUTED, medium: true, lines: 1)
                    label.attributedText = NSAttributedString(string: entry.series.uppercased(), attributes: [.kern: 0.8])
                    let box = UIStackView(arrangedSubviews: [label])
                    box.isLayoutMarginsRelativeArrangement = true
                    box.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 16, leading: 6, bottom: 8, trailing: 6)
                    list.addArrangedSubview(box)
                }
                list.addArrangedSubview(card(lecture))
            }
        case .PHONE:
            let here = Lectures.onPhone()
            if here.isEmpty {
                say("Nothing kept on the phone yet. A saved lecture is kept once you play it (or hold it and choose " +
                    "Keep for offline); a lecture zip opens with Import.")
            }
            here.forEach { list.addArrangedSubview(card($0)) }
        case .SAMPLES:
            let samples = Lectures.samples()
            if samples.isEmpty { say("This build has no sample scenes.") }
            samples.forEach { list.addArrangedSubview(card($0)) }
        }
    }

    private func say(_ message: String) {
        status.text = message
        status.isHidden = false
    }

    /** One lecture's card: still, length, progress, title, where it comes from. */
    private func card(_ lecture: Lecture) -> UIView {
        let card = CardView()
        card.backgroundColor = Ui.SURFACE
        card.layer.cornerRadius = 14
        card.onTap = { [weak self] in self?.play(lecture, fromStart: false) }
        card.menu = { [weak self] in self?.more(lecture) ?? [] }
        card.menuTitle = lecture.title
        card.accessibilityLabel = lecture.title

        let still = UIView()
        still.backgroundColor = Ui.SURFACE_HIGH
        still.layer.cornerRadius = 10
        still.clipsToBounds = true
        let placeholder = placeholderView(lecture)
        let picture = UIImageView()
        picture.contentMode = .scaleAspectFill
        for view in [placeholder, picture] {
            view.translatesAutoresizingMaskIntoConstraints = false
            still.addSubview(view)
            NSLayoutConstraint.activate([
                view.topAnchor.constraint(equalTo: still.topAnchor),
                view.bottomAnchor.constraint(equalTo: still.bottomAnchor),
                view.leadingAnchor.constraint(equalTo: still.leadingAnchor),
                view.trailingAnchor.constraint(equalTo: still.trailingAnchor),
            ])
        }
        if let seconds = lecture.seconds {
            let length = Ui.PaddedLabel()
            length.text = Ui.clock(seconds)
            length.font = Ui.medium(11)
            length.textColor = Ui.TEXT
            length.insets = UIEdgeInsets(top: 2, left: 5, bottom: 2, right: 5)
            length.backgroundColor = Ui.argb(0xCC000000)
            length.layer.cornerRadius = 4
            length.layer.masksToBounds = true
            length.translatesAutoresizingMaskIntoConstraints = false
            still.addSubview(length)
            NSLayoutConstraint.activate([
                length.trailingAnchor.constraint(equalTo: still.trailingAnchor, constant: -5),
                length.bottomAnchor.constraint(equalTo: still.bottomAnchor, constant: -6),
            ])
        }
        if let progress = Lectures.progress(lecture.key) {
            let fraction = CGFloat(min(max(progress.at / progress.of, 0), 1))
            if fraction > 0.01 {
                let rest = UIView()
                rest.backgroundColor = Ui.argb(0x66FFFFFF)
                let done = UIView()
                done.backgroundColor = Ui.ACCENT
                for view in [rest, done] {
                    view.translatesAutoresizingMaskIntoConstraints = false
                    still.addSubview(view)
                    NSLayoutConstraint.activate([
                        view.bottomAnchor.constraint(equalTo: still.bottomAnchor),
                        view.heightAnchor.constraint(equalToConstant: 3),
                        view.leadingAnchor.constraint(equalTo: still.leadingAnchor),
                    ])
                }
                rest.trailingAnchor.constraint(equalTo: still.trailingAnchor).isActive = true
                done.widthAnchor.constraint(equalTo: still.widthAnchor, multiplier: fraction).isActive = true
            }
        }
        still.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            still.widthAnchor.constraint(equalToConstant: 136),
            still.heightAnchor.constraint(equalToConstant: 136 * 9 / 16),
        ])
        loadStill(lecture, picture)

        let title = Ui.text(15.5, Ui.TEXT, medium: true, lines: 2)
        title.text = lecture.title
        let subtitle = Ui.text(12.5, Ui.MUTED, lines: 1)
        subtitle.text = lecture.subtitle
        let chips = UIStackView()
        chips.spacing = 6
        switch lecture {
        case .saved(let entry, _):
            if let busy = keeping[lecture.key] {
                chips.addArrangedSubview(Ui.chip(busy, Ui.ACCENT, Ui.ACCENT_DARK))
            } else if lecture.onPhone {
                chips.addArrangedSubview(Ui.chip("✓ On phone", Ui.GOOD, Ui.GOOD_DARK))
            } else {
                chips.addArrangedSubview(Ui.chip("Streams · \(Ui.bytes(entry.libraryBytes))", Ui.MUTED, Ui.SURFACE_HIGH))
            }
            if !entry.narrated { chips.addArrangedSubview(Ui.chip("Silent", Ui.MUTED, Ui.SURFACE_HIGH)) }
        case .imported:
            chips.addArrangedSubview(Ui.chip("✓ On phone", Ui.GOOD, Ui.GOOD_DARK))
        case .sample:
            chips.addArrangedSubview(Ui.chip("Sample", Ui.MUTED, Ui.SURFACE_HIGH))
        }
        chips.addArrangedSubview(UIView())

        let words = UIStackView(arrangedSubviews: [title, subtitle, chips])
        words.axis = .vertical
        words.alignment = .fill
        words.setCustomSpacing(5, after: title)
        words.setCustomSpacing(8, after: subtitle)

        let row = UIStackView(arrangedSubviews: [still, words])
        row.alignment = .center
        row.spacing = 14
        row.isUserInteractionEnabled = false
        row.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(row)
        NSLayoutConstraint.activate([
            row.topAnchor.constraint(equalTo: card.topAnchor, constant: 8),
            row.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -8),
            row.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 8),
            row.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -10),
        ])

        let wrap = UIStackView(arrangedSubviews: [card])
        wrap.isLayoutMarginsRelativeArrangement = true
        wrap.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 5, leading: 0, bottom: 5, trailing: 0)
        return wrap
    }

    /** Before a still exists (a lecture not on the phone yet): its series' first letter on a colour of its own. */
    private func placeholderView(_ lecture: Lecture) -> UIView {
        // Java's String.hashCode, so a series gets the colour it has on Android.
        var hash: Int32 = 0
        for unit in lecture.subtitle.utf16 { hash = hash &* 31 &+ Int32(unit) }
        let hue = CGFloat(Int(hash & 0x7fffffff) % 360)
        let view = GradientView()
        view.gradient.colors = [
            UIColor(hue: hue / 360, saturation: 0.45, brightness: 0.35, alpha: 1).cgColor,
            UIColor(hue: CGFloat((Int(hue) + 40) % 360) / 360, saturation: 0.55, brightness: 0.18, alpha: 1).cgColor,
        ]
        view.gradient.startPoint = CGPoint(x: 0, y: 0)
        view.gradient.endPoint = CGPoint(x: 1, y: 1)
        let letter = Ui.text(26, Ui.argb(0xCCFFFFFF), medium: true)
        let source: String
        if case .saved(let entry, _) = lecture { source = entry.series } else { source = lecture.title }
        letter.text = String(source.prefix(1)).uppercased()
        letter.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(letter)
        NSLayoutConstraint.activate([
            letter.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            letter.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
        return view
    }

    /** The lecture's still, drawn once from the lecture itself (off the main thread) and kept. */
    private func loadStill(_ lecture: Lecture, _ into: UIImageView) {
        let key = lecture.key
        if let ready = stills.object(forKey: key as NSString) {
            into.image = ready
            return
        }
        if !lecture.onPhone { return }
        let file = Lectures.stills.appendingPathComponent("\(key).png")
        let width = Int(272 * (view.window?.screen.scale ?? UIScreen.main.scale) / 2)
        into.accessibilityIdentifier = key
        stillMaker.async { [weak self] in
            let image = Thumbnails.cached(file) {
                guard let storage = Lectures.storageOf(lecture) else { throw LibraryError("no library for \(key)") }
                let library = try Library.load(storage)
                guard let entry = library.scenes.first(where: {
                    if case .sample(let scene, _) = lecture { return $0.name == scene }
                    return true
                }) else { throw LibraryError("the library has no scenes") }
                let frames = try library.open(entry.name)
                return try Thumbnails.render(frames, Thumbnails.pick(frames, entry.chapters.map { $0.frame }), width)
            }
            guard let still = image else { return }
            DispatchQueue.main.async {
                self?.stills.setObject(still, forKey: key as NSString)
                if into.accessibilityIdentifier == key { into.image = still }
            }
        }
    }

    // ---- actions ----------------------------------------------------------------------------------------------

    private func play(_ lecture: Lecture, fromStart: Bool) {
        let player = PlayerViewController(lecture: lecture, fromStart: fromStart)
        // A zip opened from Files while a lecture plays: that one makes way.
        if let playing = presentedViewController {
            playing.dismiss(animated: false) { [weak self] in self?.present(player, animated: true) }
        } else {
            present(player, animated: true)
        }
    }

    private func more(_ lecture: Lecture) -> [UIAction] {
        var actions = [UIAction(title: "Play", image: UIImage(systemName: "play.fill")) { [weak self] _ in
            self?.play(lecture, fromStart: false)
        }]
        if Lectures.progress(lecture.key) != nil {
            actions.append(UIAction(title: "Play from the start", image: UIImage(systemName: "backward.end.fill")) {
                [weak self] _ in self?.play(lecture, fromStart: true)
            })
        }
        if case .saved = lecture, !lecture.onPhone, keeping[lecture.key] == nil {
            actions.append(UIAction(title: "Keep for offline", image: UIImage(systemName: "arrow.down.circle")) {
                [weak self] _ in self?.keep(lecture)
            })
        }
        if !lecture.isSample, let dir = Lectures.dirOf(lecture), Lectures.isDirectory(dir) {
            actions.append(UIAction(title: "Remove from phone", image: UIImage(systemName: "trash"),
                                    attributes: .destructive) { [weak self] _ in
                Lectures.remove(lecture)
                self?.stills.removeObject(forKey: lecture.key as NSString)
                self?.show()
            })
        }
        return actions
    }

    /** Download a saved lecture, narration and all, so it plays without the network. */
    private func keep(_ lecture: Lecture) {
        guard case .saved(let entry, let dir) = lecture, let project = Lectures.project() else { return }
        let key = lecture.key
        keeping[key] = "Downloading…"
        show()
        let wasOnPhone = lecture.onPhone
        let update: (String) -> Void = { [weak self] text in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.keeping[key] = text
                if self.tab == .SAVED { self.show() }
            }
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var failure: Error?
            do {
                if !wasOnPhone {
                    _ = try SavedLectures.download(project, entry, dir) { progress in
                        update("Downloading · \(progress)")
                    }
                    try lecture.title.write(to: dir.appendingPathComponent(Lectures.TITLE_FILE), atomically: true,
                                            encoding: .utf8)
                }
                let library = try Library.load(LibraryImport.DirStorage(dir))
                if let audio = library.scenes.first?.audio {
                    _ = try SavedLectures.fetchNarration(project, entry, audio, dir, cancelled: { false }) { progress in
                        update("Narration · \(progress)")
                    }
                }
            } catch {
                failure = error
            }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.keeping.removeValue(forKey: key)
                if let error = failure {
                    self.say("Could not keep \(lecture.title): \(Ui.message(of: error))")
                    Ui.showError(self, "Could not keep “\(lecture.title)”", error)
                }
                self.show()
            }
        }
    }

    private func refresh(quiet: Bool) {
        guard let project = Lectures.project() else {
            if !quiet { configure() }
            return
        }
        if refreshing { return }
        refreshing = true
        spinner.startAnimating()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Result { try Lectures.refreshCatalog(project) }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.refreshing = false
                self.spinner.stopAnimating()
                self.show()
                if case .failure(let error) = result {
                    if self.tab == .SAVED {
                        self.say("Could not reach the saved lectures (showing what was here last): " +
                            Ui.message(of: error))
                    }
                    if !quiet { Ui.showError(self, "Could not reach the saved lectures", error) }
                }
            }
        }
    }

    /** Ask for the project's URL and anon key (Supabase: Project Settings → API). */
    private func configure() {
        let known = Lectures.project()
        let alert = UIAlertController(
            title: "Where lectures are saved",
            message: "The Supabase project the web app saves to: its URL and anon key (Project Settings → API).",
            preferredStyle: .alert)
        alert.addTextField { field in
            field.placeholder = "https://<project>.supabase.co"
            field.text = known?.url
            field.keyboardType = .URL
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
        }
        alert.addTextField { field in
            field.placeholder = "anon / publishable key"
            field.text = known?.anonKey
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Save", style: .default) { [weak self, weak alert] _ in
            Lectures.setProject(url: alert?.textFields?[0].text ?? "", key: alert?.textFields?[1].text ?? "")
            self?.tab = .SAVED
            self?.show()
            self?.refresh(quiet: false)
        })
        present(alert, animated: true)
    }

    // ---- importing a zip ----------------------------------------------------------------------------------------

    private func pickZip() {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.zip], asCopy: true)
        picker.delegate = self
        picker.allowsMultipleSelection = false
        present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        if let url = urls.first { importFrom(url) }
    }

    /** Unpack a lecture's zip (checked file by file before it replaces anything), then play it. */
    func importFrom(_ url: URL) {
        let name = importName(url)
        tab = .PHONE
        show()
        say("Importing \(name)…")
        spinner.startAnimating()
        let dest = Lectures.importRoot.appendingPathComponent(name, isDirectory: true)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            let result = Result<Void, Error> {
                try FileManager.default.createDirectory(at: Lectures.importRoot, withIntermediateDirectories: true)
                guard let input = InputStream(url: url) else { throw LibraryError("cannot read \(url.lastPathComponent)") }
                input.open()
                defer { input.close() }
                _ = try LibraryImport.unpack(input, dest)
            }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.spinner.stopAnimating()
                self.show()
                switch result {
                case .success:
                    self.play(.imported(dir: dest, name: name.replacingOccurrences(of: "-", with: " ")), fromStart: false)
                case .failure(let error):
                    self.say("Could not import \(name): \(Ui.message(of: error))")
                    Ui.showError(self, "Could not import \(name)", error)
                }
            }
        }
    }

    private func importName(_ url: URL) -> String {
        var raw = url.lastPathComponent
        if raw.hasSuffix(".zip") { raw.removeLast(4) }
        if raw.hasSuffix("-library") { raw.removeLast(8) }
        let cleaned = raw.replacingOccurrences(of: "[^A-Za-z0-9_-]+", with: "-", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        let name = String(cleaned.prefix(80))
        return name.isEmpty ? "lecture" : name
    }
}

/** An error the app makes itself, with the text to show. */
struct LibraryError: LocalizedError {
    let text: String
    init(_ text: String) { self.text = text }
    var errorDescription: String? { text }
}

/** A gradient-backed view (the placeholder still). */
final class GradientView: UIView {
    override class var layerClass: AnyClass { CAGradientLayer.self }
    var gradient: CAGradientLayer { layer as! CAGradientLayer }
}

/** A lecture's card: tap to play, hold for its menu. */
final class CardView: UIControl {
    var onTap: (() -> Void)?
    var menu: (() -> [UIAction])?
    var menuTitle = ""

    override init(frame: CGRect) {
        super.init(frame: frame)
        isAccessibilityElement = true
        accessibilityTraits = .button
        addAction(UIAction { [weak self] _ in self?.onTap?() }, for: .touchUpInside)
        // UIControl brings its own context-menu interaction; it only needs switching on.
        isContextMenuInteractionEnabled = true
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var isHighlighted: Bool {
        didSet { alpha = isHighlighted ? 0.7 : 1 }
    }

    override func contextMenuInteraction(_ interaction: UIContextMenuInteraction,
                                         configurationForMenuAtLocation location: CGPoint) -> UIContextMenuConfiguration? {
        guard let actions = menu?(), !actions.isEmpty else { return nil }
        let title = menuTitle
        return UIContextMenuConfiguration(identifier: nil, previewProvider: nil) { _ in
            UIMenu(title: title, children: actions)
        }
    }
}
