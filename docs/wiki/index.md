# Serin Research Wiki — Index

Hard-won knowledge that does not live in the code, the internet, or anyone
else's head. Articles use `[[wikilink]]` syntax. Sources: git history, vendored
diffs, and the author's debugging sessions.

## Voice / Rust Receiver

- [[dave-support-vs-receive-support]] — the thesis: every library advertised
  DAVE, none had a living voice-*receive* implementation; the whole ordeal
  in one distinction
- [[songbird-dave-offset-bug]] — the one-line upstream bug (computed offset
  discarded) that broke every Opus decode under DAVE encryption
- [[songbird-clientconnect-patch]] — re-enabling the "discontinued"
  ClientConnect event for SSRC→user_id mapping
- [[gateway-less-voice-driver]] — running songbird's Driver standalone with no
  Discord gateway, fed from Python
- [[python-rust-voice-protocol]] — the stdin/stdout wire protocol between
  RustVoiceBridge and the receiver binary

## Debugging History

- [[voice-debugging-log]] — root causes and dead ends from the voice pipeline
  bring-up (July 2026)
