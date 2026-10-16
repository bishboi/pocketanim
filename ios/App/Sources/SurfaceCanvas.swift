// Ported from player/android/src/main/kotlin/com/pocketanim/android/SurfaceCanvas.kt.
import CoreGraphics

/**
 * The buffer a frame is drawn into, off the main thread.
 *
 * On Android this chose between a GPU-backed and a software canvas. CoreGraphics has only the one path -- a bitmap
 * context, rasterised on the CPU -- so what is kept from the Kotlin is the shape: acquire a target, draw the whole
 * frame (background included, nothing is preserved from the last one), release it as a picture for the view's layer.
 *
 * The context is reused while the size holds: making a 2-3 MP bitmap per frame is allocation the frame does not
 * need. `makeImage()` is copy-on-write, so the picture handed to the layer stays intact while the next frame draws.
 */
final class SurfaceCanvas {
    private var context: CGContext?
    private var widthPx = 0
    private var heightPx = 0

    /** What draws the frames. Reported, never assumed. */
    let description = "CoreGraphics (CPU raster)"

    func acquire(_ width: Int, _ height: Int) -> CGContext? {
        guard width > 0, height > 0 else { return nil }
        if let ready = context, width == widthPx, height == heightPx { return ready }
        let space = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                            space: space,
                            bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)
        widthPx = width
        heightPx = height
        return context
    }

    /** The frame just drawn, as a picture. */
    func release(_ context: CGContext) -> CGImage? {
        context.makeImage()
    }
}
