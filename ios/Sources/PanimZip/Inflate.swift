// Raw DEFLATE (RFC 1951) decompression in Swift, for reading a library zip.
//
// The Kotlin import (player/core LibraryImport.kt) leans on java.util.zip; PanimCore imports Foundation only, and
// Apple's Compression framework is not on Linux, where the port is checked. So the zip layer carries its own
// inflater: stored, fixed-Huffman and dynamic-Huffman blocks, streaming -- compressed bytes are pulled as needed and
// output leaves in chunks through a 64 KB window -- so a large entry never sits in memory whole.

import Foundation

/// CRC-32 (ISO-HDLC, as zip uses: reflected 0xEDB88320, inverted start and end).
public struct CRC32 {
    public private(set) var value: UInt32 = 0

    public init() {}

    static let table: [UInt32] = (0..<256).map { i -> UInt32 in
        var c = UInt32(i)
        for _ in 0..<8 { c = c & 1 != 0 ? 0xEDB8_8320 ^ (c >> 1) : c >> 1 }
        return c
    }

    public mutating func update(_ bytes: UnsafeBufferPointer<UInt8>) {
        var c = ~value
        CRC32.table.withUnsafeBufferPointer { t in
            for b in bytes { c = t[Int((c ^ UInt32(b)) & 0xFF)] ^ (c >> 8) }
        }
        value = ~c
    }

    public mutating func update(_ bytes: [UInt8]) {
        bytes.withUnsafeBufferPointer { update($0) }
    }

    public static func checksum(_ bytes: [UInt8]) -> UInt32 {
        var crc = CRC32()
        crc.update(bytes)
        return crc.value
    }
}

public enum InflateError: Error, Equatable, CustomStringConvertible {
    case truncated
    case invalid(String)

    public var description: String {
        switch self {
        case .truncated: return "the compressed data ends early"
        case .invalid(let why): return "the compressed data is damaged (\(why))"
        }
    }
}

/// Streaming raw-DEFLATE decoder.
public final class Inflater {
    private let pull: () throws -> [UInt8]?
    private var input: [UInt8] = []
    private var pos = 0
    private var bitBuf: UInt64 = 0
    private var bitCount = 0
    private var padBits = 0                 // zero bits added past the end of the input
    private var inputEnded = false

    private static let windowSize = 1 << 16
    private static let windowMask = windowSize - 1
    private let window: UnsafeMutablePointer<UInt8>
    private var written = 0                 // bytes produced in all
    private var flushed = 0                 // bytes handed to the sink

    /// [pull] gives the next piece of compressed input, or nil when there is no more.
    public init(pull: @escaping () throws -> [UInt8]?) {
        self.pull = pull
        window = .allocate(capacity: Self.windowSize)
    }

    deinit { window.deallocate() }

    /// Bytes produced so far.
    public var outputCount: Int { written }

    /// Decode the whole stream, handing output to [sink] in pieces of up to 32 KB.
    public func run(_ sink: ([UInt8]) throws -> Void) throws {
        var last = false
        while !last {
            last = try bits(1) == 1
            switch try bits(2) {
            case 0: try storedBlock(sink)
            case 1: try huffmanBlock(Self.fixedLiterals, Self.fixedDistances, sink)
            case 2:
                let (lit, dist) = try dynamicTables()
                try huffmanBlock(lit, dist, sink)
            default: throw InflateError.invalid("block type 3")
            }
        }
        try flush(sink)
    }

    /// Inflate [data] in one go.
    public static func inflate(_ data: [UInt8]) throws -> [UInt8] {
        var given = false
        let inflater = Inflater { () -> [UInt8]? in
            if given { return nil }
            given = true
            return data
        }
        var out: [UInt8] = []
        try inflater.run { out.append(contentsOf: $0) }
        return out
    }

    // MARK: bits

    private func refill() throws {
        while bitCount <= 56 {
            if pos == input.count {
                if !inputEnded, let more = try pull() {
                    input = more
                    pos = 0
                    continue
                }
                inputEnded = true
                // Pad with zeros so a Huffman lookup near the end can peek; consuming them is an error.
                bitCount += 8
                padBits += 8
                if padBits > 64 { throw InflateError.truncated }
                continue
            }
            bitBuf |= UInt64(input[pos]) << UInt64(bitCount)
            pos += 1
            bitCount += 8
        }
    }

    @inline(__always) private func bits(_ n: Int) throws -> Int {
        if bitCount < n { try refill() }
        let v = Int(bitBuf & ((1 << UInt64(n)) - 1))
        try drop(n)
        return v
    }

    @inline(__always) private func drop(_ n: Int) throws {
        bitBuf >>= UInt64(n)
        bitCount -= n
        if bitCount < padBits { throw InflateError.truncated }
    }

    // MARK: output

    @inline(__always) private func put(_ byte: UInt8) {
        window[written & Self.windowMask] = byte
        written += 1
    }

    private func flush(_ sink: ([UInt8]) throws -> Void) throws {
        while flushed < written {
            let start = flushed & Self.windowMask
            let n = min(written - flushed, Self.windowSize - start)
            try sink(Array(UnsafeBufferPointer(start: window + start, count: n)))
            flushed += n
        }
    }

    // MARK: blocks

    private func storedBlock(_ sink: ([UInt8]) throws -> Void) throws {
        try drop(bitCount & 7)                         // to a byte boundary
        let len = try bits(16)
        let nlen = try bits(16)
        guard len == (~nlen & 0xFFFF) else { throw InflateError.invalid("stored length check") }
        var left = len
        while left > 0 && bitCount >= 8 {               // bytes already in the bit buffer
            put(UInt8(try bits(8)))
            left -= 1
        }
        while left > 0 {
            if pos == input.count {
                guard !inputEnded, let more = try pull() else { throw InflateError.truncated }
                input = more
                pos = 0
                continue
            }
            let n = min(left, input.count - pos, 32 * 1024)
            for i in 0..<n { put(input[pos + i]) }
            pos += n
            left -= n
            if written - flushed >= 32 * 1024 { try flush(sink) }
        }
        if written - flushed >= 32 * 1024 { try flush(sink) }
    }

    private static let lengthBase: [Int] = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59,
                                            67, 83, 99, 115, 131, 163, 195, 227, 258]
    private static let lengthExtra: [Int] = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
                                             4, 4, 4, 4, 5, 5, 5, 5, 0]
    private static let distBase: [Int] = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513,
                                          769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577]
    private static let distExtra: [Int] = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
                                           9, 9, 10, 10, 11, 11, 12, 12, 13, 13]

    private func huffmanBlock(_ lit: Huffman, _ dist: Huffman, _ sink: ([UInt8]) throws -> Void) throws {
        while true {
            let sym = try decode(lit)
            if sym < 256 {
                put(UInt8(sym))
            } else if sym == 256 {
                break
            } else {
                let li = sym - 257
                guard li < 29 else { throw InflateError.invalid("length code \(sym)") }
                let length = Self.lengthBase[li] + (Self.lengthExtra[li] > 0 ? try bits(Self.lengthExtra[li]) : 0)
                let di = try decode(dist)
                guard di < 30 else { throw InflateError.invalid("distance code \(di)") }
                let distance = Self.distBase[di] + (Self.distExtra[di] > 0 ? try bits(Self.distExtra[di]) : 0)
                guard distance <= written else { throw InflateError.invalid("distance past the start") }
                var from = written - distance
                for _ in 0..<length {
                    put(window[from & Self.windowMask])
                    from += 1
                }
            }
            if written - flushed >= 32 * 1024 { try flush(sink) }
        }
    }

    @inline(__always) private func decode(_ h: Huffman) throws -> Int {
        if bitCount < h.maxBits { try refill() }
        let entry = h.table[Int(bitBuf & UInt64(h.mask))]
        let len = Int(entry & 15)
        guard len > 0 else { throw InflateError.invalid("no such Huffman code") }
        try drop(len)
        return Int(entry >> 4)
    }

    private static let codeLengthOrder = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]

    private func dynamicTables() throws -> (Huffman, Huffman) {
        let hlit = try bits(5) + 257
        let hdist = try bits(5) + 1
        let hclen = try bits(4) + 4
        guard hlit <= 286, hdist <= 30 else { throw InflateError.invalid("too many codes") }
        var clens = [Int](repeating: 0, count: 19)
        for i in 0..<hclen { clens[Self.codeLengthOrder[i]] = try bits(3) }
        let clh = try Huffman(lengths: clens)
        var lengths: [Int] = []
        lengths.reserveCapacity(hlit + hdist)
        while lengths.count < hlit + hdist {
            let sym = try decode(clh)
            switch sym {
            case 0...15: lengths.append(sym)
            case 16:
                guard let prev = lengths.last else { throw InflateError.invalid("repeat with nothing before") }
                lengths += repeatElement(prev, count: 3 + (try bits(2)))
            case 17: lengths += repeatElement(0, count: 3 + (try bits(3)))
            default: lengths += repeatElement(0, count: 11 + (try bits(7)))
            }
        }
        guard lengths.count == hlit + hdist else { throw InflateError.invalid("code lengths overrun") }
        guard lengths[256] > 0 else { throw InflateError.invalid("no end-of-block code") }
        return (try Huffman(lengths: Array(lengths[0..<hlit])), try Huffman(lengths: Array(lengths[hlit...])))
    }

    private static let fixedLiterals = try! Huffman(
        lengths: [Int](repeating: 8, count: 144) + [Int](repeating: 9, count: 112)
            + [Int](repeating: 7, count: 24) + [Int](repeating: 8, count: 8))
    private static let fixedDistances = try! Huffman(lengths: [Int](repeating: 5, count: 30))
}

/// A canonical Huffman code as one lookup table indexed by the next maxBits input bits (LSB first): each entry is
/// symbol << 4 | code length, 0 where no code lands (an incomplete code, allowed for distances).
struct Huffman {
    let table: [UInt16]
    let maxBits: Int
    let mask: Int

    init(lengths: [Int]) throws {
        var maxBits = 0
        var counts = [Int](repeating: 0, count: 16)
        for l in lengths where l > 0 {
            counts[l] += 1
            maxBits = max(maxBits, l)
        }
        maxBits = max(maxBits, 1)
        // Over-subscribed codes are invalid; incomplete ones are allowed.
        var left = 1
        for l in 1...15 {
            left = left << 1 - counts[l]
            guard left >= 0 else { throw InflateError.invalid("over-subscribed Huffman code") }
        }
        var next = [Int](repeating: 0, count: 16)
        var code = 0
        for l in 1...15 {
            next[l] = code
            code = (code + counts[l]) << 1
        }
        var table = [UInt16](repeating: 0, count: 1 << maxBits)
        for (symbol, l) in lengths.enumerated() where l > 0 {
            let c = next[l]
            next[l] += 1
            var reversed = 0
            for b in 0..<l where c & (1 << b) != 0 { reversed |= 1 << (l - 1 - b) }
            let entry = UInt16(symbol << 4 | l)
            var i = reversed
            while i < table.count {
                table[i] = entry
                i += 1 << l
            }
        }
        self.table = table
        self.maxBits = maxBits
        self.mask = (1 << maxBits) - 1
    }
}
