// Where the narration's bytes come from: a file on the phone, or a stream that grows as they arrive.
//
// On Android AudioPlayer hands MediaExtractor a path or an http(s) URL and the extractor reads (and, over the
// network, waits) by itself. Here the reading is explicit: the player pulls whatever has arrived, and when it needs
// more than that it waits -- which is what AudioPlayer's `buffering` reports. Pure Swift, builds on Linux.

import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// The narration's bytes, complete or still arriving. Thread-safe.
public final class NarrationSource {
    private let condition = NSCondition()
    private var data: Data
    private var complete: Bool
    private var problem: String?
    /// Bytes the server said the file has (Content-Length), when it said.
    public private(set) var expectedLength: Int?
    private var task: URLSessionDataTask?
    private var session: URLSession?

    /// Called on an arbitrary thread whenever bytes arrive: (bytes so far, bytes in all when known).
    public var onProgress: ((Int, Int?) -> Void)?

    /// A narration that is all here.
    public init(data: Data) {
        self.data = data
        self.complete = true
    }

    /// A narration that will arrive through [append], ended by [finish] or [fail].
    public init() {
        self.data = Data()
        self.complete = false
    }

    /// A file on the phone, mapped rather than read (a WAV fallback can be hundreds of MB).
    public convenience init(contentsOf file: URL) throws {
        self.init(data: try Data(contentsOf: file, options: .alwaysMapped))
    }

    /// Stream [url] (a saved lecture's narration not yet on the phone). When [keepAt] is given the whole file is
    /// written there once it has all arrived, so it plays offline next time.
    public static func stream(_ url: URL, keepAt: URL? = nil, configuration: URLSessionConfiguration = .default)
        -> NarrationSource {
        let source = NarrationSource()
        let delegate = StreamDelegate(source: source, keepAt: keepAt)
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        let task = session.dataTask(with: url)
        source.condition.lock()
        source.session = session
        source.task = task
        source.condition.unlock()
        task.resume()
        return source
    }

    public func append(_ bytes: Data) {
        condition.lock()
        data.append(bytes)
        let count = data.count, expected = expectedLength
        condition.broadcast()
        condition.unlock()
        onProgress?(count, expected)
    }

    /// Every byte has arrived.
    public func finish() {
        condition.lock()
        complete = true
        condition.broadcast()
        condition.unlock()
    }

    /// The bytes stopped coming, for [message]'s reason.
    public func fail(_ message: String) {
        condition.lock()
        if !complete { problem = message }
        complete = true
        condition.broadcast()
        condition.unlock()
    }

    /// Stop a stream (the player is gone).
    public func cancel() {
        condition.lock()
        let task = self.task, session = self.session
        self.task = nil
        self.session = nil
        condition.unlock()
        task?.cancel()
        session?.invalidateAndCancel()
    }

    fileprivate func setExpectedLength(_ length: Int?) {
        condition.lock()
        expectedLength = length
        condition.unlock()
    }

    /// Bytes here so far.
    public var count: Int {
        condition.lock()
        defer { condition.unlock() }
        return data.count
    }

    /// No more bytes will arrive (all here, or failed).
    public var isComplete: Bool {
        condition.lock()
        defer { condition.unlock() }
        return complete
    }

    /// Why the bytes stopped coming before the end, when they did.
    public var failure: String? {
        condition.lock()
        defer { condition.unlock() }
        return problem
    }

    /// A copy of the bytes in [range], clipped to what has arrived.
    public func bytes(_ range: Range<Int>) -> [UInt8] {
        condition.lock()
        defer { condition.unlock() }
        let upper = min(range.upperBound, data.count)
        guard range.lowerBound < upper else { return [] }
        let start = data.startIndex
        return [UInt8](data[(start + range.lowerBound)..<(start + upper)])
    }

    /// Wait until more than [count] bytes are here or no more will come, at most [timeout] seconds. True when
    /// either happened.
    @discardableResult
    public func waitForMore(than count: Int, timeout: TimeInterval) -> Bool {
        let deadline = Date(timeIntervalSinceNow: timeout)
        condition.lock()
        defer { condition.unlock() }
        while data.count <= count && !complete {
            if !condition.wait(until: deadline) { return data.count > count || complete }
        }
        return true
    }

    /// What the narration is, once enough of it is here (a few hundred bytes), waiting up to [timeout] seconds for
    /// them. Throws when it is neither Ogg Opus nor PCM WAV, or the bytes did not come.
    public func format(timeout: TimeInterval = 30) throws -> NarrationFormat {
        let deadline = Date(timeIntervalSinceNow: timeout)
        var have = 0
        while true {
            have = count
            let head = bytes(0..<min(have, 64 * 1024))
            if head.count >= 4 {
                if head.starts(with: Array("RIFF".utf8)) {
                    if let wav = try WavHeader.parse(head) { return .wav(wav) }
                } else {
                    let demuxer = OggOpusDemuxer()
                    try demuxer.append(head)
                    if let opus = demuxer.head { return .oggOpus(opus) }
                }
            }
            if isComplete {
                throw failure.map { NarrationFormatError.badPage($0) } ?? NarrationFormatError.notOgg
            }
            if Date() >= deadline { throw NarrationFormatError.badPage("the narration did not arrive") }
            waitForMore(than: have, timeout: deadline.timeIntervalSinceNow)
        }
    }
}

/// The two forms a narration ships in.
public enum NarrationFormat: Equatable {
    case oggOpus(OpusHead)
    case wav(WavHeader)

    /// The rate the player's PCM runs at: Opus always decodes at 48 kHz.
    public var sampleRate: Int {
        switch self {
        case .oggOpus: return Opus.sampleRate
        case .wav(let header): return header.sampleRate
        }
    }

    public var channels: Int {
        switch self {
        case .oggOpus(let head): return head.channels
        case .wav(let header): return header.channels
        }
    }
}

private final class StreamDelegate: NSObject, URLSessionDataDelegate {
    private weak var source: NarrationSource?
    private let keepAt: URL?

    init(source: NarrationSource, keepAt: URL?) {
        self.source = source
        self.keepAt = keepAt
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            source?.fail("HTTP \(http.statusCode) for the narration")
            completionHandler(.cancel)
            return
        }
        let length = response.expectedContentLength
        source?.setExpectedLength(length > 0 ? Int(length) : nil)
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        source?.append(data)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        defer { session.finishTasksAndInvalidate() }
        guard let source else { return }
        if let error {
            source.fail(error.localizedDescription)
            return
        }
        if let expected = source.expectedLength, source.count < expected {
            source.fail("the narration stopped at \(source.count) of \(expected) bytes")
            return
        }
        if let keepAt {
            let all = Data(source.bytes(0..<source.count))
            let partial = keepAt.appendingPathExtension("part")
            if (try? all.write(to: partial)) != nil {
                try? FileManager.default.removeItem(at: keepAt)
                try? FileManager.default.moveItem(at: partial, to: keepAt)
            }
        }
        source.finish()
    }
}
