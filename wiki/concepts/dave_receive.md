---
type: concept
tags: [voice, dave, songbird, rust]
created: 2026-08-16
updated: 2026-08-25
sources: [docs/wiki/dave-support-vs-receive-support.md, docs/wiki/songbird-dave-offset-bug.md, docs/wiki/songbird-clientconnect-patch.md, docs/wiki/gateway-less-voice-driver.md, docs/wiki/voice-debugging-log.md]
status: seed
---

# DAVE & the Voice-Receive Saga

## What it is

The hard-won story of making Serin *receive* DAVE-encrypted Discord voice. DAVE (end-to-end
voice encryption, enforced by Discord 2026-03-01) broke receive for everyone; the debugging
cost Serin ~4+ days and produced the wiki's most valuable articles.

## The core thesis ([[dave-support-vs-receive-support]])

Every library "supported DAVE" — for **send** (existential for music bots). The **receive** path
was the ecosystem's unmaintained attic: discord.py (receive only via an unmerged PR),
songbird (receive existed but was never run end-to-end under DAVE), discord.js (the one mature
exception, at the cost of Node on a 50fps audio path). Serin is plausibly among the first to push
real DAVE-encrypted inbound audio through songbird's receive path.

## The two real bugs

1. **The "one-line songbird fix" is a myth** ([[songbird-dave-offset-bug]]): upstream fixed the
   DAVE offset bug in `653177e7` (2026-03-12), shipped in 0.6.0. Serin's vendored
   `udp_rx/mod.rs` edit is a **no-op** vs the pristine 0.6.0 tarball (proven by forensic diff +
   OpenCode session replay — the `adjusted_tail` line was debug scaffolding, and the night's
   real fix was a Python `_EOF` sentinel in the bridge read loop).
2. **The ClientConnect patch** ([[songbird-clientconnect-patch]]): upstream ignores
   `ClientConnect` as "discontinued," but Discord still sends it — and without the
   SSRC→user_id mapping, the DAVE decrypt path **silently drops unmapped packets** before
   decryption. This is the **only behavioral vendored patch** (commit `313a220`, 3 files, 18
   lines) and the sole reason the vendor tree must be kept. Dies silently on re-vendor.

## Architectural outcome

The [[gateway-less-voice-driver]] design: songbird `Driver` standalone, no gateway client,
fed `ConnectionInfo` from Python's py-cord over stdin — one gateway per token.

## Lessons (meta)

- The expensive bugs were in *other people's correct-looking code* or *between layers* — not the
  feature logic.
- Silent drops are the enemy; prefer loud errors during bring-up.
- Wire reality beats documentation — twice.
- "Supported" in a feature matrix means the code exists, not that anyone runs it.

## The ClientConnect patch is now guarded (2026-08-25)

The "dies silently on re-vendor" risk above has tripwires (see [[known_debt]]
§ Vendored-songbird patch): a presence-contract test
(`tests/test_songbird_patch_contract.py`), a CI `cargo check --locked` job
(`voice-receiver` in `.github/workflows/test.yml`), a once-per-SSRC
`UNKNOWN_SSRC` stderr warning in `voice/rust_receiver/src/main.rs`, the
Python-side `voice.raw_ssrc_attribution` warning on sub-2^32 "user ids"
(`d4_1_io_bridge.py`), and hot-reloader watching of `vendor/songbird/src/`.
Losing the patch now fails CI or logs loudly — it can no longer vanish quietly.

## See also

[[voice_flow]] · [[rust_voice_bridge]] · [[architecture]] · [[index]]
