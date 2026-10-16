// Ported from player/android/src/main/kotlin/com/pocketanim/android/CanvasSink.kt.
import CoreGraphics
import Foundation
import ImageIO
import PanimCore

/**
 * [PathSink] on CoreGraphics.
 *
 * The context is put into *scene* coordinates -- y up, origin centred -- rather than converting points as they
 * arrive. Manim expresses stroke_width in scene units, so letting CoreGraphics scale the stroke is what makes widths
 * match Cairo instead of approximating them. A bitmap context is already y up, so unlike Skia's canvas the scale's
 * y is not negated.
 *
 * One path is built per instance and handed to the context once per paint: CoreGraphics consumes the context's own
 * path when it fills, and the renderer may fill and then stroke the same geometry.
 */
final class CGSink: PathSink {
    private var path = CGMutablePath()
    private var context: CGContext?

    /**
     * Point the sink at a context for one frame, cleared to [background] (ARGB). The caller owns [end], so an error
     * mid-frame cannot leave the context transformed.
     */
    func begin(_ target: CGContext, _ widthPx: Int, _ heightPx: Int, _ background: Int32) {
        context = target
        target.saveGState()
        target.setFillColor(CGSink.color(background))
        target.fill(CGRect(x: 0, y: 0, width: widthPx, height: heightPx))
        target.translateBy(x: CGFloat(widthPx) / 2, y: CGFloat(heightPx) / 2)
        target.scaleBy(x: CGFloat(Float(widthPx) / FRAME_WIDTH), y: CGFloat(Float(heightPx) / FRAME_HEIGHT))
        target.setLineCap(.round)
        target.setLineJoin(.round)
        target.setShouldAntialias(true)
        target.interpolationQuality = .medium
    }

    func end() {
        context?.restoreGState()
        context = nil
    }

    /** An ARGB colour (Int32, its bits as the Kotlin Int's) as a CGColor in sRGB. */
    static func color(_ argb: Int32) -> CGColor {
        let v = UInt32(bitPattern: argb)
        return CGColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                       blue: CGFloat(v & 0xFF) / 255, alpha: CGFloat(v >> 24) / 255)
    }

    private func setFill(_ argb: Int32) {
        let v = UInt32(bitPattern: argb)
        context?.setFillColor(red: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                              blue: CGFloat(v & 0xFF) / 255, alpha: CGFloat(v >> 24) / 255)
    }

    private func setStroke(_ argb: Int32) {
        let v = UInt32(bitPattern: argb)
        context?.setStrokeColor(red: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                                blue: CGFloat(v & 0xFF) / 255, alpha: CGFloat(v >> 24) / 255)
    }

    func strokeStyle(round: Bool) {
        context?.setLineJoin(round ? .round : .bevel)
    }

    func beginPath() {
        path = CGMutablePath()
    }

    func moveTo(_ x: Float, _ y: Float) {
        path.move(to: CGPoint(x: CGFloat(x), y: CGFloat(y)))
    }

    func cubicTo(_ x1: Float, _ y1: Float, _ x2: Float, _ y2: Float, _ x3: Float, _ y3: Float) {
        path.addCurve(to: CGPoint(x: CGFloat(x3), y: CGFloat(y3)),
                      control1: CGPoint(x: CGFloat(x1), y: CGFloat(y1)),
                      control2: CGPoint(x: CGFloat(x2), y: CGFloat(y2)))
    }

    func lineTo(_ x: Float, _ y: Float) {
        path.addLine(to: CGPoint(x: CGFloat(x), y: CGFloat(y)))
    }

    func closeSubpath() {
        path.closeSubpath()
    }

    func fillPath(_ argb: Int32) {
        guard let c = context, !path.isEmpty else { return }
        setFill(argb)
        c.addPath(path)
        c.fillPath(using: .winding)
    }

    func strokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        guard let c = context, !path.isEmpty else { return }
        setStroke(argb)
        c.setLineWidth(CGFloat(widthInSceneUnits))
        c.addPath(path)
        c.strokePath()
    }

    // Same geometry, one traversal: the renderer only asks when the two colours are identical and opaque.
    func fillAndStrokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        guard let c = context, !path.isEmpty else { return }
        setFill(argb)
        setStroke(argb)
        c.setLineWidth(CGFloat(widthInSceneUnits))
        c.addPath(path)
        c.drawPath(using: .fillStroke)
    }

    // ---- pictures ---------------------------------------------------------------------------------------------

    /**
     * Decoded pictures, by file, up to [IMAGE_CACHE_BYTES]: a lecture holds dozens and a frame shows one or two, so
     * the ones on screen stay decoded and the rest are dropped. A picture is decoded no larger than [IMAGE_MAX_PX]
     * on its long side -- more than a phone screen's worth of the stage.
     */
    private let bitmaps: NSCache<NSString, CGImage> = {
        let cache = NSCache<NSString, CGImage>()
        cache.totalCostLimit = CGSink.IMAGE_CACHE_BYTES
        return cache
    }()
    private let lock = NSLock()
    private var unreadable = Set<String>()
    /** Pictures being decoded ahead of their frames ([prefetch]). */
    private var pending = Set<String>()
    private let decoder = DispatchQueue(label: "panim-images", qos: .utility)

    /**
     * Decode [src] on the sink's own queue, ahead of the frame that shows it, so drawing it costs only the draw.
     * Ready ones (and ones already being decoded) are left alone.
     */
    func prefetch(_ src: String, _ bytes: @escaping (String) -> [UInt8]?) {
        if bitmaps.object(forKey: src as NSString) != nil { return }
        lock.lock()
        let skip = unreadable.contains(src) || pending.contains(src)
        if !skip { pending.insert(src) }
        lock.unlock()
        if skip { return }
        decoder.async { [weak self] in
            guard let self = self else { return }
            _ = self.decode(src, bytes)
            self.lock.lock()
            self.pending.remove(src)
            self.lock.unlock()
        }
    }

    private func decode(_ src: String, _ bytes: (String) -> [UInt8]?) -> CGImage? {
        if let ready = bitmaps.object(forKey: src as NSString) { return ready }
        lock.lock()
        let bad = unreadable.contains(src)
        lock.unlock()
        if bad { return nil }
        var decoded: CGImage?
        if let data = bytes(src), let source = CGImageSourceCreateWithData(Data(data) as CFData, nil) {
            // WebP and PNG both: ImageIO reads WebP from iOS 14. A thumbnail decode is a sampled decode, bounded
            // on its long side, and done now rather than at first draw.
            let options: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceThumbnailMaxPixelSize: CGSink.IMAGE_MAX_PX,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
            ]
            decoded = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
        }
        guard let image = decoded else {
            lock.lock()
            unreadable.insert(src)
            lock.unlock()
            return nil
        }
        bitmaps.setObject(image, forKey: src as NSString, cost: image.bytesPerRow * image.height)
        return image
    }

    func drawImage(_ image: ImageDraw, _ bytes: (String) -> [UInt8]?) {
        guard let c = context, let bitmap = decode(image.src, bytes) else { return }
        let k = image.corners
        guard k.count >= 6 else { return }
        // Bitmap pixel (u, v) -> scene: UL + u/w (UR - UL) + v/h (DL - UL), w and h the decoded bitmap's (a sampled
        // decode is smaller than the file, and covers the same corners). CoreGraphics draws an image into the unit
        // rect y up, its top row at y = h, so v = h - y: the y column is negated and the origin is DL.
        let w = CGFloat(bitmap.width)
        let h = CGFloat(bitmap.height)
        let ulx = CGFloat(k[0]), uly = CGFloat(k[1]), urx = CGFloat(k[2]), ury = CGFloat(k[3])
        let dlx = CGFloat(k[4]), dly = CGFloat(k[5])
        let matrix = CGAffineTransform(a: (urx - ulx) / w, b: (ury - uly) / w,
                                       c: -(dlx - ulx) / h, d: -(dly - uly) / h, tx: dlx, ty: dly)
        c.saveGState()
        c.concatenate(matrix)
        c.setAlpha(CGFloat(min(max(image.alpha, 0), 1)))
        c.draw(bitmap, in: CGRect(x: 0, y: 0, width: w, height: h))
        c.restoreGState()
    }

    /** Drop decoded pictures (a new scene, or the view going away). */
    func clearImages() {
        bitmaps.removeAllObjects()
        lock.lock()
        unreadable.removeAll()
        lock.unlock()
    }

    private static let IMAGE_CACHE_BYTES = 48 * 1024 * 1024
    private static let IMAGE_MAX_PX = 2048
}
