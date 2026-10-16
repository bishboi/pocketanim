// Ported from player/app/src/main/kotlin/com/pocketanim/player/PlayerActivity.kt.
import AVFoundation
import MediaPlayer
import PanimAudio
import PanimCore
import UIKit

/**
 * The player, as a viewer meets it: like a video, though nothing here is a video. The lecture is a program the
 * phone draws frame by frame as it plays, which is why it starts after a few megabytes, seeks instantly and looks
 * sharp at any size.
 *
 * A saved lecture streams: its program and pictures (a few MB) come first and it starts; its narration plays from
 * the network while it is kept on the phone for next time. The picture follows the narration, and holds -- with a
 * spinner, as a video buffers -- when the network falls behind.
 *
 * Tap the picture for the controls (they hide themselves while it plays); double-tap its left or right side to go
 * back or on ten seconds. Turn the phone, or press the corner button, for the whole screen.
 */
final class PlayerViewController: UIViewController, UIGestureRecognizerDelegate, TimelineListener {

    private static let TICK_SECONDS = 0.066
    private static let HIDE_AFTER_SECONDS = 3.2
    private static let SKIP_SECONDS = 10.0
    private static let SPEEDS: [Double] = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]

    private var lecture: Lecture
    private let fromStart: Bool

    private let stage = UIView()
    private let panim = PanimView()
    private let overlay = UIView()
    private let controls = UIView()
    private var playButton: UIButton!
    private let timeline = TimelineView()
    private let timeLabel = Ui.text(13, Ui.TEXT, medium: true)
    private let chapterLabel = Ui.text(12, Ui.argb(0xCCFFFFFF), lines: 1)
    private let titleLabel = Ui.text(15, Ui.TEXT, medium: true, lines: 1)
    private let speedButton = UIButton(type: .custom)
    private var fullscreenButton: UIButton!
    private var chaptersButton: UIButton!
    private let spinner = UIActivityIndicatorView(style: .large)
    private let loadingBar = UIProgressView(progressViewStyle: .bar)
    private let loadingLabel = Ui.text(13, Ui.TEXT)
    private let loadingBox = UIStackView()
    private let hint = Ui.PaddedLabel()
    private var hintLeading: NSLayoutConstraint!
    private var hintTrailing: NSLayoutConstraint!
    private let notice = Ui.PaddedLabel()
    private var noticeAction: (() -> Void)?
    private let endCard = UIStackView()
    private let endScrim = UIView()
    private let details = UIScrollView()
    private let chapterList = UIStackView()
    private let infoLabel = Ui.text(13, Ui.MUTED)

    private var portraitLayout: [NSLayoutConstraint] = []
    private var fullLayout: [NSLayoutConstraint] = []

    private var frames: Frames?
    private var scene: SceneEntry?
    private var chapters: [Chapter] = []
    private var fps = 30
    private var frameCount = 1

    /** What the viewer asked for: playing or not. Buffering holds the picture without changing this. */
    private var wantPlaying = false
    private var heldForNetwork = false
    private var controlsShown = true
    private var scrubbing = false
    private var scrubWasPlaying = false
    private var endShown = false
    private var speed = 1.0
    private var lastSaved = Date.distantPast
    private var shownChapter = -2
    private var loadedFraction: Float = 1
    private var audioProblemShown = false
    private var frameErrorShown = false
    private var closed = false

    /** The whole screen: the phone turned, or the corner button pressed. */
    private var fullscreen = false
    private var forcedFullscreen = false

    private let narrationFetch = CancelFlag()
    private var ticker: Timer?
    private var hideControls: DispatchWorkItem?
    private var observers: [NSObjectProtocol] = []
    private var remoteTargets: [(MPRemoteCommand, Any)] = []

    init(lecture: Lecture, fromStart: Bool) {
        self.lecture = lecture
        self.fromStart = fromStart
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .fullScreen
        modalTransitionStyle = .crossDissolve
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    // ---- life ---------------------------------------------------------------------------------------------------

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }
    override var prefersStatusBarHidden: Bool { fullscreen }
    override var prefersHomeIndicatorAutoHidden: Bool { fullscreen && !controlsShown }
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask {
        UIDevice.current.userInterfaceIdiom == .pad ? .all : .allButUpsideDown
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        overrideUserInterfaceStyle = .dark
        build()
        layoutFor(view.bounds.size)
        listen()
        prepare()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        ticker?.invalidate()
        let timer = Timer(timeInterval: PlayerViewController.TICK_SECONDS, repeats: true) { [weak self] _ in self?.sync() }
        RunLoop.main.add(timer, forMode: .common)
        ticker = timer
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        ticker?.invalidate()
        ticker = nil
        if wantPlaying { pause() }
        remember()
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed || presentingViewController == nil { close() }
    }

    /** The player is going: stop the narration and its download, and let the phone sleep again. */
    private func close() {
        if closed { return }
        closed = true
        narrationFetch.cancel()
        for observer in observers { NotificationCenter.default.removeObserver(observer) }
        observers.removeAll()
        for (command, target) in remoteTargets { command.removeTarget(target) }
        remoteTargets.removeAll()
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        UIApplication.shared.isIdleTimerDisabled = false
        panim.release()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    override func viewWillTransition(to size: CGSize, with coordinator: UIViewControllerTransitionCoordinator) {
        super.viewWillTransition(to: size, with: coordinator)
        coordinator.animate(alongsideTransition: { [weak self] _ in self?.layoutFor(size) })
    }

    // ---- getting it ready -----------------------------------------------------------------------------------------

    /**
     * Get the lecture onto the phone if it is not (a saved one: its program and pictures, a few MB, in one
     * request), open it, and start. Off the main thread; the stage says how far it has got.
     */
    private func prepare() {
        loading(true, "Getting ready…")
        let current = lecture
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Result<(Storage, SceneEntry, Frames), Error> {
                if case .saved(let entry, let dir) = current, !current.onPhone {
                    guard let project = Lectures.project() else {
                        throw LibraryError("no Supabase project is set (Library → ⋮)")
                    }
                    _ = try SavedLectures.download(project, entry, dir) { progress in
                        DispatchQueue.main.async {
                            if progress.unit == "bytes" && progress.total > 0 {
                                let share = Float(progress.done) / Float(progress.total)
                                self?.loading(true, "Loading the lecture · \(progress)", share)
                            } else {
                                self?.loading(true, "Loading the lecture · \(progress)")
                            }
                        }
                    }
                    try current.title.write(to: dir.appendingPathComponent(Lectures.TITLE_FILE), atomically: true,
                                            encoding: .utf8)
                }
                DispatchQueue.main.async { self?.loading(true, "Opening…") }
                guard let storage = Lectures.storageOf(current) else { throw LibraryError("this build has no library") }
                let library = try Library.load(storage)
                let entry: SceneEntry
                if case .sample(let name, _) = current {
                    entry = try library.entry(name)
                } else {
                    guard let first = library.scenes.first else { throw LibraryError("the library has no scenes") }
                    entry = first
                }
                let opened = try library.open(entry.name)
                return (storage, entry, opened)
            }
            DispatchQueue.main.async {
                guard let self = self, !self.closed else { return }
                switch result {
                case .success(let (storage, entry, opened)):
                    self.start(storage, entry, opened)
                case .failure(let error):
                    self.loading(false)
                    self.showNotice("Could not play this lecture: \(Ui.message(of: error))", action: "Back") {
                        [weak self] in self?.dismiss(animated: true)
                    }
                    Ui.showError(self, "Could not play “\(self.lecture.title)”", error)
                }
            }
        }
    }

    private func start(_ storage: Storage, _ entry: SceneEntry, _ opened: Frames) {
        frames = opened
        scene = entry
        fps = max(opened.fps, 1)
        frameCount = max(opened.frameCount, 1)
        chapters = entry.chapters
        panim.load(opened)
        panim.playback?.looping = false
        panim.setSpeed(speed)
        timeline.durationSeconds = Double(frameCount) / Double(fps)
        timeline.chapters = chapters.map { (Float($0.frame) / Float(frameCount), $0.title) }
        fillDetails()
        loading(false)

        let total = Double(frameCount) / Double(fps)
        if !fromStart, let saved = Lectures.progress(lecture.key), saved.at > 5, saved.at < total - 10 {
            panim.seekToFrame(Int(saved.at * Double(fps)))
            showNotice("Resumed at \(Ui.clock(saved.at))", action: "Start over") { [weak self] in self?.seekSeconds(0) }
        }
        play()
        narrate(storage, entry)
    }

    /**
     * The narration: from the phone when it is here; else, for a saved lecture, streamed from where Save put it,
     * and kept on the phone as it plays (written beside the lecture once it has all arrived). The picture plays at
     * once; the voice joins at the picture's place.
     */
    private func narrate(_ storage: Storage, _ entry: SceneEntry) {
        guard let path = entry.audio else { return }
        let current = lecture
        let fetch = narrationFetch
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var described = path
            let result = Result<NarrationSource?, Error> {
                // In place: a folder on the phone, the app's own library included (an iOS bundle is a folder).
                if let file = storage.file(path), Lectures.isFile(file),
                   ((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) > 0 {
                    described = file.path
                    return try NarrationSource(contentsOf: file)
                }
                guard case .saved(let saved, let dir) = current, let project = Lectures.project(),
                      let url = URL(string: SavedLectures.narrationUrl(project, saved, path)) else { return nil }
                described = url.absoluteString
                let keep = dir.appendingPathComponent(path)
                try? FileManager.default.createDirectory(at: keep.deletingLastPathComponent(),
                                                         withIntermediateDirectories: true)
                let source = NarrationSource.stream(url, keepAt: keep)
                fetch.onCancel { source.cancel() }
                DispatchQueue.main.async { self?.loadedFraction = 0 }
                source.onProgress = { have, total in
                    guard let total = total, total > 0 else { return }
                    let share = Float(have) / Float(total)
                    DispatchQueue.main.async { self?.loadedFraction = share }
                }
                return source
            }
            // What it is, once its first bytes are here (a stream waits for them, which is why this is off the main
            // thread).
            let opened = result.flatMap { source in
                Result<(NarrationSource, NarrationFormat)?, Error> {
                    guard let source = source else { return nil }
                    let format = try source.format()
                    return (source, format)
                }
            }
            DispatchQueue.main.async {
                guard let self = self, !self.closed else { return }
                switch opened {
                case .success(let found):
                    guard let pair = found else { return }
                    self.panim.attachAudio(pair.0, pair.1)
                case .failure(let error):
                    self.showNotice("Playing without narration: \(Ui.message(of: error))", action: "Details") {
                        [weak self] in
                        guard let self = self else { return }
                        Ui.showError(self, "The narration could not be read (\(described))", error)
                    }
                }
            }
        }
    }

    // ---- layout -------------------------------------------------------------------------------------------------

    private func build() {
        view.backgroundColor = .black

        // The system stopped the narration (a call, other audio, headphones out): the picture stops with it.
        panim.onAudioSystemPause = { [weak self] in
            if self?.wantPlaying == true { self?.pause() }
        }
        // A frame that cannot be drawn: its full error, once (every frame after it would say the same).
        panim.onFrameError = { [weak self] index, error in
            guard let self = self, !self.frameErrorShown, !self.closed else { return }
            self.frameErrorShown = true
            Ui.showError(self, "Frame \(index) of this lecture could not be drawn", error)
        }

        stage.backgroundColor = .black
        stage.clipsToBounds = true
        for v in [stage, details] {
            v.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(v)
        }
        fill(stage, with: panim)
        fill(stage, with: overlay)

        let single = UITapGestureRecognizer(target: self, action: #selector(tapped))
        let double = UITapGestureRecognizer(target: self, action: #selector(doubleTapped(_:)))
        double.numberOfTapsRequired = 2
        single.require(toFail: double)
        for g in [single, double] {
            g.delegate = self
            overlay.addGestureRecognizer(g)
        }

        fill(overlay, with: controls)

        // Top: back, the title and the chapter, speed, chapters.
        let top = GradientView()
        top.gradient.colors = [Ui.argb(0xB3000000).cgColor, UIColor.clear.cgColor]
        titleLabel.text = lecture.title
        let names = UIStackView(arrangedSubviews: [titleLabel, chapterLabel])
        names.axis = .vertical
        names.spacing = 3
        speedButton.setTitle("1×", for: .normal)
        speedButton.titleLabel?.font = Ui.medium(13)
        speedButton.setTitleColor(Ui.TEXT, for: .normal)
        speedButton.backgroundColor = Ui.argb(0x33FFFFFF)
        speedButton.layer.cornerRadius = 14
        speedButton.contentEdgeInsets = UIEdgeInsets(top: 6, left: 10, bottom: 6, right: 10)
        speedButton.accessibilityLabel = "Playback speed"
        speedButton.addAction(UIAction { [weak self] _ in self?.chooseSpeed() }, for: .touchUpInside)
        chaptersButton = Ui.iconButton(.CHAPTERS, description: "Chapters") { [weak self] in self?.chooseChapter() }
        let topRow = UIStackView(arrangedSubviews: [
            Ui.iconButton(.BACK, description: "Back") { [weak self] in self?.back() },
            names, speedButton, chaptersButton,
        ])
        topRow.alignment = .center
        topRow.spacing = 4
        topRow.setCustomSpacing(8, after: topRow.arrangedSubviews[0])
        topRow.translatesAutoresizingMaskIntoConstraints = false
        top.addSubview(topRow)
        top.translatesAutoresizingMaskIntoConstraints = false
        controls.addSubview(top)

        // Middle: back ten seconds, play or pause, on ten seconds.
        playButton = Ui.iconButton(.PLAY, size: 68, fill: Ui.argb(0x66000000), description: "Play") { [weak self] in
            self?.togglePlay()
        }
        let middle = UIStackView(arrangedSubviews: [
            Ui.iconButton(.BACK10, size: 52, fill: Ui.argb(0x40000000), description: "Back 10 seconds") {
                [weak self] in self?.skip(-PlayerViewController.SKIP_SECONDS)
            },
            playButton,
            Ui.iconButton(.FORWARD10, size: 52, fill: Ui.argb(0x40000000), description: "Forward 10 seconds") {
                [weak self] in self?.skip(PlayerViewController.SKIP_SECONDS)
            },
        ])
        middle.alignment = .center
        middle.spacing = 28
        middle.translatesAutoresizingMaskIntoConstraints = false
        controls.addSubview(middle)

        // Bottom: the time, the timeline, the whole screen.
        let bottom = GradientView()
        bottom.gradient.colors = [UIColor.clear.cgColor, Ui.argb(0xB3000000).cgColor]
        timeLabel.text = "0:00 / 0:00"
        fullscreenButton = Ui.iconButton(.FULLSCREEN, size: 40, description: "Whole screen") { [weak self] in
            self?.toggleFullscreen()
        }
        let row = UIStackView(arrangedSubviews: [timeLabel, UIView(), fullscreenButton])
        row.alignment = .center
        timeline.listener = self
        let bottomStack = UIStackView(arrangedSubviews: [row, timeline])
        bottomStack.axis = .vertical
        bottomStack.translatesAutoresizingMaskIntoConstraints = false
        bottom.addSubview(bottomStack)
        bottom.translatesAutoresizingMaskIntoConstraints = false
        controls.addSubview(bottom)

        let safe = overlay.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            top.topAnchor.constraint(equalTo: controls.topAnchor),
            top.leadingAnchor.constraint(equalTo: controls.leadingAnchor),
            top.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
            topRow.topAnchor.constraint(equalTo: safe.topAnchor, constant: 6),
            topRow.leadingAnchor.constraint(equalTo: safe.leadingAnchor, constant: 4),
            topRow.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -8),
            topRow.bottomAnchor.constraint(equalTo: top.bottomAnchor, constant: -24),

            middle.centerXAnchor.constraint(equalTo: controls.centerXAnchor),
            middle.centerYAnchor.constraint(equalTo: controls.centerYAnchor),

            bottom.bottomAnchor.constraint(equalTo: controls.bottomAnchor),
            bottom.leadingAnchor.constraint(equalTo: controls.leadingAnchor),
            bottom.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
            bottomStack.topAnchor.constraint(equalTo: bottom.topAnchor, constant: 28),
            bottomStack.leadingAnchor.constraint(equalTo: safe.leadingAnchor, constant: 8),
            bottomStack.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -8),
            bottomStack.bottomAnchor.constraint(equalTo: safe.bottomAnchor, constant: 2),
            timeline.heightAnchor.constraint(equalToConstant: 64),
            row.heightAnchor.constraint(equalToConstant: 40),
        ])
        row.isLayoutMarginsRelativeArrangement = true
        row.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 0, leading: 10, bottom: 0, trailing: 0)

        // While getting ready or waiting on the network.
        spinner.color = Ui.ACCENT
        spinner.hidesWhenStopped = true
        loadingBar.progressTintColor = Ui.ACCENT
        loadingBar.trackTintColor = Ui.argb(0x40FFFFFF)
        loadingBar.widthAnchor.constraint(equalToConstant: 160).isActive = true
        loadingLabel.textAlignment = .center
        loadingLabel.numberOfLines = 2
        for v in [spinner, loadingBar, loadingLabel] as [UIView] { loadingBox.addArrangedSubview(v) }
        loadingBox.axis = .vertical
        loadingBox.alignment = .center
        loadingBox.spacing = 12
        loadingBox.isUserInteractionEnabled = false
        loadingBox.translatesAutoresizingMaskIntoConstraints = false
        overlay.addSubview(loadingBox)

        // "« 10 s" / "10 s »" where a double tap landed.
        hint.font = Ui.medium(15)
        hint.textColor = Ui.TEXT
        hint.insets = UIEdgeInsets(top: 10, left: 16, bottom: 10, right: 16)
        hint.backgroundColor = Ui.argb(0x99000000)
        hint.layer.cornerRadius = 22
        hint.layer.masksToBounds = true
        hint.isHidden = true
        hint.translatesAutoresizingMaskIntoConstraints = false
        overlay.addSubview(hint)
        hintLeading = hint.leadingAnchor.constraint(equalTo: overlay.leadingAnchor, constant: 40)
        hintTrailing = hint.trailingAnchor.constraint(equalTo: overlay.trailingAnchor, constant: -40)

        // A line with an action: "Resumed at 4:12 · Start over", a problem.
        notice.font = Ui.regular(13)
        notice.textColor = Ui.TEXT
        notice.numberOfLines = 3
        notice.insets = UIEdgeInsets(top: 10, left: 14, bottom: 10, right: 14)
        notice.backgroundColor = Ui.argb(0xE6202329)
        notice.layer.cornerRadius = 10
        notice.layer.masksToBounds = true
        notice.isHidden = true
        notice.isUserInteractionEnabled = true
        notice.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(noticeTapped)))
        notice.translatesAutoresizingMaskIntoConstraints = false
        overlay.addSubview(notice)

        // At the end: watch again, or the next lecture of the series.
        endScrim.backgroundColor = Ui.argb(0xB3000000)
        endScrim.isHidden = true
        fill(overlay, with: endScrim)
        endCard.axis = .horizontal
        endCard.alignment = .top
        endCard.spacing = 8
        endCard.translatesAutoresizingMaskIntoConstraints = false
        endScrim.addSubview(endCard)

        NSLayoutConstraint.activate([
            loadingBox.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
            loadingBox.centerYAnchor.constraint(equalTo: overlay.centerYAnchor),
            loadingBox.widthAnchor.constraint(lessThanOrEqualTo: overlay.widthAnchor, constant: -32),
            hint.centerYAnchor.constraint(equalTo: overlay.centerYAnchor),
            notice.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
            notice.bottomAnchor.constraint(equalTo: safe.bottomAnchor, constant: -84),
            notice.widthAnchor.constraint(lessThanOrEqualTo: overlay.widthAnchor, constant: -32),
            endCard.centerXAnchor.constraint(equalTo: endScrim.centerXAnchor),
            endCard.centerYAnchor.constraint(equalTo: endScrim.centerYAnchor),
        ])

        // Below the picture when the phone is upright: the lecture, and its chapters to jump to.
        details.backgroundColor = Ui.BG
        details.alwaysBounceVertical = true
        let heading = Ui.text(19, Ui.TEXT, medium: true)
        heading.text = lecture.title
        infoLabel.text = lecture.subtitle
        infoLabel.numberOfLines = 0
        chapterList.axis = .vertical
        let words = UIStackView(arrangedSubviews: [heading, infoLabel, chapterList])
        words.axis = .vertical
        words.setCustomSpacing(6, after: heading)
        words.setCustomSpacing(14, after: infoLabel)
        words.isLayoutMarginsRelativeArrangement = true
        words.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 16, leading: 18, bottom: 28, trailing: 18)
        words.translatesAutoresizingMaskIntoConstraints = false
        details.addSubview(words)
        NSLayoutConstraint.activate([
            words.topAnchor.constraint(equalTo: details.contentLayoutGuide.topAnchor),
            words.bottomAnchor.constraint(equalTo: details.contentLayoutGuide.bottomAnchor),
            words.leadingAnchor.constraint(equalTo: details.contentLayoutGuide.leadingAnchor),
            words.trailingAnchor.constraint(equalTo: details.contentLayoutGuide.trailingAnchor),
            words.widthAnchor.constraint(equalTo: details.frameLayoutGuide.widthAnchor),
        ])

        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            stage.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            stage.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            details.leadingAnchor.constraint(equalTo: guide.leadingAnchor),
            details.trailingAnchor.constraint(equalTo: guide.trailingAnchor),
            details.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        portraitLayout = [
            stage.topAnchor.constraint(equalTo: guide.topAnchor),
            stage.heightAnchor.constraint(equalTo: stage.widthAnchor, multiplier: 9.0 / 16.0),
            details.topAnchor.constraint(equalTo: stage.bottomAnchor),
        ]
        fullLayout = [
            stage.topAnchor.constraint(equalTo: view.topAnchor),
            stage.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            details.topAnchor.constraint(equalTo: view.bottomAnchor),
        ]
    }

    private func fill(_ parent: UIView, with child: UIView) {
        child.translatesAutoresizingMaskIntoConstraints = false
        parent.addSubview(child)
        NSLayoutConstraint.activate([
            child.topAnchor.constraint(equalTo: parent.topAnchor),
            child.bottomAnchor.constraint(equalTo: parent.bottomAnchor),
            child.leadingAnchor.constraint(equalTo: parent.leadingAnchor),
            child.trailingAnchor.constraint(equalTo: parent.trailingAnchor),
        ])
    }

    /** Upright: the picture across the top, the lecture's details under it. Sideways: the picture, whole screen. */
    private func layoutFor(_ size: CGSize) {
        let whole = size.width > size.height || forcedFullscreen
        fullscreen = whole
        NSLayoutConstraint.deactivate(whole ? portraitLayout : fullLayout)
        NSLayoutConstraint.activate(whole ? fullLayout : portraitLayout)
        details.isHidden = whole
        fullscreenButton.setImage(Ui.image(whole ? .EXIT_FULLSCREEN : .FULLSCREEN, side: 40 * 0.56, color: Ui.TEXT),
                                  for: .normal)
        setNeedsStatusBarAppearanceUpdate()
        setNeedsUpdateOfHomeIndicatorAutoHidden()
        view.layoutIfNeeded()
    }

    /**
     * The corner button. iOS 16 can be asked to turn the screen; on 15 an app cannot, so the picture takes the whole
     * (upright) screen instead, and turning the phone does the rest.
     */
    private func toggleFullscreen() {
        let leaving = fullscreen
        forcedFullscreen = !leaving
        if #available(iOS 16.0, *), let scene = view.window?.windowScene {
            setNeedsUpdateOfSupportedInterfaceOrientations()
            let mask: UIInterfaceOrientationMask = leaving ? .portrait : .landscape
            scene.requestGeometryUpdate(.iOS(interfaceOrientations: mask)) { _ in }
        }
        UIView.animate(withDuration: 0.25) { self.layoutFor(self.view.bounds.size) }
        scheduleHide()
    }

    /** Out of the whole screen first, as a video app does; back again leaves. */
    private func back() {
        if forcedFullscreen {
            toggleFullscreen()
            return
        }
        dismiss(animated: true)
    }

    // ---- the details panel ----------------------------------------------------------------------------------------

    private func fillDetails() {
        let seconds = Double(frameCount) / Double(fps)
        var bits = [lecture.subtitle, Ui.length(seconds)]
        if !chapters.isEmpty { bits.append("\(chapters.count) chapters") }
        infoLabel.text = bits.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }.joined(separator: "  ·  ")
        chapterList.arrangedSubviews.forEach { $0.removeFromSuperview() }
        if chapters.isEmpty { return }
        let header = Ui.text(12.5, Ui.MUTED, medium: true)
        header.attributedText = NSAttributedString(string: "CHAPTERS", attributes: [.kern: 1.0])
        let headerBox = UIStackView(arrangedSubviews: [header])
        headerBox.isLayoutMarginsRelativeArrangement = true
        headerBox.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 4, leading: 0, bottom: 8, trailing: 0)
        chapterList.addArrangedSubview(headerBox)
        for (index, chapter) in chapters.enumerated() {
            let row = CardView()
            row.layer.cornerRadius = 10
            row.tag = index + 1
            row.onTap = { [weak self] in self?.jumpTo(chapter) }
            row.accessibilityLabel = "\(Ui.clock(Double(chapter.frame) / Double(fps))) \(chapter.title)"
            let time = Ui.text(13, Ui.ACCENT, medium: true)
            time.text = Ui.clock(Double(chapter.frame) / Double(fps))
            time.widthAnchor.constraint(greaterThanOrEqualToConstant: 56).isActive = true
            time.setContentHuggingPriority(.required, for: .horizontal)
            let name = Ui.text(14.5, Ui.TEXT, lines: 2)
            name.text = chapter.title
            let line = UIStackView(arrangedSubviews: [time, name])
            line.alignment = .center
            line.isUserInteractionEnabled = false
            line.translatesAutoresizingMaskIntoConstraints = false
            row.addSubview(line)
            NSLayoutConstraint.activate([
                line.topAnchor.constraint(equalTo: row.topAnchor, constant: 12),
                line.bottomAnchor.constraint(equalTo: row.bottomAnchor, constant: -12),
                line.leadingAnchor.constraint(equalTo: row.leadingAnchor, constant: 12),
                line.trailingAnchor.constraint(equalTo: row.trailingAnchor, constant: -12),
            ])
            chapterList.addArrangedSubview(row)
        }
        shownChapter = -2
    }

    private func currentChapter(_ frame: Int) -> Int {
        chapters.lastIndex { $0.frame <= frame } ?? -1
    }

    // ---- playing --------------------------------------------------------------------------------------------------

    private func play() {
        guard frames != nil, let playback = panim.playback else { return }
        if playback.currentFrame() >= frameCount - 1 { panim.seekToFrame(0) }
        endShown = false
        endScrim.isHidden = true
        try? AudioClock.activateSession()
        wantPlaying = true
        heldForNetwork = false
        panim.play()
        UIApplication.shared.isIdleTimerDisabled = true
        setPlayIcon(.PAUSE, "Pause")
        scheduleHide()
        nowPlaying()
    }

    private func pause() {
        wantPlaying = false
        heldForNetwork = false
        panim.pause()
        UIApplication.shared.isIdleTimerDisabled = false
        setPlayIcon(.PLAY, "Play")
        hideControls?.cancel()
        setControls(true)
        remember()
        nowPlaying()
    }

    private func setPlayIcon(_ icon: Icon, _ label: String) {
        playButton.setImage(Ui.image(icon, side: 68 * 0.56, color: Ui.TEXT), for: .normal)
        playButton.accessibilityLabel = label
    }

    private func togglePlay() {
        if wantPlaying { pause() } else { play() }
    }

    private func seekSeconds(_ seconds: Double) {
        let frame = min(max(Int(seconds * Double(fps)), 0), frameCount - 1)
        panim.seekToFrame(frame)
        endShown = false
        endScrim.isHidden = true
        showTime(Float(frame))
        nowPlaying()
    }

    private func skip(_ seconds: Double) {
        guard let playback = panim.playback else { return }
        seekSeconds(Double(playback.currentFrame()) / Double(fps) + seconds)
        hint.text = seconds < 0 ? "« \(Int(-seconds)) s" : "\(Int(seconds)) s »"
        hintLeading.isActive = seconds < 0
        hintTrailing.isActive = seconds >= 0
        hint.isHidden = false
        hint.layer.removeAllAnimations()
        hint.alpha = 1
        UIView.animate(withDuration: 0.3, delay: 0.5, options: [.allowUserInteraction], animations: {
            self.hint.alpha = 0
        }, completion: { done in if done { self.hint.isHidden = true } })
        if controlsShown { scheduleHide() }
    }

    private func jumpTo(_ chapter: Chapter) {
        seekSeconds(Double(chapter.frame) / Double(fps))
        if !wantPlaying { play() }
    }

    private func chooseChapter() {
        if chapters.isEmpty {
            showNotice("This lecture has no chapters.")
            return
        }
        let now = currentChapter(panim.playback?.currentFrame() ?? 0)
        let names = chapters.enumerated().map { i, c in
            "\(i == now ? "▶ " : "")\(Ui.clock(Double(c.frame) / Double(fps)))   \(c.title)"
        }
        choose("Chapters", names, from: chaptersButton) { [weak self] which in
            guard let self = self else { return }
            self.jumpTo(self.chapters[which])
        }
    }

    private func chooseSpeed() {
        let names = PlayerViewController.SPEEDS.map { $0 == speed ? "✓  \(label($0))" : label($0) }
        choose("Playback speed", names, from: speedButton) { [weak self] which in
            guard let self = self else { return }
            self.speed = PlayerViewController.SPEEDS[which]
            self.panim.setSpeed(self.speed)
            self.speedButton.setTitle(self.label(self.speed), for: .normal)
            self.nowPlaying()
        }
    }

    /** A list to pick from (the Kotlin's AlertDialog.setItems): a sheet, anchored on an iPad. */
    private func choose(_ title: String, _ items: [String], from anchor: UIView, _ picked: @escaping (Int) -> Void) {
        let sheet = UIAlertController(title: title, message: nil, preferredStyle: .actionSheet)
        for (index, item) in items.enumerated() {
            sheet.addAction(UIAlertAction(title: item, style: .default) { _ in picked(index) })
        }
        sheet.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        if let popover = sheet.popoverPresentationController {
            popover.sourceView = anchor
            popover.sourceRect = anchor.bounds
        }
        hideControls?.cancel()
        present(sheet, animated: true)
    }

    private func label(_ value: Double) -> String {
        (value == Double(Int(value)) ? "\(Int(value))" : "\(value)") + "×"
    }

    // ---- gestures and the timeline ---------------------------------------------------------------------------------

    @objc private func tapped() {
        setControls(!controlsShown)
    }

    @objc private func doubleTapped(_ gesture: UITapGestureRecognizer) {
        let x = gesture.location(in: overlay).x
        let third = overlay.bounds.width / 3
        if x < third {
            skip(-PlayerViewController.SKIP_SECONDS)
        } else if x > 2 * third {
            skip(PlayerViewController.SKIP_SECONDS)
        } else {
            togglePlay()
        }
    }

    /** Taps on a button, the timeline or the end card are theirs, not the picture's. */
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
        var view = touch.view
        while let v = view, v !== overlay {
            if v is UIControl || v is TimelineView || v === notice || v === endScrim { return false }
            view = v.superview
        }
        return true
    }

    func onScrubStart() {
        scrubbing = true
        scrubWasPlaying = wantPlaying
        hideControls?.cancel()
        // The picture follows the finger; the narration is sought once, where it lifts.
        panim.beginScrub()
    }

    func onScrub(_ fraction: Float) {
        panim.scrubTo(Int(fraction * Float(frameCount - 1)))
        showTime(fraction * Float(frameCount - 1))
    }

    func onScrubEnd(_ fraction: Float) {
        scrubbing = false
        panim.endScrub(Int(fraction * Float(frameCount - 1)))
        endShown = false
        endScrim.isHidden = true
        if scrubWasPlaying { scheduleHide() }
        nowPlaying()
    }

    // ---- controls -------------------------------------------------------------------------------------------------

    private func setControls(_ show: Bool) {
        controlsShown = show
        controls.layer.removeAllAnimations()
        if show {
            controls.isHidden = false
            UIView.animate(withDuration: 0.15, delay: 0, options: [.allowUserInteraction, .beginFromCurrentState]) {
                self.controls.alpha = 1
            }
            if wantPlaying { scheduleHide() }
        } else {
            UIView.animate(withDuration: 0.22, delay: 0, options: [.allowUserInteraction, .beginFromCurrentState],
                           animations: { self.controls.alpha = 0 },
                           completion: { _ in if !self.controlsShown { self.controls.isHidden = true } })
        }
        setNeedsUpdateOfHomeIndicatorAutoHidden()
    }

    private func scheduleHide() {
        hideControls?.cancel()
        guard wantPlaying else { return }
        let work = DispatchWorkItem { [weak self] in
            guard let self = self, self.wantPlaying, !self.scrubbing, self.presentedViewController == nil else { return }
            self.setControls(false)
        }
        hideControls = work
        DispatchQueue.main.asyncAfter(deadline: .now() + PlayerViewController.HIDE_AFTER_SECONDS, execute: work)
    }

    private func loading(_ on: Bool, _ text: String = "", _ share: Float = -1) {
        if on { spinner.startAnimating() } else { spinner.stopAnimating() }
        loadingLabel.isHidden = !(on && !text.isEmpty)
        loadingLabel.text = text
        loadingBar.isHidden = !(on && share >= 0)
        if share >= 0 { loadingBar.setProgress(share, animated: true) }
    }

    private func showNotice(_ text: String, action: String? = nil, onAction: (() -> Void)? = nil) {
        let shown = NSMutableAttributedString(string: text, attributes: [.foregroundColor: Ui.TEXT, .font: Ui.regular(13)])
        if let action = action {
            shown.append(NSAttributedString(string: "    \(action)",
                                            attributes: [.foregroundColor: Ui.ACCENT, .font: Ui.medium(13)]))
        }
        notice.attributedText = shown
        noticeAction = onAction
        notice.isHidden = false
        notice.layer.removeAllAnimations()
        notice.alpha = 1
        UIView.animate(withDuration: 0.4, delay: 5, options: [.allowUserInteraction], animations: {
            self.notice.alpha = 0
        }, completion: { done in if done { self.notice.isHidden = true } })
    }

    @objc private func noticeTapped() {
        notice.layer.removeAllAnimations()
        notice.isHidden = true
        let action = noticeAction
        noticeAction = nil
        action?()
    }

    private func showEnd() {
        endShown = true
        endCard.arrangedSubviews.forEach { $0.removeFromSuperview() }
        func choice(_ icon: Icon, _ label: String, _ action: @escaping () -> Void) -> UIView {
            let control = CardView()
            control.layer.cornerRadius = 14
            control.onTap = action
            control.accessibilityLabel = label
            let circle = UIImageView(image: Ui.image(icon, side: 32, color: Ui.TEXT))
            circle.contentMode = .center
            circle.backgroundColor = Ui.argb(0x33FFFFFF)
            circle.layer.cornerRadius = 30
            circle.widthAnchor.constraint(equalToConstant: 60).isActive = true
            circle.heightAnchor.constraint(equalToConstant: 60).isActive = true
            let words = Ui.text(13, Ui.TEXT, medium: true, lines: 2)
            words.text = label
            words.textAlignment = .center
            words.widthAnchor.constraint(lessThanOrEqualToConstant: 180).isActive = true
            let stack = UIStackView(arrangedSubviews: [circle, words])
            stack.axis = .vertical
            stack.alignment = .center
            stack.spacing = 8
            stack.isUserInteractionEnabled = false
            stack.translatesAutoresizingMaskIntoConstraints = false
            control.addSubview(stack)
            NSLayoutConstraint.activate([
                stack.topAnchor.constraint(equalTo: control.topAnchor, constant: 10),
                stack.bottomAnchor.constraint(equalTo: control.bottomAnchor, constant: -10),
                stack.leadingAnchor.constraint(equalTo: control.leadingAnchor, constant: 18),
                stack.trailingAnchor.constraint(equalTo: control.trailingAnchor, constant: -18),
            ])
            return control
        }
        endCard.addArrangedSubview(choice(.REPLAY, "Watch again") { [weak self] in
            self?.seekSeconds(0)
            self?.play()
        })
        if case .saved(let entry, _) = lecture, let next = Lectures.nextInSeries(entry) {
            endCard.addArrangedSubview(choice(.NEXT, "Up next: \(next.shortTitle)") { [weak self] in
                guard let self = self else { return }
                Lectures.forget(self.lecture.key)
                let following = PlayerViewController(
                    lecture: .saved(next, dir: Lectures.savedRoot.appendingPathComponent(next.buildId, isDirectory: true)),
                    fromStart: false)
                let presenter = self.presentingViewController
                self.dismiss(animated: false) { presenter?.present(following, animated: true) }
            })
        }
        endScrim.isHidden = false
        setControls(false)
    }

    // ---- the clock ---------------------------------------------------------------------------------------------

    /** Fifteen times a second: the timeline, the time, the chapter, buffering, the end. */
    private func sync() {
        guard let playback = panim.playback else { return }
        // The network fell behind the narration: hold the picture with it, as a video buffers.
        if wantPlaying && !scrubbing && !heldForNetwork && panim.audioBuffering {
            heldForNetwork = true
            panim.pause()
            loading(true, "Buffering…")
        } else if heldForNetwork && !panim.audioBuffering {
            heldForNetwork = false
            loading(false)
            if wantPlaying { panim.play() }
        }
        if !audioProblemShown, let problem = panim.audioProblem {
            audioProblemShown = true
            showNotice("Playing without narration: \(problem)")
        }

        let frame = playback.currentFrame()
        if !scrubbing {
            timeline.played = Float(frame) / Float(max(frameCount - 1, 1))
            showTime(Float(frame))
        }
        timeline.loaded = max(loadedFraction, timeline.played)

        let chapter = currentChapter(frame)
        if chapter != shownChapter {
            shownChapter = chapter
            if chapter >= 0 && chapter < chapters.count {
                chapterLabel.text = "Chapter \(chapter + 1) · \(chapters[chapter].title)"
            } else {
                chapterLabel.text = lecture.subtitle
            }
            for row in chapterList.arrangedSubviews where row.tag > 0 {
                row.backgroundColor = row.tag == chapter + 1 ? Ui.SURFACE_HIGH : .clear
            }
        }

        if wantPlaying && !scrubbing && !playback.playing && frame >= frameCount - 1 && !endShown {
            wantPlaying = false
            UIApplication.shared.isIdleTimerDisabled = false
            setPlayIcon(.REPLAY, "Watch again")
            Lectures.forget(lecture.key)
            showEnd()
            nowPlaying()
        }

        if wantPlaying && Date().timeIntervalSince(lastSaved) > 5 { remember() }
    }

    private func showTime(_ frame: Float) {
        let total = Double(frameCount) / Double(fps)
        timeLabel.text = "\(Ui.clock(Double(frame) / Double(fps))) / \(Ui.clock(total))"
    }

    /** Where the viewer got to, for the library's progress bar and for resuming. */
    private func remember() {
        guard let playback = panim.playback, frames != nil, !endShown else { return }
        lastSaved = Date()
        Lectures.remember(lecture.key, at: Double(playback.currentFrame()) / Double(fps),
                          of: Double(frameCount) / Double(fps))
    }

    // ---- interruptions, the lock screen -----------------------------------------------------------------------------

    private func listen() {
        let center = NotificationCenter.default
        // A call, another app's sound: stop, and let the viewer start again.
        observers.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil,
                                            queue: .main) { [weak self] note in
            let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            if raw == AVAudioSession.InterruptionType.began.rawValue, self?.wantPlaying == true { self?.pause() }
        })
        // Headphones pulled out: stop, as a video app does, rather than speak to the room.
        observers.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil,
                                            queue: .main) { [weak self] note in
            let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            if raw == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue, self?.wantPlaying == true {
                self?.pause()
            }
        })
        // Away from the app: a narrated lecture plays on (it is the clock; the picture catches up on return), a
        // silent one has nothing to play and stops.
        observers.append(center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil,
                                            queue: .main) { [weak self] _ in
            guard let self = self else { return }
            if self.wantPlaying && !self.panim.hasAudio { self.pause() }
            self.remember()
        })

        let commands = MPRemoteCommandCenter.shared()
        remoteTargets.append((commands.playCommand, commands.playCommand.addTarget { [weak self] _ in
            guard let self = self, self.frames != nil else { return .noActionableNowPlayingItem }
            if !self.wantPlaying { self.play() }
            return .success
        }))
        remoteTargets.append((commands.pauseCommand, commands.pauseCommand.addTarget { [weak self] _ in
            if self?.wantPlaying == true { self?.pause() }
            return .success
        }))
        remoteTargets.append((commands.togglePlayPauseCommand, commands.togglePlayPauseCommand.addTarget {
            [weak self] _ in
            self?.togglePlay()
            return .success
        }))
    }

    private func nowPlaying() {
        guard frames != nil, let playback = panim.playback else { return }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = [
            MPMediaItemPropertyTitle: lecture.title,
            MPMediaItemPropertyArtist: lecture.subtitle,
            MPMediaItemPropertyPlaybackDuration: Double(frameCount) / Double(fps),
            MPNowPlayingInfoPropertyElapsedPlaybackTime: Double(playback.currentFrame()) / Double(fps),
            MPNowPlayingInfoPropertyPlaybackRate: wantPlaying ? speed : 0.0,
        ]
    }
}

/** A flag one thread sets and another reads (the Kotlin's AtomicBoolean), and what to stop when it is set. */
final class CancelFlag {
    private let lock = NSLock()
    private var value = false
    private var actions: [() -> Void] = []

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    /** Run [action] on cancelling (now, if that has happened). */
    func onCancel(_ action: @escaping () -> Void) {
        lock.lock()
        let now = value
        if !now { actions.append(action) }
        lock.unlock()
        if now { action() }
    }

    func cancel() {
        lock.lock()
        value = true
        let pending = actions
        actions.removeAll()
        lock.unlock()
        pending.forEach { $0() }
    }
}
