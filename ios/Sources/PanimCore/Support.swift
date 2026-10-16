// Support for the port, with no Kotlin file of its own: what the JVM gives the Kotlin core for free and Swift does
// not -- its exceptions, its number conversions and parsing, its String.format, its stable sorts, its
// insertion-ordered maps, and SHA-256 (java.security). Each helper says which Kotlin behaviour it reproduces, so
// the port's arithmetic and text agree with the Android player's to the bit.
import Foundation

// MARK: - Errors

/**
 * Kotlin's exceptions, as one Swift error. The case is the exception's class (Verify prints it, as Kotlin's
 * `e::class.simpleName` does) and the message is the text the Kotlin code builds, which the app shows.
 */
public enum PanimError: Error, CustomStringConvertible, Equatable {
    /** `require(...)`, a bad argument. */
    case illegalArgument(String)
    /** `error(...)`, `check(...)`. */
    case illegalState(String)
    /** `Map.getValue`, `first()` on nothing. */
    case noSuchElement(String)
    /** A list or array read past its end (the JVM's IndexOutOfBoundsException). */
    case indexOutOfBounds(String)
    /** A number that does not parse (`toInt()`, `toDouble()`). */
    case numberFormat(String)
    /** A container read past its end (ByteBuffer's BufferUnderflowException, which has no message). */
    case bufferUnderflow
    /** A file that could not be read. */
    case io(String)
    /** Kotlin's `!!` on a null. */
    case nullPointer(String)

    public var message: String? {
        switch self {
        case .illegalArgument(let m), .illegalState(let m), .noSuchElement(let m), .indexOutOfBounds(let m),
             .numberFormat(let m), .io(let m), .nullPointer(let m):
            return m
        case .bufferUnderflow:
            return nil
        }
    }

    /** The JVM exception this stands for, by its simple name. */
    public var kotlinName: String {
        switch self {
        case .illegalArgument: return "IllegalArgumentException"
        case .illegalState: return "IllegalStateException"
        case .noSuchElement: return "NoSuchElementException"
        case .indexOutOfBounds: return "IndexOutOfBoundsException"
        case .numberFormat: return "NumberFormatException"
        case .bufferUnderflow: return "BufferUnderflowException"
        case .io: return "IOException"
        case .nullPointer: return "NullPointerException"
        }
    }

    public var description: String { message ?? kotlinName }
}

/** Kotlin's `require(condition) { message }`. */
@inline(__always)
func require(_ condition: Bool, _ message: @autoclosure () -> String) throws {
    if !condition { throw PanimError.illegalArgument(message()) }
}

/** Kotlin's `Map.getValue`: the value, or NoSuchElementException with the JVM's message. */
func getValue<V>(_ map: [String: V], _ key: String) throws -> V {
    guard let value = map[key] else { throw PanimError.noSuchElement("Key \(key) is missing in the map.") }
    return value
}

/** `list[index]` as the JVM does it: past the end is an exception rather than a trap. */
func element<T>(_ list: [T], _ index: Int) throws -> T {
    guard index >= 0 && index < list.count else {
        throw PanimError.indexOutOfBounds("Index \(index) out of bounds for length \(list.count)")
    }
    return list[index]
}

// MARK: - Kotlin number conversions

/** Kotlin's `Double.toInt()`: towards zero, NaN to 0, saturating at Int's 32 bits. */
@inline(__always)
public func kToInt(_ d: Double) -> Int {
    if d.isNaN { return 0 }
    if d >= 2147483647.0 { return 2147483647 }
    if d <= -2147483648.0 { return -2147483648 }
    return Int(d)
}

/** Kotlin's `Float.toInt()`. */
@inline(__always)
public func kToInt(_ f: Float) -> Int { kToInt(Double(f)) }

/** Kotlin's `Double.toLong()`: towards zero, NaN to 0, saturating at 64 bits. */
@inline(__always)
public func kToLong(_ d: Double) -> Int64 {
    if d.isNaN { return 0 }
    if d >= 9223372036854775807.0 { return Int64.max }
    if d <= -9223372036854775808.0 { return Int64.min }
    return Int64(d)
}

/** A colour or bit pattern held in Kotlin's 32-bit Int, wrapped as the JVM wraps it. */
@inline(__always)
func i32(_ v: Int) -> Int32 { Int32(truncatingIfNeeded: v) }

/** Kotlin's `ushr` on an Int. */
@inline(__always)
func ushr(_ v: Int32, _ by: Int32) -> Int32 { Int32(bitPattern: UInt32(bitPattern: v) >> UInt32(by & 31)) }

/** Kotlin's `Float.toRawBits()`. */
@inline(__always)
func rawBits(_ f: Float) -> Int32 { Int32(bitPattern: f.bitPattern) }

/** `Math.toRadians` as JDK 9 and later compute it: one multiplication by the constant. */
@inline(__always)
func toRadians(_ degrees: Double) -> Double { degrees * 0.017453292519943295 }

/** `Math.floorMod` for Ints. */
@inline(__always)
func floorMod(_ x: Int, _ y: Int) -> Int {
    let m = x % y
    return (m != 0 && ((m < 0) != (y < 0))) ? m + y : m
}

/** Java's Character.isWhitespace, together with isSpaceChar as Kotlin's Char.isWhitespace does. */
func kIsWhitespace(_ c: UInt16) -> Bool {
    switch c {
    case 0x09...0x0D, 0x1C...0x20, 0x85, 0xA0, 0x1680, 0x2000...0x200A, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000:
        return true
    default:
        return false
    }
}

/** Kotlin's `String.trim()`. */
func kTrim(_ s: String) -> String {
    let units = Array(s.utf16)
    var start = 0
    var end = units.count
    while start < end && kIsWhitespace(units[start]) { start += 1 }
    while end > start && kIsWhitespace(units[end - 1]) { end -= 1 }
    if start == 0 && end == units.count { return s }
    return String(decoding: units[start..<end], as: UTF16.self)
}

/**
 * Kotlin's `String.toDouble()` (Java's Double.parseDouble): surrounding whitespace allowed, a trailing f/d type
 * letter allowed, "NaN" and "Infinity" spelled Java's way; anything else that is not a number throws.
 */
public func kDouble(_ text: String) throws -> Double {
    var s = text.trimmingCharacters(in: CharacterSet(charactersIn: " \t\n\r\u{0B}\u{0C}\u{00}"))
    if let last = s.last, "fFdD".contains(last), s.count > 1, !s.lowercased().hasPrefix("0x") {
        s.removeLast()
    }
    var body = Substring(s)
    var sign = 1.0
    if body.hasPrefix("-") { sign = -1; body = body.dropFirst() } else if body.hasPrefix("+") { body = body.dropFirst() }
    if body == "NaN" { return Double.nan }
    if body == "Infinity" { return sign * Double.infinity }
    // Digits, an optional point, an optional exponent: what parseDouble takes in decimal form. Swift's own parser
    // would also take "inf", "nan" and hex, which Java's does not.
    var sawDigit = false
    var i = body.startIndex
    while i < body.endIndex, body[i].isASCII, body[i].isNumber { sawDigit = true; i = body.index(after: i) }
    if i < body.endIndex, body[i] == "." {
        i = body.index(after: i)
        while i < body.endIndex, body[i].isASCII, body[i].isNumber { sawDigit = true; i = body.index(after: i) }
    }
    if sawDigit, i < body.endIndex, body[i] == "e" || body[i] == "E" {
        var j = body.index(after: i)
        if j < body.endIndex, body[j] == "+" || body[j] == "-" { j = body.index(after: j) }
        var expDigit = false
        while j < body.endIndex, body[j].isASCII, body[j].isNumber { expDigit = true; j = body.index(after: j) }
        if expDigit { i = j } else { sawDigit = false }
    }
    guard sawDigit, i == body.endIndex, let value = Double(String(body)) else {
        throw PanimError.numberFormat(text.isEmpty ? "empty String" : "For input string: \"\(text)\"")
    }
    return sign * value
}

/** Kotlin's `String.toInt()` (and `toInt(16)`): an optional sign and digits, within 32 bits, or it throws. */
public func kInt(_ text: String, radix: Int = 10) throws -> Int {
    var body = Substring(text)
    var negative = false
    if body.hasPrefix("-") { negative = true; body = body.dropFirst() } else if body.hasPrefix("+") { body = body.dropFirst() }
    guard !body.isEmpty, body.allSatisfy({ $0.isASCII && $0.isHexDigit }),
          let magnitude = Int(body, radix: radix) else {
        throw PanimError.numberFormat("For input string: \"\(text)\"" + (radix == 10 ? "" : " under radix \(radix)"))
    }
    let value = negative ? -magnitude : magnitude
    guard value >= Int(Int32.min) && value <= Int(Int32.max) else {
        throw PanimError.numberFormat("For input string: \"\(text)\"" + (radix == 10 ? "" : " under radix \(radix)"))
    }
    return value
}

// MARK: - Stable sorting

extension Array {
    /** Kotlin's `sortedBy`: stable, equal keys keep their order. */
    func stableSorted<K: Comparable>(by key: (Element) -> K) -> [Element] {
        let keyed = self.enumerated().map { (key($0.element), $0.offset, $0.element) }
        return keyed.sorted { a, b in a.0 < b.0 || (!(b.0 < a.0) && a.1 < b.1) }.map { $0.2 }
    }
}

/** Kotlin's `sortedBy` on Doubles compares with Double.compareTo: -0.0 below 0.0, NaN above everything. */
@inline(__always)
func kCompare(_ a: Double, _ b: Double) -> Int {
    if a < b { return -1 }
    if a > b { return 1 }
    let ab = a.isNaN ? Int64.max : (a == 0 ? (a.sign == .minus ? -1 : 0) : 0)
    let bb = b.isNaN ? Int64.max : (b == 0 ? (b.sign == .minus ? -1 : 0) : 0)
    return ab < bb ? -1 : (ab > bb ? 1 : 0)
}

extension Array {
    /** `sortedBy` with a Double key, ordered as the JVM orders boxed Doubles. */
    func stableSortedByDouble(_ key: (Element) -> Double) -> [Element] {
        let keyed = self.enumerated().map { (key($0.element), $0.offset, $0.element) }
        return keyed.sorted { a, b in
            let c = kCompare(a.0, b.0)
            return c < 0 || (c == 0 && a.1 < b.1)
        }.map { $0.2 }
    }
}

// MARK: - Insertion-ordered map

/**
 * Kotlin's LinkedHashMap: iterates in the order keys were first put; putting an existing key again keeps its
 * place. Order is part of the answer wherever the Kotlin core iterates one (it decides atlas offsets and draw
 * order), so a Swift Dictionary will not do.
 */
public struct OrderedMap<Value> {
    public private(set) var keys: [String] = []
    private var storage: [String: Value] = [:]

    public init() {}

    public var count: Int { keys.count }
    public var isEmpty: Bool { keys.isEmpty }

    public subscript(key: String) -> Value? {
        get { storage[key] }
        set {
            if let value = newValue {
                if storage.updateValue(value, forKey: key) == nil { keys.append(key) }
            } else {
                remove(key)
            }
        }
    }

    public func contains(_ key: String) -> Bool { storage[key] != nil }

    @discardableResult
    public mutating func remove(_ key: String) -> Value? {
        guard let old = storage.removeValue(forKey: key) else { return nil }
        if let at = keys.firstIndex(of: key) { keys.remove(at: at) }
        return old
    }

    public mutating func removeAll() {
        keys.removeAll()
        storage.removeAll()
    }

    /** Entries in insertion order. */
    public var entries: [(key: String, value: Value)] { keys.map { ($0, storage[$0]!) } }
    public var values: [Value] { keys.map { storage[$0]! } }

    func getValue(_ key: String) throws -> Value {
        guard let value = storage[key] else { throw PanimError.noSuchElement("Key \(key) is missing in the map.") }
        return value
    }
}

// MARK: - Java's String.format, for the parts the port uses

/**
 * `String.format(Locale.ROOT, ...)` for `%d`, `%s`, `%f` and `%%`, with flags `-` and `0`, a width and a
 * precision.
 *
 * `%f` is Java's, not C's, and they differ: Java takes the shortest decimal that reads back as the double (a Float
 * argument is widened first) and rounds *that* half up, where C rounds the exact binary value half to even. So
 * 0.125 is "0.13" in Java and "0.12" in C, and only Java's answer diffs clean against the Kotlin dumps. A negative
 * zero, or a negative value that rounds to zero, keeps its minus sign in both.
 */
public enum JavaFormat {
    public enum Arg {
        case int(Int64)
        case double(Double)
        case string(String)
    }

    /** `%.<precision>f` of [value]. */
    public static func fixed(_ value: Double, _ precision: Int) -> String {
        if value.isNaN { return "NaN" }
        if value.isInfinite { return value < 0 ? "-Infinity" : "Infinity" }
        let negative = value.sign == .minus
        let magnitude = Swift.abs(value)
        var body: String
        if magnitude == 0 {
            body = "0" + (precision > 0 ? "." + String(repeating: "0", count: precision) : "")
        } else {
            let (digits, exponent) = shortestDigits(magnitude)
            body = roundHalfUp(digits: digits, decimalExponent: exponent, precision: precision)
        }
        return negative ? "-" + body : body
    }

    public static func fixed(_ value: Float, _ precision: Int) -> String { fixed(Double(value), precision) }

    /**
     * The shortest digits that read back as [value] (positive, finite) and the exponent that places them:
     * value = 0.d1d2d3... x 10^exponent. Swift's description is the shortest round-trip form, as Java's is.
     */
    static func shortestDigits(_ value: Double) -> ([UInt8], Int) {
        let text = value.description // e.g. "0.001", "123.45", "1e-07", "1.5e+20"
        var mantissa = Substring(text)
        var exp10 = 0
        if let e = text.firstIndex(where: { $0 == "e" || $0 == "E" }) {
            mantissa = text[text.startIndex..<e]
            exp10 = Int(text[text.index(after: e)...].replacingOccurrences(of: "+", with: ""))!
        }
        var digits: [UInt8] = []
        var pointAt = -1
        for ch in mantissa.utf8 {
            if ch == UInt8(ascii: ".") { pointAt = digits.count } else { digits.append(ch - 48) }
        }
        if pointAt < 0 { pointAt = digits.count }
        // Strip leading zeros (moving the point) and trailing zeros.
        var lead = 0
        while lead < digits.count - 1 && digits[lead] == 0 { lead += 1 }
        digits.removeFirst(lead)
        pointAt -= lead
        while digits.count > 1 && digits.last == 0 { digits.removeLast() }
        return (digits, pointAt + exp10)
    }

    /** Java's FormattedFloatingDecimal.applyPrecision and fillDecimal: round half up at [precision] places. */
    static func roundHalfUp(digits input: [UInt8], decimalExponent: Int, precision: Int) -> String {
        var digits = input
        var exp = decimalExponent
        let keep = exp + precision // digits that survive
        if keep < 0 {
            digits = [0]
            exp = 1
        } else if keep < digits.count {
            if digits[keep] >= 5 {
                var i = keep - 1
                var carried = true
                while i >= 0 {
                    if digits[i] == 9 {
                        digits[i] = 0
                        i -= 1
                    } else {
                        digits[i] += 1
                        carried = false
                        break
                    }
                }
                digits.removeSubrange(keep...)
                if carried {
                    digits.insert(1, at: 0)
                    exp += 1
                }
            } else {
                digits.removeSubrange(keep...)
            }
            if digits.isEmpty { digits = [0]; exp = 1 }
        }
        // Lay out: integer part, then exactly `precision` fraction digits.
        var integer = ""
        var fraction = ""
        if exp > 0 {
            for i in 0..<exp { integer.append(i < digits.count ? Character(String(digits[i])) : "0") }
            for i in exp..<(exp + precision) { fraction.append(i < digits.count ? Character(String(digits[i])) : "0") }
        } else {
            integer = "0"
            for p in 0..<precision {
                let i = p + exp // position into digits
                fraction.append(i >= 0 && i < digits.count ? Character(String(digits[i])) : "0")
            }
        }
        while integer.count > 1 && integer.first == "0" { integer.removeFirst() }
        if integer.isEmpty { integer = "0" }
        return precision > 0 ? integer + "." + fraction : integer
    }

    /** The format string with its arguments, as `String.format(Locale.ROOT, ...)` would write it. */
    public static func format(_ pattern: String, _ args: Arg...) -> String { format(pattern, args) }

    public static func format(_ pattern: String, _ args: [Arg]) -> String {
        var out = ""
        var next = 0
        let chars = Array(pattern)
        var i = 0
        while i < chars.count {
            let c = chars[i]
            if c != "%" { out.append(c); i += 1; continue }
            i += 1
            var left = false
            var zero = false
            while i < chars.count, chars[i] == "-" || chars[i] == "0" {
                if chars[i] == "-" { left = true } else { zero = true }
                i += 1
            }
            var width = 0
            while i < chars.count, let d = chars[i].wholeNumberValue, chars[i].isASCII { width = width * 10 + d; i += 1 }
            var precision = -1
            if i < chars.count, chars[i] == "." {
                i += 1
                precision = 0
                while i < chars.count, let d = chars[i].wholeNumberValue, chars[i].isASCII { precision = precision * 10 + d; i += 1 }
            }
            let conversion = chars[i]
            i += 1
            var text: String
            switch conversion {
            case "%": text = "%"
            case "n": text = "\n"
            default:
                let arg = args[next]
                next += 1
                switch (conversion, arg) {
                case ("d", .int(let v)): text = String(v)
                case ("f", .double(let v)): text = fixed(v, precision < 0 ? 6 : precision)
                case ("f", .int(let v)): text = fixed(Double(v), precision < 0 ? 6 : precision)
                case ("s", .string(let v)): text = v
                case ("s", .int(let v)): text = String(v)
                case ("s", .double(let v)): text = String(v)
                case ("x", .int(let v)): text = String(UInt32(truncatingIfNeeded: v), radix: 16)
                default: text = "?"
                }
            }
            if text.count < width {
                let pad = width - text.count
                if left {
                    text += String(repeating: " ", count: pad)
                } else if zero {
                    let negative = text.hasPrefix("-")
                    let digits = negative ? String(text.dropFirst()) : text
                    text = (negative ? "-" : "") + String(repeating: "0", count: pad) + digits
                } else {
                    text = String(repeating: " ", count: pad) + text
                }
            }
            out += text
        }
        return out
    }
}

// MARK: - SHA-256

/**
 * SHA-256 (FIPS 180-4), for the manifest's digests. java.security has it on the JVM; PanimCore imports Foundation
 * only, and Foundation has none on Linux, so it is written out. Fed in pieces, so a file of any size is digested
 * through a stream, as Library.digestOf does.
 */
public struct SHA256 {
    private var h: [UInt32] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]
    private var buffer: [UInt8] = []
    private var length: UInt64 = 0

    private static let k: [UInt32] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ]

    public init() {}

    public mutating func update(_ bytes: UnsafeBufferPointer<UInt8>) {
        length &+= UInt64(bytes.count)
        var start = 0
        if !buffer.isEmpty {
            let take = Swift.min(64 - buffer.count, bytes.count)
            buffer.append(contentsOf: bytes[0..<take])
            start = take
            if buffer.count == 64 {
                buffer.withUnsafeBufferPointer { block($0, 0) }
                buffer.removeAll(keepingCapacity: true)
            }
        }
        while bytes.count - start >= 64 {
            block(bytes, start)
            start += 64
        }
        if start < bytes.count { buffer.append(contentsOf: bytes[start...]) }
    }

    public mutating func update(_ bytes: [UInt8]) {
        bytes.withUnsafeBufferPointer { update($0) }
    }

    public mutating func finish() -> [UInt8] {
        let bits = length &* 8
        var tail: [UInt8] = [0x80]
        let used = (buffer.count + 1) % 64
        tail.append(contentsOf: [UInt8](repeating: 0, count: used <= 56 ? 56 - used : 120 - used))
        for i in (0..<8).reversed() { tail.append(UInt8(truncatingIfNeeded: bits >> (UInt64(i) * 8))) }
        let saved = length
        update(tail)
        length = saved
        var out: [UInt8] = []
        for word in h { for i in (0..<4).reversed() { out.append(UInt8(truncatingIfNeeded: word >> (UInt32(i) * 8))) } }
        return out
    }

    private mutating func block(_ p: UnsafeBufferPointer<UInt8>, _ at: Int) {
        var w = [UInt32](repeating: 0, count: 64)
        for t in 0..<16 {
            let o = at + t * 4
            w[t] = UInt32(p[o]) << 24 | UInt32(p[o + 1]) << 16 | UInt32(p[o + 2]) << 8 | UInt32(p[o + 3])
        }
        for t in 16..<64 {
            let s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >> 3)
            let s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >> 10)
            w[t] = w[t - 16] &+ s0 &+ w[t - 7] &+ s1
        }
        var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7]
        for t in 0..<64 {
            let s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
            let ch = (e & f) ^ (~e & g)
            let t1 = hh &+ s1 &+ ch &+ SHA256.k[t] &+ w[t]
            let s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
            let maj = (a & b) ^ (a & c) ^ (b & c)
            let t2 = s0 &+ maj
            hh = g; g = f; f = e; e = d &+ t1; d = c; c = b; b = a; a = t1 &+ t2
        }
        h[0] &+= a; h[1] &+= b; h[2] &+= c; h[3] &+= d; h[4] &+= e; h[5] &+= f; h[6] &+= g; h[7] &+= hh
    }

    @inline(__always)
    private func rotr(_ x: UInt32, _ n: UInt32) -> UInt32 { (x >> n) | (x << (32 - n)) }
}
