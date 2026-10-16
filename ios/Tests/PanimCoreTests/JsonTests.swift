import XCTest
@testable import PanimCore

/** The manifest reader: what a library.json needs, read as the Kotlin reader reads it. */
final class JsonTests: XCTestCase {
    func testObjectKeepsFieldOrderAndTypes() throws {
        let json = try Json.parse("""
            { "version": 1, "name": "Lecture", "flag": true, "none": null,
              "list": [1, 2.5, -3e2, "x"], "nested": {"b": 2, "a": 1, "b2": {"deep": [ ]}} }
            """)
        XCTAssertEqual(json["version"]?.asInt, 1)
        XCTAssertEqual(json["name"]?.asString, "Lecture")
        XCTAssertEqual(json["flag"]?.asBool, true)
        if case .null = json["none"]! {} else { XCTFail("null expected") }
        XCTAssertEqual(json["list"]?.asList.count, 4)
        XCTAssertEqual(json["list"]?[1]?.asLong, 2)
        XCTAssertEqual(json["list"]?[2]?.asInt, -300)
        XCTAssertNil(json["list"]?[9])
        XCTAssertEqual(json["nested"]?.fields?.keys, ["b", "a", "b2"])
        XCTAssertEqual(json["nested"]?["b2"]?["deep"]?.asList.count, 0)
        XCTAssertEqual(json.fields?.keys, ["version", "name", "flag", "none", "list", "nested"])
        // Wrong types answer nil, as Kotlin's `as?` does.
        XCTAssertNil(json["name"]?.asInt)
        XCTAssertNil(json["version"]?.asString)
        XCTAssertEqual(json["name"]?.asList.count, 0)
    }

    func testEscapes() throws {
        let json = try Json.parse(#"["a\"b\\c\/d\n\t", "é€", "😀", "plain é"]"#)
        XCTAssertEqual(json[0]?.asString, "a\"b\\c/d\n\t")
        XCTAssertEqual(json[1]?.asString, "é€")
        XCTAssertEqual(json[2]?.asString, "😀") // a surrogate pair, two \u escapes
        XCTAssertEqual(json[3]?.asString, "plain é")
    }

    func testNumbersConvertAsKotlinDoes() throws {
        let json = try Json.parse("[2.9, -2.9, 1e12, 3000000000]")
        XCTAssertEqual(json[0]?.asInt, 2)              // towards zero
        XCTAssertEqual(json[1]?.asInt, -2)
        XCTAssertEqual(json[2]?.asInt, 2147483647)     // saturates at Int's 32 bits
        XCTAssertEqual(json[3]?.asLong, 3000000000)
    }

    func testErrorsCarryTheKotlinMessages() {
        XCTAssertThrowsError(try Json.parse("{} x")) { error in
            XCTAssertEqual(error as? PanimError, .illegalArgument("trailing input at 3"))
        }
        XCTAssertThrowsError(try Json.parse("[1, 2")) { error in
            XCTAssertEqual(error as? PanimError, .illegalState("expected ',' or ']' at 5"))
        }
        XCTAssertThrowsError(try Json.parse("{\"a\" 1}")) { error in
            XCTAssertEqual(error as? PanimError, .illegalArgument("expected ':' at 5"))
        }
        XCTAssertThrowsError(try Json.parse("")) { error in
            XCTAssertEqual(error as? PanimError, .illegalState("unexpected end of JSON"))
        }
        XCTAssertThrowsError(try Json.parse("nul")) { error in
            XCTAssertEqual(error as? PanimError, .illegalArgument("bad literal at 0"))
        }
    }

    func testLibraryManifest() throws {
        let storage = MemoryStorage([
            "library.json": Array("""
                {"version": 1, "glyph_atlas": {"path": "library.atlas", "bytes": 3, "sha256_16": "ba7816bf8f01cfea"},
                 "assets": [{"path": "assets/a.panm", "bytes": 2, "sha256_16": "0000000000000000"}],
                 "asset_pack": {"path": "assets.pack", "index": {"a": [0, 2]}},
                 "scenes": [{"name": "S", "tier": 1, "program": "scenes/S.panim", "assets": ["assets/a.panm"],
                             "needs_glyph_atlas": true, "frames": 10, "playable_bytes": 99,
                             "chapters": [{"number": 2, "title": "Two", "frame": 8}, {"number": 1, "frame": 0},
                                          {"title": "no number", "frame": 4}]}]}
                """.utf8),
            "library.atlas": Array("abc".utf8),
            "assets/a.panm": [1, 2],
        ])
        let library = try Library.load(storage)
        XCTAssertEqual(library.scenes.count, 1)
        let scene = library.scenes[0]
        XCTAssertEqual(scene.chapters.map { $0.number }, [1, 2]) // sorted by frame, the incomplete one dropped
        XCTAssertEqual(scene.chapters.map { $0.title }, ["", "Two"])
        XCTAssertEqual(library.pack?.index["a"]?.0, 0)
        XCTAssertEqual(library.pack?.index["a"]?.1, 2)
        XCTAssertEqual(library.missing(), ["scenes/S.panim"])
        XCTAssertFalse(library.isPlayable(scene))
        // "abc" hashes to ba7816bf8f01cfea...; the asset's digest is wrong on purpose.
        let problems = try library.checkIntegrity(verifyDigests: true)
        XCTAssertEqual(problems.map { $0.description },
                       ["assets/a.panm: digest \(Library.digestOf([1, 2])), expected 0000000000000000"])
        XCTAssertEqual(Library.digestOf(Array("abc".utf8)), "ba7816bf8f01cfea")
        XCTAssertEqual(Library.digestOf([]), "e3b0c44298fc1c14")
        XCTAssertEqual(Library.digestOf([UInt8](repeating: 0x61, count: 1_000_000)), "cdc76e5c9914fb92")
    }
}

/** Storage in memory, for tests. */
final class MemoryStorage: Storage {
    var files: [String: [UInt8]]

    init(_ files: [String: [UInt8]]) { self.files = files }

    func exists(_ path: String) -> Bool { files[path] != nil }
    func read(_ path: String) throws -> [UInt8] {
        guard let bytes = files[path] else { throw PanimError.io("\(path) (No such file or directory)") }
        return bytes
    }
    func sizeOf(_ path: String) -> Int64 { Int64(files[path]?.count ?? 0) }
}
