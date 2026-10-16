// Ported from player/core/src/main/kotlin/com/pocketanim/core/Json.kt.
import Foundation

/**
 * A minimal JSON reader.
 *
 * `core` stays free of Android so the renderer can be run and checked off
 * device, which rules out `org.json`; and a library manifest is not worth a
 * third-party dependency on a module this small. So: enough JSON to read a
 * generated manifest, and no more.
 *
 * Reading only. Nothing here writes JSON, because nothing on the device
 * produces a manifest -- the exporter does.
 *
 * (Swift has JSONSerialization, but its numbers, its key order and its errors are not the Kotlin reader's, and
 * the two players must read a manifest alike.)
 */
public indirect enum Json {
    case null
    case bool(Bool)
    case num(Double)
    case text(String)
    case arr([Json])
    /** Fields in the order the text gave them, as Kotlin's LinkedHashMap keeps them. */
    case obj(OrderedMap<Json>)

    public subscript(key: String) -> Json? {
        if case .obj(let fields) = self { return fields[key] }
        return nil
    }

    public subscript(index: Int) -> Json? {
        if case .arr(let items) = self, index >= 0, index < items.count { return items[index] }
        return nil
    }

    public var asString: String? {
        if case .text(let value) = self { return value }
        return nil
    }

    public var asInt: Int? {
        if case .num(let value) = self { return kToInt(value) }
        return nil
    }

    public var asLong: Int64? {
        if case .num(let value) = self { return kToLong(value) }
        return nil
    }

    public var asBool: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    public var asList: [Json] {
        if case .arr(let items) = self { return items }
        return []
    }

    /** The fields of an object, or nil for anything else. */
    public var fields: OrderedMap<Json>? {
        if case .obj(let fields) = self { return fields }
        return nil
    }

    public static func parse(_ text: String) throws -> Json {
        let reader = Reader(text)
        let value = try reader.value()
        reader.skipSpace()
        try require(reader.done, "trailing input at \(reader.at)")
        return value
    }

    /** Reads UTF-16 code units, as the Kotlin reader reads chars, so positions in messages agree. */
    private final class Reader {
        private let src: [UInt16]
        var at = 0
        var done: Bool { at >= src.count }

        init(_ text: String) { src = Array(text.utf16) }

        private func char(_ i: Int) -> UInt16? { i >= 0 && i < src.count ? src[i] : nil }

        private func isDigit(_ c: UInt16) -> Bool { c >= 0x30 && c <= 0x39 }

        func skipSpace() {
            while at < src.count && kIsWhitespace(src[at]) { at += 1 }
        }

        func value() throws -> Json {
            skipSpace()
            guard let c = char(at) else { throw PanimError.illegalState("unexpected end of JSON") }
            switch c {
            case 0x7B: return try obj() // {
            case 0x5B: return try arr() // [
            case 0x22: return .text(try string()) // "
            case 0x74: return try literal("true", .bool(true))
            case 0x66: return try literal("false", .bool(false))
            case 0x6E: return try literal("null", .null)
            default:
                if c == 0x2D || isDigit(c) { return try number() }
                throw PanimError.illegalState("unexpected '\(String(decoding: [c], as: UTF16.self))' at \(at)")
            }
        }

        private func literal(_ word: String, _ result: Json) throws -> Json {
            let units = Array(word.utf16)
            let matches = at + units.count <= src.count && Array(src[at..<(at + units.count)]) == units
            try require(matches, "bad literal at \(at)")
            at += units.count
            return result
        }

        private func obj() throws -> Json {
            at += 1 // {
            var fields = OrderedMap<Json>()
            skipSpace()
            if char(at) == 0x7D {
                at += 1
                return .obj(fields)
            }
            while true {
                skipSpace()
                let key = try string()
                skipSpace()
                try require(char(at) == 0x3A, "expected ':' at \(at)")
                at += 1
                fields[key] = try value()
                skipSpace()
                switch char(at) {
                case 0x2C: at += 1
                case 0x7D:
                    at += 1
                    return .obj(fields)
                default: throw PanimError.illegalState("expected ',' or '}' at \(at)")
                }
            }
        }

        private func arr() throws -> Json {
            at += 1 // [
            var items: [Json] = []
            skipSpace()
            if char(at) == 0x5D {
                at += 1
                return .arr(items)
            }
            while true {
                items.append(try value())
                skipSpace()
                switch char(at) {
                case 0x2C: at += 1
                case 0x5D:
                    at += 1
                    return .arr(items)
                default: throw PanimError.illegalState("expected ',' or ']' at \(at)")
                }
            }
        }

        private func string() throws -> String {
            try require(char(at) == 0x22, "expected string at \(at)")
            at += 1
            var out: [UInt16] = []
            while true {
                guard let c = char(at) else { throw PanimError.illegalState("unterminated string") }
                switch c {
                case 0x22:
                    at += 1
                    return String(decoding: out, as: UTF16.self)
                case 0x5C:
                    at += 1
                    guard let e = char(at) else { throw PanimError.illegalState("unterminated escape") }
                    switch e {
                    case 0x22, 0x5C, 0x2F: out.append(e)
                    case 0x62: out.append(0x08)
                    case 0x66: out.append(0x0C)
                    case 0x6E: out.append(0x0A)
                    case 0x72: out.append(0x0D)
                    case 0x74: out.append(0x09)
                    case 0x75:
                        guard at + 5 <= src.count,
                              let unit = UInt16(String(decoding: src[(at + 1)..<(at + 5)], as: UTF16.self), radix: 16)
                        else {
                            throw PanimError.numberFormat("bad \\u escape at \(at)")
                        }
                        out.append(unit)
                        at += 4
                    default:
                        throw PanimError.illegalState("bad escape '\\\(String(decoding: [e], as: UTF16.self))' at \(at)")
                    }
                    at += 1
                default:
                    out.append(c)
                    at += 1
                }
            }
        }

        private func number() throws -> Json {
            let start = at
            if src[at] == 0x2D { at += 1 }
            while at < src.count && (isDigit(src[at]) || src[at] == 0x2E || src[at] == 0x65 || src[at] == 0x45 ||
                                     src[at] == 0x2B || src[at] == 0x2D) { at += 1 }
            return .num(try kDouble(String(decoding: src[start..<at], as: UTF16.self)))
        }
    }
}
