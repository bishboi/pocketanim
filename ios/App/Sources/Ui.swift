// Ported from player/app/src/main/kotlin/com/pocketanim/player/Ui.kt.
import UIKit

/**
 * The app's look, in code: colours, sizes, and the icons, drawn as paths (the app has no resources and no
 * libraries, so it builds its views itself). Dark throughout, like a video app: the picture is the bright thing.
 */
enum Ui {
    static let BG = argb(0xFF0E1014)
    static let SURFACE = argb(0xFF171A20)
    static let SURFACE_HIGH = argb(0xFF20242C)
    static let LINE = argb(0xFF2A2F38)
    static let TEXT = argb(0xFFF2F3F5)
    static let MUTED = argb(0xFF9AA1AD)
    static let FAINT = argb(0xFF6B7280)
    static let ACCENT = argb(0xFFF5B83D)          // the lectures' gold
    static let ACCENT_DARK = argb(0xFF3A2E12)
    static let GOOD = argb(0xFF5BC489)
    static let GOOD_DARK = argb(0xFF173325)
    static let SCRIM = argb(0x99000000)

    /** A colour from an ARGB literal, as the Kotlin writes them. */
    static func argb(_ value: UInt32) -> UIColor {
        UIColor(red: CGFloat((value >> 16) & 0xFF) / 255, green: CGFloat((value >> 8) & 0xFF) / 255,
                blue: CGFloat(value & 0xFF) / 255, alpha: CGFloat((value >> 24) & 0xFF) / 255)
    }

    static func medium(_ size: CGFloat) -> UIFont { .systemFont(ofSize: size, weight: .medium) }
    static func regular(_ size: CGFloat) -> UIFont { .systemFont(ofSize: size, weight: .regular) }
    static func mono(_ size: CGFloat) -> UIFont { .monospacedSystemFont(ofSize: size, weight: .regular) }

    static func text(_ size: CGFloat, _ color: UIColor = Ui.TEXT, medium: Bool = false, lines: Int = 0) -> UILabel {
        let label = UILabel()
        label.font = medium ? Ui.medium(size) : regular(size)
        label.textColor = color
        label.numberOfLines = lines
        label.lineBreakMode = .byTruncatingTail
        return label
    }

    /** A label with padding and a rounded background: chips, the time on a still, notices. */
    final class PaddedLabel: UILabel {
        var insets = UIEdgeInsets.zero
        override func drawText(in rect: CGRect) { super.drawText(in: rect.inset(by: insets)) }
        override var intrinsicContentSize: CGSize {
            let size = super.intrinsicContentSize
            return CGSize(width: size.width + insets.left + insets.right, height: size.height + insets.top + insets.bottom)
        }
        override func textRect(forBounds bounds: CGRect, limitedToNumberOfLines lines: Int) -> CGRect {
            let inner = super.textRect(forBounds: bounds.inset(by: insets), limitedToNumberOfLines: lines)
            return inner.inset(by: UIEdgeInsets(top: -insets.top, left: -insets.left, bottom: -insets.bottom,
                                                right: -insets.right))
        }
    }

    /** A small rounded label: "On phone", "Streams", "Sample". */
    static func chip(_ label: String, _ color: UIColor, _ background: UIColor) -> UILabel {
        let chip = PaddedLabel()
        chip.text = label
        chip.font = medium(11)
        chip.textColor = color
        chip.backgroundColor = background
        chip.insets = UIEdgeInsets(top: 3, left: 8, bottom: 3, right: 8)
        chip.layer.cornerRadius = 10
        chip.layer.masksToBounds = true
        chip.textAlignment = .center
        return chip
    }

    /** A round icon button. */
    static func iconButton(_ icon: Icon, size: CGFloat = 44, tint: UIColor = Ui.TEXT, fill: UIColor = .clear,
                           description: String, action: @escaping () -> Void) -> UIButton {
        let button = UIButton(type: .custom)
        button.setImage(image(icon, side: size * 0.56, color: tint), for: .normal)
        button.backgroundColor = fill
        button.layer.cornerRadius = size / 2
        button.accessibilityLabel = description
        button.addAction(UIAction { _ in action() }, for: .touchUpInside)
        button.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            button.widthAnchor.constraint(equalToConstant: size),
            button.heightAnchor.constraint(equalToConstant: size),
        ])
        return button
    }

    /** 1:05:09, 24:05, 0:42. */
    static func clock(_ seconds: Double) -> String {
        let total = Int(max(seconds, 0))
        let h = total / 3600, m = (total / 60) % 60, s = total % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    /** "24 min", "1 h 5 min", "45 s". */
    static func length(_ seconds: Double) -> String {
        let total = Int(seconds)
        if total < 60 { return "\(total) s" }
        if total < 3600 { return "\((total + 30) / 60) min" }
        return "\(total / 3600) h \(((total % 3600) + 30) / 60) min"
    }

    static func bytes(_ count: Int64) -> String {
        if count >= 1_000_000 { return String(format: "%.1f MB", Double(count) / 1e6) }
        if count >= 1_000 { return String(format: "%.0f kB", Double(count) / 1e3) }
        return "\(count) B"
    }

    // ---- errors -------------------------------------------------------------------------------------------------

    /**
     * What an error says. A Swift error bridged to NSError says only "The operation couldn't be completed", so the
     * core's own errors (PanimError, carrying the Kotlin message text) are described, and Foundation's localised.
     */
    static func message(of error: Error) -> String {
        if let localized = error as? LocalizedError, let text = localized.errorDescription { return text }
        let ns = error as NSError
        if [NSCocoaErrorDomain, NSURLErrorDomain, NSPOSIXErrorDomain, NSOSStatusErrorDomain].contains(ns.domain) {
            return ns.localizedDescription
        }
        return String(describing: error)
    }

    /**
     * An error as a report: what was being done, the phone and app, and the whole error -- its type, message and
     * every underlying error -- so a failure on the phone can be read (and copied) without a cable and a console.
     */
    static func errorText(_ what: String, _ error: Error) -> String {
        let info = Bundle.main.infoDictionary
        let version = (info?["CFBundleShortVersionString"] as? String ?? "?") + " (" +
            (info?["CFBundleVersion"] as? String ?? "?") + ")"
        var text = "\(what)\n\n\(String(reflecting: type(of: error))): \(message(of: error))\n"
        var cause = (error as NSError).userInfo[NSUnderlyingErrorKey] as? Error
        var depth = 0
        while let underlying = cause, depth < 8 {
            text += "caused by \(String(reflecting: type(of: underlying))): \(message(of: underlying))\n"
            cause = (underlying as NSError).userInfo[NSUnderlyingErrorKey] as? Error
            depth += 1
        }
        var machine = utsname()
        uname(&machine)
        let model = withUnsafeBytes(of: &machine.machine) { raw in
            String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
        }
        let device = UIDevice.current
        text += "\napp \(version) · \(device.systemName) \(device.systemVersion) · \(model)\n\n"
        text += String(reflecting: error) + "\n"
        let ns = error as NSError
        if !ns.userInfo.isEmpty { text += "\n\(ns.domain) \(ns.code) \(ns.userInfo)\n" }
        return text
    }

    /** The full error in a sheet: selectable, scrollable, with Copy. [onClose] runs when it is dismissed. */
    static func showError(_ from: UIViewController, _ what: String, _ error: Error, onClose: (() -> Void)? = nil) {
        let text = errorText(what, error)
        NSLog("Pocketanim: %@", text)
        let sheet = ErrorViewController(title: what, text: text, onClose: onClose)
        var top = from
        while let presented = top.presentedViewController, !presented.isBeingDismissed { top = presented }
        guard top.viewIfLoaded?.window != nil else { return }
        top.present(sheet, animated: true)
    }
}

/** The error sheet: the report in monospace, Copy and Close. */
final class ErrorViewController: UIViewController {
    private let text: String
    private let onClose: (() -> Void)?

    init(title: String, text: String, onClose: (() -> Void)?) {
        self.text = text
        self.onClose = onClose
        super.init(nibName: nil, bundle: nil)
        self.title = title
        modalPresentationStyle = .pageSheet
        overrideUserInterfaceStyle = .dark
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = Ui.SURFACE
        let heading = Ui.text(17, Ui.TEXT, medium: true, lines: 3)
        heading.text = title
        let body = UITextView()
        body.text = text
        body.isEditable = false
        body.isSelectable = true
        body.font = Ui.mono(11)
        body.textColor = Ui.TEXT
        body.backgroundColor = Ui.BG
        body.layer.cornerRadius = 10
        body.textContainerInset = UIEdgeInsets(top: 12, left: 10, bottom: 12, right: 10)
        let copy = UIButton(type: .system)
        copy.setTitle("Copy", for: .normal)
        copy.titleLabel?.font = Ui.medium(16)
        copy.tintColor = Ui.ACCENT
        copy.addAction(UIAction { [weak self, weak copy] _ in
            UIPasteboard.general.string = self?.text
            copy?.setTitle("Copied", for: .normal)
        }, for: .touchUpInside)
        let close = UIButton(type: .system)
        close.setTitle("Close", for: .normal)
        close.titleLabel?.font = Ui.medium(16)
        close.tintColor = Ui.TEXT
        close.addAction(UIAction { [weak self] _ in self?.dismiss(animated: true) }, for: .touchUpInside)
        let buttons = UIStackView(arrangedSubviews: [UIView(), close, copy])
        buttons.spacing = 24
        let stack = UIStackView(arrangedSubviews: [heading, body, buttons])
        stack.axis = .vertical
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: guide.topAnchor, constant: 20),
            stack.leadingAnchor.constraint(equalTo: guide.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: guide.trailingAnchor, constant: -16),
            stack.bottomAnchor.constraint(equalTo: guide.bottomAnchor, constant: -12),
        ])
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed || presentingViewController == nil { onClose?() }
    }
}

enum Icon { case PLAY, PAUSE, REPLAY, BACK10, FORWARD10, BACK, CHAPTERS, FULLSCREEN, EXIT_FULLSCREEN, CLOUD, CHECK,
    IMPORT, REFRESH, MORE, NEXT, SPEED, DOWNLOAD }

extension Ui {
    /**
     * The app's icons, drawn on a 24-unit grid scaled to [side] points: no image files to ship or scale, crisp at
     * any size, tinted by colour. (IconDrawable in the Kotlin.)
     */
    static func image(_ icon: Icon, side: CGFloat, color: UIColor) -> UIImage {
        let format = UIGraphicsImageRendererFormat.preferred()
        format.opaque = false
        return UIGraphicsImageRenderer(size: CGSize(width: side, height: side), format: format).image { context in
            let c = context.cgContext
            c.scaleBy(x: side / 24, y: side / 24)
            c.setFillColor(color.cgColor)
            c.setStrokeColor(color.cgColor)
            c.setLineWidth(2.2)
            c.setLineCap(.round)
            c.setLineJoin(.round)
            let path = CGMutablePath()
            // Android's addArc(oval, start, sweep): degrees, clockwise on a y-down screen -- increasing angle here.
            func arc(_ rect: CGRect, _ start: CGFloat, _ sweep: CGFloat) {
                let startRad = start * .pi / 180
                let center = CGPoint(x: rect.midX, y: rect.midY)
                path.move(to: CGPoint(x: center.x + rect.width / 2 * cos(startRad),
                                      y: center.y + rect.width / 2 * sin(startRad)))
                path.addRelativeArc(center: center, radius: rect.width / 2, startAngle: startRad,
                                    delta: sweep * .pi / 180)
            }
            func arrowHead(_ x: CGFloat, _ y: CGFloat) {
                c.move(to: CGPoint(x: x + 3.2, y: y))
                c.addLine(to: CGPoint(x: x - 1.6, y: y - 2.8))
                c.addLine(to: CGPoint(x: x - 1.6, y: y + 2.8))
                c.closePath()
                c.fillPath()
            }
            func stroke() {
                c.addPath(path)
                c.strokePath()
            }
            func fill() {
                c.addPath(path)
                c.fillPath()
            }
            switch icon {
            case .PLAY:
                path.addLines(between: [CGPoint(x: 8, y: 5.5), CGPoint(x: 19, y: 12), CGPoint(x: 8, y: 18.5)])
                path.closeSubpath()
                fill()
            case .PAUSE:
                path.addRoundedRect(in: CGRect(x: 6.5, y: 5, width: 3.5, height: 14), cornerWidth: 1, cornerHeight: 1)
                path.addRoundedRect(in: CGRect(x: 14, y: 5, width: 3.5, height: 14), cornerWidth: 1, cornerHeight: 1)
                fill()
            case .REPLAY, .REFRESH:
                arc(CGRect(x: 4.5, y: 4.5, width: 15, height: 15), -70, 300)
                stroke()
                arrowHead(9.2, 3.2)
            case .BACK10, .FORWARD10:
                c.saveGState()
                if icon == .FORWARD10 {
                    c.translateBy(x: 24, y: 0)
                    c.scaleBy(x: -1, y: 1)
                }
                arc(CGRect(x: 3.5, y: 3.5, width: 17, height: 17), -60, 290)
                stroke()
                arrowHead(9.5, 2.6)
                c.restoreGState()
                let label = "10" as NSString
                let attributes: [NSAttributedString.Key: Any] = [
                    .font: UIFont.systemFont(ofSize: 7.5, weight: .bold), .foregroundColor: color,
                ]
                let size = label.size(withAttributes: attributes)
                label.draw(at: CGPoint(x: 12 - size.width / 2, y: 15 - size.height * 0.8), withAttributes: attributes)
            case .BACK:
                path.move(to: CGPoint(x: 19, y: 12)); path.addLine(to: CGPoint(x: 5.5, y: 12))
                path.move(to: CGPoint(x: 11, y: 6)); path.addLine(to: CGPoint(x: 5, y: 12))
                path.addLine(to: CGPoint(x: 11, y: 18))
                stroke()
            case .CHAPTERS:
                for y in [CGFloat(7), 12, 17] {
                    c.fillEllipse(in: CGRect(x: 5 - 1.3, y: y - 1.3, width: 2.6, height: 2.6))
                    path.move(to: CGPoint(x: 9, y: y)); path.addLine(to: CGPoint(x: 20, y: y))
                }
                stroke()
            case .FULLSCREEN, .EXIT_FULLSCREEN:
                let inward = icon == .EXIT_FULLSCREEN
                for (cx, cy) in [(CGFloat(4), CGFloat(4)), (20, 4), (4, 20), (20, 20)] {
                    let dx: CGFloat = cx < 12 ? 1 : -1
                    let dy: CGFloat = cy < 12 ? 1 : -1
                    let x = inward ? cx + dx * 5 : cx
                    let y = inward ? cy + dy * 5 : cy
                    let sx = inward ? -dx : dx
                    let sy = inward ? -dy : dy
                    path.move(to: CGPoint(x: x + sx * 5, y: y)); path.addLine(to: CGPoint(x: x, y: y))
                    path.addLine(to: CGPoint(x: x, y: y + sy * 5))
                }
                stroke()
            case .CLOUD:
                path.addEllipse(in: CGRect(x: 4.5, y: 8.5, width: 9, height: 9))
                path.addEllipse(in: CGRect(x: 8.5, y: 5, width: 11, height: 11))
                path.addRoundedRect(in: CGRect(x: 4.5, y: 12.5, width: 16, height: 5.5), cornerWidth: 2.75,
                                    cornerHeight: 2.75)
                fill()
            case .CHECK:
                path.addLines(between: [CGPoint(x: 5, y: 12.5), CGPoint(x: 10, y: 17.5), CGPoint(x: 19.5, y: 7)])
                stroke()
            case .IMPORT:
                path.move(to: CGPoint(x: 12, y: 4)); path.addLine(to: CGPoint(x: 12, y: 15))
                path.addLines(between: [CGPoint(x: 7.5, y: 10.5), CGPoint(x: 12, y: 15), CGPoint(x: 16.5, y: 10.5)])
                path.addLines(between: [CGPoint(x: 5, y: 15.5), CGPoint(x: 5, y: 19.5), CGPoint(x: 19, y: 19.5),
                                        CGPoint(x: 19, y: 15.5)])
                stroke()
            case .DOWNLOAD:
                path.move(to: CGPoint(x: 12, y: 4)); path.addLine(to: CGPoint(x: 12, y: 16))
                path.addLines(between: [CGPoint(x: 7, y: 11), CGPoint(x: 12, y: 16), CGPoint(x: 17, y: 11)])
                path.move(to: CGPoint(x: 5.5, y: 20)); path.addLine(to: CGPoint(x: 18.5, y: 20))
                stroke()
            case .MORE:
                for y in [CGFloat(5.5), 12, 18.5] {
                    c.fillEllipse(in: CGRect(x: 12 - 1.9, y: y - 1.9, width: 3.8, height: 3.8))
                }
            case .NEXT:
                path.addLines(between: [CGPoint(x: 6, y: 6), CGPoint(x: 15, y: 12), CGPoint(x: 6, y: 18)])
                path.closeSubpath()
                path.addRoundedRect(in: CGRect(x: 16, y: 6, width: 2.5, height: 12), cornerWidth: 0.8,
                                    cornerHeight: 0.8)
                fill()
            case .SPEED:
                arc(CGRect(x: 3.5, y: 5, width: 17, height: 17), 180, 180)
                path.move(to: CGPoint(x: 12, y: 13.5)); path.addLine(to: CGPoint(x: 16.5, y: 9))
                stroke()
                c.fillEllipse(in: CGRect(x: 12 - 1.6, y: 13.5 - 1.6, width: 3.2, height: 3.2))
            }
        }
    }
}
