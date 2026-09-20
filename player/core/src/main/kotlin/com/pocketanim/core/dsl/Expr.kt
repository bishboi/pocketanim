package com.pocketanim.core.dsl

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.tan

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
class Expr private constructor(private val root: Node) {

    fun eval(u: Double, v: Double): Double = root.eval(u, v)

    private sealed class Node {
        abstract fun eval(u: Double, v: Double): Double
    }

    private class Const(val value: Double) : Node() {
        override fun eval(u: Double, v: Double) = value
    }

    private class Var(val isU: Boolean) : Node() {
        override fun eval(u: Double, v: Double) = if (isU) u else v
    }

    private class Binary(val op: Char, val left: Node, val right: Node) : Node() {
        override fun eval(u: Double, v: Double): Double {
            val a = left.eval(u, v)
            val b = right.eval(u, v)
            return when (op) {
                '+' -> a + b
                '-' -> a - b
                '*' -> a * b
                else -> a / b
            }
        }
    }

    private class Negate(val inner: Node) : Node() {
        override fun eval(u: Double, v: Double) = -inner.eval(u, v)
    }

    private class Call(val name: String, val arg: Node) : Node() {
        override fun eval(u: Double, v: Double): Double {
            val x = arg.eval(u, v)
            return when (name) {
                "sin" -> sin(x)
                "cos" -> cos(x)
                "tan" -> tan(x)
                "exp" -> exp(x)
                "sqrt" -> sqrt(x)
                "abs" -> abs(x)
                "log" -> ln(x)
                else -> throw IllegalArgumentException("unknown function $name")
            }
        }
    }

    companion object {
        fun parse(text: String): Expr = Expr(Parser(text.replace(" ", "")).parseAll())
    }

    private class Parser(private val src: String) {
        private var at = 0

        fun parseAll(): Node {
            val node = parseSum()
            require(at == src.length) { "trailing input in expression at $at: $src" }
            return node
        }

        private fun peek(): Char? = src.getOrNull(at)

        private fun parseSum(): Node {
            var left = parseProduct()
            while (true) {
                val c = peek()
                if (c == '+' || c == '-') {
                    at++
                    left = Binary(c, left, parseProduct())
                } else return left
            }
        }

        private fun parseProduct(): Node {
            var left = parseUnary()
            while (true) {
                val c = peek()
                if (c == '*' || c == '/') {
                    at++
                    left = Binary(c, left, parseUnary())
                } else return left
            }
        }

        private fun parseUnary(): Node {
            if (peek() == '-') {
                at++
                return Negate(parseUnary())
            }
            if (peek() == '+') at++
            return parseAtom()
        }

        private fun parseAtom(): Node {
            val c = peek() ?: throw IllegalArgumentException("expression ended early: $src")

            if (c == '(') {
                at++
                val inner = parseSum()
                require(peek() == ')') { "unbalanced parentheses in $src" }
                at++
                return inner
            }

            if (c.isDigit() || c == '.') {
                val start = at
                while (at < src.length && (src[at].isDigit() || src[at] == '.' ||
                        src[at] == 'e' || src[at] == 'E' ||
                        ((src[at] == '-' || src[at] == '+') && (src[at - 1] == 'e' || src[at - 1] == 'E')))
                ) at++
                return Const(src.substring(start, at).toDouble())
            }

            if (c.isLetter() || c == '_') {
                val start = at
                while (at < src.length && (src[at].isLetterOrDigit() || src[at] == '_')) at++
                val name = src.substring(start, at)
                if (peek() == '(') {
                    at++
                    val arg = parseSum()
                    require(peek() == ')') { "unbalanced parentheses in $src" }
                    at++
                    return Call(name, arg)
                }
                return when (name) {
                    "u" -> Var(true)
                    "v" -> Var(false)
                    "pi" -> Const(Math.PI)
                    else -> throw IllegalArgumentException("unknown name '$name' in $src")
                }
            }

            throw IllegalArgumentException("unexpected '$c' in $src")
        }
    }
}
