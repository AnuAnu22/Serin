# Voice pipeline bring-up — debugging log (July 2026)

**Root causes and dead ends from getting Discord voice receive working
end-to-end. Mined from git history; each entry lists the commit for the full
diff. The two big ones have their own articles:
[[songbird-dave-offset-bug]] (~4 days) and [[songbird-clientconnect-patch]].**

## Rust / receiver side

- **Every Opus decode failing under DAVE** → upstream uses `rtp_body_tail`
  where it computed `adjusted_tail`. One line. See
  [[songbird-dave-offset-bug]].
- **Audio not attributable to users / dropped before decrypt** → upstream
  ignores `ClientConnect` as "discontinued"; Discord still sends it. Vendored
  patch `313a220`. See [[songbird-clientconnect-patch]].
- **Receiver binary not found** (`00b717b`) — off-by-one in the `pardir` count
  when building the binary path from the Python module location. Symptom:
  bridge spawns nothing; looks like a Rust failure, is a Python path bug.
- **TTS overlap / bot deaf after speaking** — solved by the `TTS_DONE`
  track-end event instead of guessing playback duration (`1d04f04`). See
  [[python-rust-voice-protocol]].

## Python / integration side

- **`process_voice_input` wiring saga** (`4c38826` → `14cf6ea` → `2afaa34` →
  `a19c210`): binding a method onto the message manager after construction,
  then a `hasattr` guard evaluating falsely, then a defensive guard
  suppressing calls entirely. Lesson: **dynamic method injection defeats every
  static guarantee** — each fix moved the silent failure one layer down.
  Eventually also `8c7e43f` (handle the attribute genuinely missing).
- **`dir()` bug + lock bypass + ffmpeg flag** (`82cd116`) — several stacked
  issues in one commit; includes third-person prompt + context injection for
  voice.
- **LLM voice-decider output unparseable** (`27dc043`) — local model emitted
  JSON missing commas between key-value pairs; first patched the parser, then
  properly fixed by forcing `response_format` structured output (`5663fb7`).
  Lesson: constrain generation instead of parsing garbage.
- **Stale bridge API after the d-rename migration** (`f7f424e`) — callers kept
  old `RustVoiceBridge` method names; nothing failed until runtime.
- **Test file committed as null bytes** (`f4edc5c`) — CR/line-ending
  corruption turned `test_voice_action.py` into NULs on commit. If a Python
  file suddenly "has no tests", check for binary content.
- **Voice imports blocking startup** (`72bdfc4`) + **5 duplicate voice files**
  (`269d076`) — pre-migration duplicate modules (`rust_voice_bridge.py` vs
  `bridge.py`, etc.) meant fixes landed in the copy that wasn't imported.
- **Display names** (`531a86e`) — resolve Discord display names for voice
  users rather than raw IDs before prompting the LLM.
- **Shutdown** (`9da2f86`) — disconnect voice channels *immediately* on
  shutdown; lingering voice sessions broke the next connect.

## Meta-lessons

1. The expensive bugs were all **in other people's correct-looking code**
   (vendored songbird) or **between layers** (Python↔Rust spawn paths,
   post-rename call sites) — not in the feature logic itself.
2. Silent drops are the enemy: DAVE decrypt drops unmapped SSRCs, guards
   swallowed `process_voice_input`, duplicate modules swallowed fixes. Prefer
   loud errors during bring-up.
3. Wire reality beats documentation — twice ([[songbird-clientconnect-patch]],
   [[songbird-dave-offset-bug]]).
4. A feature matrix saying "supported" means the code exists, not that anyone
   runs it — [[dave-support-vs-receive-support]].
