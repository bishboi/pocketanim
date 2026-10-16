// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/Expr.kt.
import Foundation

/**
 * The surface-function evaluator.
 *
 * A `surface` declaration carries its height as an expression in u and v --
 * that is what makes a tessellated surface a few dozen bytes instead of a baked
 * mesh. The device therefore has to evaluate it, and the exporter's Python
 * `eval` is not an option here.
 *
 * Deliberately a closed grammar rather than a general one: numbers, u, v, the
 * four operators, parentheses, unary minus, and a fixed function table. There
 * is no variable lookup, no indexing and no call into anything the program did
 * not name, so a malformed or hostile program is a parse error rather than a
 * capability. Expressions are compiled once into a tree and evaluated per
 * vertex, because a 24x24 surface evaluates this 2,500 times per frame.
 */
public final class Expr {
    private let root: Node

    private init(_ root: Node) { self.root = root }

    /** Evaluate at (u, v). An unknown function throws here, as Kotlin's does: the name is only checked when called. */
    public func eval(_ u: Double, _ v: Double) throws -> Double { try root.eval(u, v) }

    private indirect enum Node {
        case const(Double)
        case variable(isU: Bool)
        case binary(op: UInt16, left: Node, right: Node)
        case negate(Node)
        case call(name: String, arg: Node)

        func eval(_ u: Double, _ v: Double) throws -> Double {
            switch self {
            case .const(let value):
                return value
            case .variable(let isU):
                return isU ? u : v
            case .binary(let op, let left, let right):
                let a = try left.eval(u, v)
                let b = try right.eval(u, v)
                switch op {
                case 0x2B: return a + b
                case 0x2D: return a - b
                case 0x2A: return a * b
                default: return a / b
                }
            case .negate(let inner):
                return -(try inner.eval(u, v))
            case .call(let name, let arg):
                let x = try arg.eval(u, v)
                switch name {
                case "sin": return sin(x)
                case "cos": return cos(x)
                case "tan": return tan(x)
                case "exp": return exp(x)
                case "sqrt": return x.squareRoot()
                case "abs": return Swift.abs(x)
                case "log": return log(x)
                default: throw PanimError.illegalArgument("unknown function \(name)")
                }
            }
        }
    }

    public static func parse(_ text: String) throws -> Expr {
        let parser = Parser(text.replacingOccurrences(of: " ", with: ""))
        return Expr(try parser.parseAll())
    }

    private final class Parser {
        private let text: String
        private let src: [UInt16]
        private var at = 0

        init(_ text: String) {
            self.text = text
            self.src = Array(text.utf16)
        }

        func parseAll() throws -> Node {
            let node = try parseSum()
            try require(at == src.count, "trailing input in expression at \(at): \(text)")
            return node
        }

        private func peek() -> UInt16? { at < src.count ? src[at] : nil }

        private func isDigit(_ c: UInt16) -> Bool {
            if c >= 0x30 && c <= 0x39 { return true }
            if c < 0x80 { return false }
            return Unicode.Scalar(c).map { $0.properties.numericType == .decimal } ?? false
        }

        private func isLetter(_ c: UInt16) -> Bool {
            if (c >= 0x41 && c <= 0x5A) || (c >= 0x61 && c <= 0x7A) { return true }
            if c < 0x80 { return false }
            return Unicode.Scalar(c).map { $0.properties.isAlphabetic } ?? false
        }

        private func substring(_ from: Int, _ to: Int) -> String { String(decoding: src[from..<to], as: UTF16.self) }

        private func parseSum() throws -> Node {
            var left = try parseProduct()
            while true {
                let c = peek()
                if c == 0x2B || c == 0x2D {
                    at += 1
                    left = .binary(op: c!, left: left, right: try parseProduct())
                } else {
                    return left
                }
            }
        }

        private func parseProduct() throws -> Node {
            var left = try parseUnary()
            while true {
                let c = peek()
                if c == 0x2A || c == 0x2F {
                    at += 1
                    left = .binary(op: c!, left: left, right: try parseUnary())
                } else {
                    return left
                }
            }
        }

        private func parseUnary() throws -> Node {
            if peek() == 0x2D {
                at += 1
                return .negate(try parseUnary())
            }
            if peek() == 0x2B { at += 1 }
            return try parseAtom()
        }

        private func parseAtom() throws -> Node {
            guard let c = peek() else { throw PanimError.illegalArgument("expression ended early: \(text)") }

            if c == 0x28 { // (
                at += 1
                let inner = try parseSum()
                try require(peek() == 0x29, "unbalanced parentheses in \(text)")
                at += 1
                return inner
            }

            if isDigit(c) || c == 0x2E {
                let start = at
                while at < src.count && (isDigit(src[at]) || src[at] == 0x2E ||
                        src[at] == 0x65 || src[at] == 0x45 ||
                        ((src[at] == 0x2D || src[at] == 0x2B) && (src[at - 1] == 0x65 || src[at - 1] == 0x45))) {
                    at += 1
                }
                return .const(try kDouble(substring(start, at)))
            }

            if isLetter(c) || c == 0x5F {
                let start = at
                while at < src.count && (isLetter(src[at]) || isDigit(src[at]) || src[at] == 0x5F) { at += 1 }
                let name = substring(start, at)
                if peek() == 0x28 {
                    at += 1
                    let arg = try parseSum()
                    try require(peek() == 0x29, "unbalanced parentheses in \(text)")
                    at += 1
                    return .call(name: name, arg: arg)
                }
                switch name {
                case "u": return .variable(isU: true)
                case "v": return .variable(isU: false)
                case "pi": return .const(Double.pi)
                default: throw PanimError.illegalArgument("unknown name '\(name)' in \(text)")
                }
            }

            throw PanimError.illegalArgument("unexpected '\(substring(at, at + 1))' in \(text)")
        }
    }
}
