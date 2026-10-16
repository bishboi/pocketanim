// Ported from player/app/src/main/kotlin/com/pocketanim/player/TimelineView.kt.
import UIKit

/** TimelineView.Listener in the Kotlin (a protocol cannot nest in a class before Swift 5.10). */
protocol TimelineListener: AnyObject {
    func onScrubStart()
    func onScrub(_ fraction: Float)
    func onScrubEnd(_ fraction: Float)
}

/**
 * The seek bar: what has played, what is here to play (a lecture still arriving), the chapters as gaps in the
 * track, and while a finger is on it, a bubble with the time and the chapter it would land in.
 */
final class TimelineView: UIView {

    weak var listener: TimelineListener?

    /** 0..1 played. Ignored while scrubbing (the finger wins). */
    var played: Float = 0 {
        didSet {
            played = min(max(played, 0), 1)
            if !scrubbing && played != oldValue { setNeedsDisplay() }
        }
    }

    /** 0..1 of the lecture on the phone (the rest still coming); 1 when it all is. */
    var loaded: Float = 1 {
        didSet {
            loaded = min(max(loaded, 0), 1)
            if loaded != oldValue { setNeedsDisplay() }
        }
    }

    /** Where each chapter begins, 0..1, and their titles (for the bubble). */
    var chapters: [(Float, String)] = [] {
        didSet {
            if !chapters.elementsEqual(chapters.sorted { $0.0 < $1.0 }, by: { $0.0 == $1.0 }) {
                chapters.sort { $0.0 < $1.0 }
            }
            setNeedsDisplay()
        }
    }

    /** The lecture's length, for the bubble's time. */
    var durationSeconds = 0.0

    private(set) var scrubbing = false
    private var scrubAt: Float = 0
    private let bubble = Bubble()

    private let pad: CGFloat = 10
    private var barHeight: CGFloat { scrubbing ? 5 : 3.5 }
    private var barY: CGFloat { bounds.height - 18 }

    override init(frame: CGRect) {
        super.init(frame: frame)
        isOpaque = false
        backgroundColor = .clear
        contentMode = .redraw
        isAccessibilityElement = true
        accessibilityLabel = "Seek"
        accessibilityTraits = .adjustable
        clipsToBounds = false
        bubble.isHidden = true
        bubble.isUserInteractionEnabled = false
        addSubview(bubble)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    // Room above the bar for the bubble while scrubbing; the touch area stays generous for a thumb.
    override var intrinsicContentSize: CGSize { CGSize(width: UIView.noIntrinsicMetric, height: 64) }

    override func draw(_ rect: CGRect) {
        guard let c = UIGraphicsGetCurrentContext() else { return }
        let left = pad
        let right = bounds.width - pad
        let span = right - left
        let y = barY
        let h = barHeight
        let at = CGFloat(scrubbing ? scrubAt : played)
        let gap: CGFloat = 2
        // The track as chapter segments: a gap where each chapter begins.
        let cuts = chapters.map { CGFloat($0.0) }.filter { $0 > 0.002 && $0 < 0.998 }
        var start: CGFloat = 0
        for end in cuts + [1] {
            let x0 = left + span * start + (start > 0 ? gap / 2 : 0)
            let x1 = left + span * end - (end < 1 ? gap / 2 : 0)
            if x1 > x0 {
                segment(c, x0, x1, y, h, Ui.argb(0x40FFFFFF))
                let lx = min(x1, left + span * CGFloat(loaded))
                if lx > x0 { segment(c, x0, lx, y, h, Ui.argb(0x70FFFFFF)) }
                let px = min(x1, left + span * at)
                if px > x0 { segment(c, x0, px, y, h, Ui.ACCENT) }
            }
            start = end
        }
        let tx = left + span * at
        let r: CGFloat = scrubbing ? 9 : 6.5
        c.setFillColor(Ui.ACCENT.cgColor)
        c.fillEllipse(in: CGRect(x: tx - r, y: y - r, width: 2 * r, height: 2 * r))

        updateBubble(tx, y)
    }

    /**
     * The bubble with the time and the chapter, above the thumb while a finger is on the bar. A subview, so it can
     * rise above the bar's own bounds (into the row of controls over it) without making the touch area taller.
     */
    private func updateBubble(_ tx: CGFloat, _ y: CGFloat) {
        guard scrubbing && durationSeconds > 0 else {
            bubble.isHidden = true
            return
        }
        let at = CGFloat(scrubAt)
        bubble.title = String((chapters.last { CGFloat($0.0) <= at + 1e-4 }?.1 ?? "").prefix(34))
        bubble.time = Ui.clock(durationSeconds * Double(at))
        let size = bubble.measure()
        let bx = min(max(tx - size.width / 2, 0), bounds.width - size.width)
        bubble.frame = CGRect(x: bx, y: y - 16 - size.height, width: size.width, height: size.height)
        bubble.isHidden = false
        bubble.setNeedsDisplay()
    }

    private func segment(_ c: CGContext, _ x0: CGFloat, _ x1: CGFloat, _ y: CGFloat, _ h: CGFloat, _ color: UIColor) {
        c.setFillColor(color.cgColor)
        c.addPath(UIBezierPath(roundedRect: CGRect(x: x0, y: y - h / 2, width: x1 - x0, height: h),
                               cornerRadius: h / 2).cgPath)
        c.fillPath()
    }

    private func fractionAt(_ x: CGFloat) -> Float {
        Float(min(max((x - pad) / (bounds.width - 2 * pad), 0), 1))
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else { return }
        scrubbing = true
        scrubAt = fractionAt(touch.location(in: self).x)
        listener?.onScrubStart()
        listener?.onScrub(scrubAt)
        setNeedsDisplay()
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard scrubbing, let touch = touches.first else { return }
        scrubAt = fractionAt(touch.location(in: self).x)
        listener?.onScrub(scrubAt)
        setNeedsDisplay()
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        finish(touches)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        finish(touches)
    }

    private func finish(_ touches: Set<UITouch>) {
        guard scrubbing else { return }
        if let touch = touches.first { scrubAt = fractionAt(touch.location(in: self).x) }
        scrubbing = false
        played = scrubAt
        listener?.onScrubEnd(scrubAt)
        setNeedsDisplay()
    }

    // VoiceOver: swipe up or down to move a twentieth of the lecture.
    override func accessibilityIncrement() { nudge(0.05) }
    override func accessibilityDecrement() { nudge(-0.05) }

    private func nudge(_ by: Float) {
        let to = min(max(played + by, 0), 1)
        listener?.onScrubStart()
        listener?.onScrubEnd(to)
        played = to
    }

    override var accessibilityValue: String? {
        get { "\(Ui.clock(durationSeconds * Double(played))) of \(Ui.clock(durationSeconds))" }
        set {}
    }
}

/** The scrub bubble: the time over the chapter's title. */
private final class Bubble: UIView {
    var time = ""
    var title = ""
    private let timeAttrs: [NSAttributedString.Key: Any] = [.font: Ui.medium(14), .foregroundColor: Ui.TEXT]
    private let titleAttrs: [NSAttributedString.Key: Any] = [.font: Ui.regular(11.5), .foregroundColor: Ui.MUTED]

    override init(frame: CGRect) {
        super.init(frame: frame)
        isOpaque = false
        backgroundColor = .clear
        contentMode = .redraw
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    func measure() -> CGSize {
        let w = max((time as NSString).size(withAttributes: timeAttrs).width,
                    (title as NSString).size(withAttributes: titleAttrs).width) + 24
        return CGSize(width: ceil(w), height: title.isEmpty ? 30 : 46)
    }

    override func draw(_ rect: CGRect) {
        Ui.argb(0xE6202329).setFill()
        UIBezierPath(roundedRect: bounds, cornerRadius: 8).fill()
        let timeSize = (time as NSString).size(withAttributes: timeAttrs)
        (time as NSString).draw(at: CGPoint(x: (bounds.width - timeSize.width) / 2, y: 6), withAttributes: timeAttrs)
        if !title.isEmpty {
            let titleSize = (title as NSString).size(withAttributes: titleAttrs)
            (title as NSString).draw(at: CGPoint(x: (bounds.width - titleSize.width) / 2, y: 26),
                                     withAttributes: titleAttrs)
        }
    }
}
