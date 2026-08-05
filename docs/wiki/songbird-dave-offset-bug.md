# The songbird DAVE-offset bug

**The most expensive bug in Serin's history: ~4 days of debugging around a
missing one-line offset adjustment in songbird's DAVE receive path. Verified
against upstream history on 2026-08-05: the bug was real, and upstream fixed
it themselves in commit `653177e7` (2026-03-12), which shipped in the 0.6.0
release — see "Historical verification" below for what that means for our
vendored patch.**

## Symptom

With DAVE (Discord's end-to-end voice encryption, https://daveprotocol.com)
active, **every** incoming Opus decode fails with `InvalidPacket`. No audio
ever reaches the VoiceTick handler. Nothing on the internet describes this;
almost nobody runs songbird as a *receiver* under DAVE.

## Root cause

In `driver/tasks/udp_rx/mod.rs`, DAVE decryption **strips overhead** — the
8-byte truncated AES128-GCM auth tag, 1-byte supplemental-data size, 2-byte
magic marker — so the decrypted body is *shorter* than the encrypted body.
The pre-fix code (songbird git, 2026-02-22 "receiving support" through
2026-03-11) copied the plaintext over the buffer but **never updated
`packet_data`**:

```rust
// pre-fix upstream — the bug
Ok(decrypted_payload) => {
    body[..decrypted_payload.len()].copy_from_slice(&decrypted_payload);
},
```

The stale `rtp_body_tail` (transport-crypto tail only) then flowed into
`StoredPacket`, so the Opus decoder was handed the plaintext **plus trailing
DAVE overhead garbage** and rejected every packet.

## The fix — the one line

```rust
Ok(decrypted_body) => {
    packet_data = Some((
        rtp_body_start,
        rtp_body_tail + (body.len() - decrypted_body.len()),   // ← this line
        decrypted,
    ));
    body[..decrypted_body.len()].copy_from_slice(&decrypted_body);
},
```

In our vendored tree: `voice/rust_receiver/vendor/songbird/src/driver/tasks/
udp_rx/mod.rs` (search `adjusted_tail`).

## Historical verification (2026-08-05)

Diffing the vendored tree against the pristine crates.io 0.6.0 tarball and
upstream git history established:

- Upstream introduced the identical fix in `653177e7`
  ("Properly handle RTP payload padding + check if bodies are E2EE
  encrypted", 2026-03-12, part of DAVE PR #291), released in songbird
  0.6.0 on 2026-04-05.
- Our vendored `udp_rx/mod.rs` differs from released 0.6.0 only by the
  `adjusted_tail` variable name and comments — **semantically a no-op**
  against the 0.6.0 base we vendor. The same is true of a small
  loop-hoist in `ssrc_state.rs`.
- Therefore the only *behavioral* vendored patch remaining is
  [[songbird-clientconnect-patch]] — that one is still absent upstream and
  is the sole reason the vendor tree must be kept.
- The `Cargo.toml` claim that upstream "computes but discards" the offset
  described the *pre-March-12* code from memory; released 0.6.0 does not
  have the bug.

Sharpened 2026-08-05 (second pass): a full untruncated diff confirms the
vendored `udp_rx/mod.rs` differs from the crates.io 0.6.0 tarball by
**exactly one line** (the rename) — and the vendor base is otherwise
byte-identical to the tarball, proving the vendor came from released 0.6.0.
Yet plain 0.6.0 receive-under-DAVE genuinely *does* fail in Serin's setup:
the only writer of `ssrc_user_map` in 0.6.0 is the `Speaking` handler
(gated on `ev.user_id` being non-null), and the DAVE decrypt path silently
drops every packet whose SSRC is unmapped — total deafness, zero errors.
So "0.6.0 still didn't work" is true; the working fix was the
[[songbird-clientconnect-patch]] map insertions, and the `InvalidPacket`
narrative belongs to the pre-0.6.0 upstream code where that bug
demonstrably existed.

## Case closed (2026-08-05, third pass — OpenCode session forensics)

The full debugging session survives in the OpenCode database
(`~/.local/share/opencode/opencode.db`, session
`ses_0f004b086ffe8h3pyR7lklts0H`, 2026-06-29). Replaying its edit history
settles the question definitively:

1. **18:54** — first-ever edit to the vendored `udp_rx/mod.rs`. Its
   `oldString` shows the file *already* contained the offset fix inline
   (`rtp_body_tail + (body.len() - decrypted_body.len())` in the tuple).
   The edit extracted it into `let adjusted_tail = …` **purely so debug
   logging could print it** (`[DBG-DAVE] … adjusted_tail={}`). That is the
   birth of the one remembered line — diagnostic scaffolding, not a fix.
2. **19:20** — the actual root cause of that night's deafness was found in
   **Python**: `rust_voice_bridge.py`'s `_read_loop` used `queue.get(1.0)`
   where `None` meant both "1s timeout" and "process died". One second of
   silence → false EOF → bridge tears down the healthy Rust process. Fix:
   a distinct `_EOF` sentinel object.
3. **19:28** — verified: **0 `OPUS_FAIL` in 4215 diagnostic lines**; the
   session's own conclusion reads "The Rust code was fine all along — DAVE
   decrypt and Opus decode both work correctly with the vendored 0.6.0."
4. **19:40** — debug lines removed; the `adjusted_tail` variable was left
   behind (the surviving no-op diff).
5. **19:50** — asked "tell me what the songbird issue was", the assistant
   **confabulated** the "computed `adjusted_tail` but discarded it" story
   (contradicting its own 19:28 finding), and at 19:54 enshrined it in the
   Cargo.toml comment and the inline `BUGFIX:` comment. That
   documentation-of-a-fix-that-never-happened is the origin of the
   "one-line songbird fix" memory.

So the ordeal's real villains, in order: the Python EOF/timeout conflation
(June 29), and the unmapped-SSRC silent drop later killed by
[[songbird-clientconnect-patch]] (July 23). The remembered one-line
`udp_rx` change is real — it just was never load-bearing.

## Why respected maintainers missed it (for the weeks it existed)

- This bug is unreachable from the send path — see
  [[dave-support-vs-receive-support]]. The vast majority of songbird users
  only *send* audio (music bots), so DAVE was tested for transmission and
  the receive plumbing went out unexercised until the PR author circled
  back.
- The pre-fix code even carried a "HACK" comment guessing at PKCS7 padding —
  the tail bookkeeping was known-murky territory.

## Lessons

1. When every packet fails identically, suspect a **length/offset
   bookkeeping error** before suspecting crypto.
2. Wire reality > documentation. See also [[songbird-clientconnect-patch]].
3. **Verify vendored patches against the exact upstream base.** Our "DAVE
   offset bugfix" turned out to be already present in the 0.6.0 we vendor —
   the patch survived as a no-op for a month because nobody diffed against
   the pristine crate.

## Maintenance status

- The DAVE-offset fix needs **no** re-applying on future songbird updates —
  upstream has shipped it since 0.6.0.
- [[songbird-clientconnect-patch]] is the only patch that must survive a
  re-vendor.
