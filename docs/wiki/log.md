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
