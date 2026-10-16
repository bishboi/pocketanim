// Ported from player/core/src/main/kotlin/com/pocketanim/core/Frames.kt.
import Foundation

/**
 * A source of frames, however they come to exist.
 *
 * Tier 3 decodes them; tier 1 computes them. The renderer is handed this and
 * cannot tell which, which is what lets one renderer serve both tiers.
 *
 * Geometry is fetched through [shape] rather than exposed as an array because a
 * computing source grows and truncates its atlas as it seeks -- a caller
 * holding the array across frames would be holding a stale one.
 *
 * The calls that position a computing source can fail half-way (a program that names something it never
 * declared), as they throw in Kotlin; here they `throw`, and [recover] starts the source again clean.
 */
public protocol Frames: AnyObject {
    var fps: Int { get }
    var frameCount: Int { get }

    /** The clear colour, ARGB. A sampled container has none and means black. */
    var background: Int32 { get }

    func shape(_ atlasId: Int) -> [Float]

    /** The camera for this frame, or nil for a 2D scene. */
    func camera(_ index: Int) throws -> [Float]?

    /**
     * The ordered instance list for this frame.
     *
     * Draw order is painter order, so the order is part of the answer, not an
     * implementation detail.
     */
    func instances(_ index: Int) throws -> [Instance]

    /**
     * The raster pictures showing in this frame, each with the instance it is drawn before. Called after
     * [instances] for the same frame. A sampled container has none.
     */
    func images(_ index: Int) throws -> [ImageDraw]

    /** A picture's file (PNG), by the name an [ImageDraw] carries; nil when the source has none. */
    func imageBytes(_ src: String) -> [UInt8]?

    /**
     * What frame [index] shows, as a number: two frames with the same key are the same picture, so a player that
     * has one on screen need not draw the other (a lecture is mostly holds). [FramesConstants.UNKNOWN] when the
     * source cannot say.
     */
    func contentKey(_ index: Int) throws -> Int64

    /** After a frame failed half-made: start again from a clean state, so the next frame is made whole. */
    func recover()

    /** The pictures (by [ImageDraw.src]) that show from frame [from] to [to]: to be decoded before they are due. */
    func imagesBetween(_ from: Int, _ to: Int) -> [String]
}

public extension Frames {
    var background: Int32 { Int32(bitPattern: 0xFF00_0000) }
    func images(_ index: Int) throws -> [ImageDraw] { [] }
    func imageBytes(_ src: String) -> [UInt8]? { nil }
    func contentKey(_ index: Int) throws -> Int64 { FramesConstants.UNKNOWN }
    func recover() {}
    func imagesBetween(_ from: Int, _ to: Int) -> [String] { [] }
}

/** Frames' companion object. */
public enum FramesConstants {
    public static let UNKNOWN = Int64.min
}

/**
 * One picture in one frame: its pixel (u, v) lands at UL + u/[width] (UR - UL) + v/[height] (DL - UL), [corners]
 * being ulx, uly, urx, ury, dlx, dly in scene units; drawn at [alpha] just before instance [before] of the frame
 * (after every object at or below its z).
 */
public final class ImageDraw {
    public let src: String
    public let width: Int
    public let height: Int
    public let alpha: Float
    public let corners: [Float]
    public let before: Int

    public init(src: String, width: Int, height: Int, alpha: Float, corners: [Float], before: Int) {
        self.src = src
        self.width = width
        self.height = height
        self.alpha = alpha
        self.corners = corners
        self.before = before
    }
}
