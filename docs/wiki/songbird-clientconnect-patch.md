# Re-enabling ClientConnect for SSRC→user mapping

**Second vendored songbird patch (commit `313a220`, 2026-07-24): upstream
deliberately ignores the `ClientConnect` voice-gateway event because Discord's
docs call it discontinued — but Discord's servers still send it, and a pure
receiver needs it.**

## The problem

To attribute incoming audio to a Discord user, you need the
`user_id ↔ audio_ssrc` mapping. Upstream songbird only learns SSRCs from
`Speaking` events — fine for a music bot, but a receiver wants the mapping
**at connect time**, before anyone has spoken. Upstream's handler was
literally:

```rust
GatewayEvent::ClientConnect(ev) => {
    debug!("Received discontinued ClientConnect: {:?}", ev);
},
```

Discord deprecated the event in their public docs; songbird's maintainers
followed the docs and reduced it to a debug log. The wire disagrees: the event
still arrives, carrying exactly the `user_id` + `audio_ssrc` pair we need.
Same theme as [[songbird-dave-offset-bug]]: **trust the wire, not the docs.**
And like that bug, this omission is invisible to senders — only a receiver
attributing inbound audio ever needs the mapping
([[dave-support-vs-receive-support]]).

## The patch (3 files, 18 lines)

1. `driver/tasks/ws.rs` — on `ClientConnect`, populate both signalling maps
   and fire a core event:
   ```rust
   self.ssrc_signalling.user_ssrc_map.insert(ev.user_id, ev.audio_ssrc);
   self.ssrc_signalling.ssrc_user_map.insert(ev.audio_ssrc, ev.user_id);
   drop(interconnect.events.send(EventMessage::FireCoreEvent(
       CoreContext::ClientConnect(ev),
   )));
   ```
2. `events/core.rs` — add `CoreEvent::ClientConnect` variant.
3. `events/context/mod.rs` — add `EventContext::ClientConnect(ClientConnect)`
   and `CoreContext::ClientConnect` plus the two match arms wiring them up.

## Why it matters beyond convenience

The DAVE decrypt path in `udp_rx` looks up
`ssrc_signalling.ssrc_user_map.get(&ssrc)` and **silently drops the packet**
if the mapping is missing. Without this patch, audio from a user who hasn't
triggered a `Speaking` event yet is discarded before decryption — so the two
patches are load-bearing *together*.

The Python side ultimately consumes this via the receiver's SSRC bookkeeping
(`known_ssrcs` DashMap in `voice/rust_receiver/src/main.rs`) — see
[[gateway-less-voice-driver]] and [[python-rust-voice-protocol]].

## Maintenance warning

This dies silently on any songbird re-vendor. Diff to re-apply is commit
`313a220`. As of the 2026-08-05 verification, this is the **only**
behavioral patch in the vendor tree — the DAVE offset fix shipped upstream
in 0.6.0 (see [[songbird-dave-offset-bug]]) — so this patch alone is why
the vendor tree exists. Upstreaming it would let Serin drop the vendor
entirely.
