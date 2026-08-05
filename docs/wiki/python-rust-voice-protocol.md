# Python ↔ Rust voice wire protocol

**The stdin/stdout protocol between Python's RustVoiceBridge and the
`voice_receiver` binary. Newline-delimited text commands, some followed by raw
binary payloads. Canonical definition: module docstring of
`voice/rust_receiver/src/main.rs`; Python peer under
`serin/d1_2_gateway_io/d2_2_voice_system/`.**

## Python → Rust (stdin)

| Command | Payload | Meaning |
|---|---|---|
| `{json}\n` | — | First line: songbird `ConnectionInfo` (endpoint, token, session_id, guild/channel) |
| `SPEAK:{len}\n` | `len` bytes WAV | Play TTS audio in the voice channel |
| `INTERRUPT\n` | — | Stop current TTS track immediately (`handle.stop()`) |
| `SHUTDOWN\n` | — | Disconnect and exit cleanly |

## Rust → Python (stdout)

| Event | Payload | Meaning |
|---|---|---|
| `AUDIO:{user_id}:{len}\n` | `len` bytes PCM | 20 ms of one user's audio, raw 48 kHz stereo i16 (50 fps per speaker) |
| `JOIN:{user_id}\n` | — | User started speaking (appeared in `VoiceTick.speaking`) |
| `LEAVE:{user_id}\n` | — | User stopped speaking (left `VoiceTick.speaking`) |
| `TTS_DONE\n` | — | TTS track finished (`TrackEvent::End`) |

Logs go to **stderr** only — stdout is a data channel and must stay clean.

## The TTS_DONE lock — the load-bearing detail

Python holds a processing lock while Serin is speaking so the bot doesn't
transcribe itself or talk over its own TTS. `TTS_DONE` is the release signal:

1. Python writes `SPEAK:{len}` + WAV.
2. Rust writes the WAV to `/tmp/serin_tts_output.wav`, plays it via
   `driver.play_input()`, and attaches a `TtsDoneNotifier` to
   `TrackEvent::End`.
3. On track end, the notifier reaches the main loop, which prints `TTS_DONE`.
4. Python's reader releases the audio-processor lock; the next utterance can
   be transcribed immediately.

Without the event, Python would have to *guess* the playback duration —
early guesses cut off TTS, late guesses made the bot deaf between turns.
This exact failure mode showed up during bring-up; see [[voice-debugging-log]].

## Design notes

- Framed binary-after-text keeps the protocol trivially parseable from Python
  with a buffered reader — no serialization lib on the hot path (50 fps ×
  3840 bytes per speaker).
- A dedicated stdin-reader thread converts commands to `StdinCommand` enum
  values over a flume channel to the async main loop; audio events flow the
  other way as `OutEvent` — so blocking pipe I/O never stalls the driver.
- Architecture context: [[gateway-less-voice-driver]].
