// Ported from player/android/src/main/kotlin/com/pocketanim/android/Thumbnails.kt.
import PanimCore
import UIKit

/**
 * A still of a lecture, for the library's cards: one frame drawn off screen by the same renderer that plays it.
 *
 * A lecture is a program, not a video, so there is no poster frame to read: this computes one. Opening a lecture
 * costs a moment, so a still is made once and kept as a PNG beside the lecture ([cached]).
 */
enum Thumbnails {

    /** A good frame to show: a little into the first chapter's body (past its title card), else a fifth in. */
    static func pick(_ frames: Frames, _ chapterStarts: [Int]) -> Int {
        let count = frames.frameCount
        if count <= 1 { return 0 }
        let first = chapterStarts.first
        let second = chapterStarts.count > 1 ? chapterStarts[1] : nil
        let guess: Int
        if let first = first, let second = second {
            guess = first + Int(Double(second - first) * 0.35)
        } else if let first = first {
            guess = first + frames.fps * 8
        } else {
            guess = count / 5
        }
        return min(max(guess, 0), count - 1)
    }

    /** Frame [index] drawn into a picture [width] pixels wide (16:9). */
    static func render(_ frames: Frames, _ index: Int, _ width: Int) throws -> UIImage {
        let height = Int(Float(width) * FRAME_HEIGHT / FRAME_WIDTH)
        guard let context = SurfaceCanvas().acquire(width, height) else {
            throw NSError(domain: "Thumbnails", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "cannot make a \(width)x\(height) bitmap"])
        }
        let sink = CGSink()
        sink.begin(context, width, height, frames.background)
        defer { sink.end() }
        try Renderer.drawFrame(frames, min(max(index, 0), frames.frameCount - 1), sink,
                               RenderOptions.forSurface(width))
        guard let image = context.makeImage() else {
            throw NSError(domain: "Thumbnails", code: 2, userInfo: [NSLocalizedDescriptionKey: "no picture"])
        }
        return UIImage(cgImage: image)
    }

    /** The still kept at [file], made by [make] the first time. Nil when it cannot be made. */
    static func cached(_ file: URL, _ make: () throws -> UIImage) -> UIImage? {
        if let kept = UIImage(contentsOfFile: file.path) { return kept }
        do {
            let image = try make()
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            if let png = image.pngData() { try png.write(to: file, options: .atomic) }
            return image
        } catch {
            // A card without its picture, not the app closing.
            NSLog("Thumbnails: no still for %@: %@", file.lastPathComponent, String(describing: error))
            return nil
        }
    }
}
