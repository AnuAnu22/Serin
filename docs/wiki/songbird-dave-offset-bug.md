# The songbird DAVE-offset bug

**The single most expensive bug in Serin's history: ~4 days of debugging that
ended in a one-line fix — upstream songbird 0.6.0 computes the correct value
and then uses the wrong variable.**

## Symptom

With DAVE (Discord's end-to-end voice encryption, https://daveprotocol.com)
active, **every** incoming Opus decode fails with `InvalidPacket`. No audio
ever reaches the VoiceTick handler. Nothing on the internet describes this;
almost nobody runs songbird as a *receiver* under DAVE.

## Root cause

In `vendor/songbird/src/driver/tasks/udp_rx/mod.rs`, after transport
decryption, DAVE-encrypted packets are decrypted a second time via
`dave_session.decrypt(...)`. DAVE decryption **strips overhead** — the 8-byte
truncated AES128-GCM auth tag, 1-byte supplemental-data size, 2-byte magic
marker — so `decrypted_body` is *shorter* than the encrypted `body`.

Upstream computes the corrected tail offset… and then discards it, passing the
stale `rtp_body_tail` into `StoredPacket`. Result: the Opus decoder is handed
the decrypted audio **plus trailing garbage bytes** (the now-meaningless
encryption overhead), and rejects every packet.

## The fix (vendored patch)

```rust
// BUGFIX: DAVE decrypt strips overhead (nonce+tag), shrinking the body.
// adjusted_tail accounts for this so StoredPacket doesn't feed
// garbage bytes into the Opus decoder.
let adjusted_tail = rtp_body_tail + (body.len() - decrypted_body.len());
packet_data = Some((rtp_body_start, adjusted_tail, decrypted));
body[..decrypted_body.len()].copy_from_slice(&decrypted_body);
```

Location: `voice/rust_receiver/vendor/songbird/src/driver/tasks/udp_rx/mod.rs`
(search for `adjusted_tail`). The `[patch.crates-io]` section of
`voice/rust_receiver/Cargo.toml` documents it and redirects the songbird dep to
`vendor/songbird`.

## Why respected maintainers missed it

- This bug is unreachable from the send path — see
  [[dave-support-vs-receive-support]]. The vast majority of songbird users
  only *send* audio (music bots), so "DAVE support" was tested for
  transmission and the receive plumbing shipped unexercised.
- DAVE receive is newer still — the encrypted-frame layout
  (tag + supplemental size + magic marker) is only specified at
  daveprotocol.com, not in Discord's own docs.
- The bug is invisible in code review: the correct computation *is present*;
  only the final use site references the wrong variable.

## Lessons

1. When every packet fails identically, suspect a **length/offset bookkeeping
   error** before suspecting crypto.
2. A computed-but-unused variable near the failure site is a smoking gun
   (a compiler `unused_variable` warning would have caught this — vendored
   crates suppress warnings).
3. Wire reality > documentation. See also [[songbird-clientconnect-patch]],
   where the same lesson applies to Discord's gateway docs.

## Maintenance warning

**This patch is silently destroyed by any re-vendor or version bump of
songbird.** Before updating: check whether upstream fixed it
(search their udp_rx for tail adjustment after DAVE decrypt); if not, re-apply.
Related patch in the same vendored tree: [[songbird-clientconnect-patch]].
