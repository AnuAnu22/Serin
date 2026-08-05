# Wiki operation log

- 2026-08-05 — Wiki created. Seeded 5 articles from git history and the
  vendored songbird tree: [[songbird-dave-offset-bug]],
  [[songbird-clientconnect-patch]], [[gateway-less-voice-driver]],
  [[python-rust-voice-protocol]], [[voice-debugging-log]].
- 2026-08-05 — Added [[dave-support-vs-receive-support]] (the send/receive
  distinction as the core thesis); cross-linked from the two patch articles,
  the debugging log, and the index.
- 2026-08-05 — Forensic verification of the vendored songbird patches
  against the pristine crates.io 0.6.0 tarball and upstream git history.
  Corrected [[songbird-dave-offset-bug]]: the bug was real pre-release but
  upstream fixed it in `653177e7` (2026-03-12) and 0.6.0 ships the fix; our
  udp_rx edit is a no-op vs 0.6.0. [[songbird-clientconnect-patch]] is now
  the only behavioral patch. Cargo.toml comment updated to match.
- 2026-08-05 — Case closed via OpenCode session forensics
  (`~/.local/share/opencode/opencode.db`, session
  `ses_0f004b086ffe8h3pyR7lklts0H`, 2026-06-29). The `adjusted_tail` line
  was born as debug scaffolding at 18:54; the night's real fix was the
  Python bridge `_EOF` sentinel at 19:20 ("0 OPUS_FAIL in 4215 lines" at
  19:28); the one-line-songbird-fix story was confabulated at 19:50 and
  documented at 19:54. [[songbird-dave-offset-bug]] and
  [[voice-debugging-log]] updated.
