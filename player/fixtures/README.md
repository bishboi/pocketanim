# Fixtures

`streamed-lecture/` is a packed phone library (tools/build_library) of a short two-chapter lecture with a narration
track: what `tools.mock_saved_lectures` serves as two saved lectures of one series, so the player's Saved list,
streaming, chapters and "Up next" are checked on an emulator (`player/ui-test.sh`, the `player-ui` workflow) and
off-device (`Verify http://127.0.0.1:8787 stream test <dir>`). Its narration is a test tone, not a voice.
