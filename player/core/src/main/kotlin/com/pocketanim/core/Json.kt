package com.pocketanim.core

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
 */
sealed class Json {
    object Null : Json()
    class Bool(val value: Boolean) : Json()
    class Num(val value: Double) : Json()
    class Text(val value: String) : Json()
    class Arr(val items: List<Json>) : Json()
    class Obj(val fields: Map<String, Json>) : Json()

    operator fun get(key: String): Json? = (this as? Obj)?.fields?.get(key)
    operator fun get(index: Int): Json? = (this as? Arr)?.items?.getOrNull(index)

    val asString: String? get() = (this as? Text)?.value
    val asInt: Int? get() = (this as? Num)?.value?.toInt()
    val asLong: Long? get() = (this as? Num)?.value?.toLong()
    val asBool: Boolean? get() = (this as? Bool)?.value
    val asList: List<Json> get() = (this as? Arr)?.items ?: emptyList()

    companion object {
        fun parse(text: String): Json = Reader(text).let {
            val value = it.value()
            it.skipSpace()
            require(it.done) { "trailing input at ${it.at}" }
            value
        }
    }

    private class Reader(private val src: String) {
        var at = 0
        val done: Boolean get() = at >= src.length

        fun skipSpace() {
            while (at < src.length && src[at].isWhitespace()) at++
        }

        fun value(): Json {
            skipSpace()
            return when (val c = src.getOrNull(at) ?: error("unexpected end of JSON")) {
                '{' -> obj()
                '[' -> arr()
                '"' -> Text(string())
                't' -> literal("true", Bool(true))
                'f' -> literal("false", Bool(false))
                'n' -> literal("null", Null)
                else -> if (c == '-' || c.isDigit()) number() else error("unexpected '$c' at $at")
            }
        }

        private fun literal(word: String, result: Json): Json {
            require(src.startsWith(word, at)) { "bad literal at $at" }
            at += word.length
            return result
        }

        private fun obj(): Json {
            at++ // {
            val fields = LinkedHashMap<String, Json>()
            skipSpace()
            if (src.getOrNull(at) == '}') {
                at++
                return Obj(fields)
            }
            while (true) {
                skipSpace()
                val key = string()
                skipSpace()
                require(src.getOrNull(at) == ':') { "expected ':' at $at" }
                at++
                fields[key] = value()
                skipSpace()
                when (src.getOrNull(at)) {
                    ',' -> at++
                    '}' -> { at++; return Obj(fields) }
                    else -> error("expected ',' or '}' at $at")
                }
            }
        }

        private fun arr(): Json {
            at++ // [
            val items = ArrayList<Json>()
            skipSpace()
            if (src.getOrNull(at) == ']') {
                at++
                return Arr(items)
            }
            while (true) {
                items.add(value())
                skipSpace()
                when (src.getOrNull(at)) {
                    ',' -> at++
                    ']' -> { at++; return Arr(items) }
                    else -> error("expected ',' or ']' at $at")
                }
            }
        }

        private fun string(): String {
            require(src.getOrNull(at) == '"') { "expected string at $at" }
            at++
            val out = StringBuilder()
            while (true) {
                when (val c = src.getOrNull(at) ?: error("unterminated string")) {
                    '"' -> { at++; return out.toString() }
                    '\\' -> {
                        at++
                        when (val e = src.getOrNull(at) ?: error("unterminated escape")) {
                            '"', '\\', '/' -> out.append(e)
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                out.append(src.substring(at + 1, at + 5).toInt(16).toChar())
                                at += 4
                            }
                            else -> error("bad escape '\\$e' at $at")
                        }
                        at++
                    }
                    else -> { out.append(c); at++ }
                }
            }
        }

        private fun number(): Json {
            val start = at
            if (src[at] == '-') at++
            while (at < src.length && (src[at].isDigit() || src[at] in ".eE+-")) at++
            return Num(src.substring(start, at).toDouble())
        }
    }
}
