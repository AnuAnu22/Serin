# Voice Architecture Plan

## Phase 1 — Fix Now (VoiceProtocol Capture)
**Goal:** Unblock voice with zero DAVE/UDP from py-cord, Rust owns all voice transport.

### Implementation
- [x] **voice/voice_listener.py** — Add `InfoCaptureProtocol(discord.VoiceProtocol)`:
  - `connect()`: sends `guild.change_voice_state()`, waits for both events, returns ConnectionInfo
  - `on_voice_server_update(data)`: stores endpoint + token
  - `on_voice_state_update(member, before, after)`: stores session_id
  - Never opens voice ws or UDP — zero DAVE from Python
- [x] **voice/voice_listener.py** — `join_channel()` uses `channel.connect(cls=InfoCaptureProtocol)`, extracts ConnectionInfo, calls `rust_bridge.start_with_info()`
- [x] **voice/voice_listener.py** — `leave_channel()` calls `protocol.disconnect()` + `protocol.cleanup()` to clean py-cord's internal state
- [x] **voice/voice_listener.py** — Remove temp event-listener approach (on_voice_server_update / on_voice_state_update client listeners)
- [ ] Test: bot joins VC, Rust connects with full DAVE handshake, audio flows both ways

### Why this works
- `VoiceProtocol.on_voice_server_update()` IS called by py-cord's state machine when a protocol is registered via `channel.connect(cls=...)`
- `VoiceProtocol` is the **documented, stable API** for voice event routing (unlike client-level `add_listener(on_voice_server_update)` which never fires)
- Every music bot on py-cord uses this same path

---

## Phase 2 — Ideal Architecture (Rust Gateway Shard)
**Goal:** Zero py-cord involvement in voice. Rust has its own gateway shard.

### Architecture
```
Python shard [0, 1]                     Rust shard [1, 1]
  ├─ Text messages                        ├─ Voice Gateway ws
  ├─ Commands                             ├─ Songbird Driver
  ├─ Guild/member state                   ├─ DAVE
  ├─ Memory/personality                   ├─ Opus receive
  └─ TTS orchestration                    ├─ TTS playback
                                          └─ STT transcription
                    IPC (stdin/stdout)
                    {"cmd": "join", ...}
                    {"event": "transcript", ...}
                    {"cmd": "speak", data_len + raw WAV}
```

### Implementation
- [ ] **rust_receiver/src/main.rs** — Add `serenity` or `twilight` gateway client
  - Connect as shard `[1, 1]` (py-cord uses `[0, 1]`)
  - Handle Opcode 4 (voice state update) + Opcode 2 (voice server update)
  - Parse session_id, endpoint, token from gateway events
  - Call `driver.connect()` with extracted ConnectionInfo
  - Handle `SEND_SPEAKING` gateway op for TTS
- [ ] **rust_receiver/src/main.rs** — IPC commands expand:
  - `JOIN:{guild_id}:{channel_id}` — join VC, Rust handles gateway events
  - `LEAVE` — send Opcode 4 with channel=null
  - `SPEAK:{len}` + data — same as current
  - `SHUTDOWN` — disconnect gateway + driver
- [ ] **rust_receiver/src/main.rs** — IPC events expand:
  - `TRANSCRIPT:{user_id}:{text}` — STT output back to Python
  - `CONNECTED` — voice session established
  - `DISCONNECTED` — voice session lost
- [ ] **voice/rust_voice_bridge.py** — Remove all py-cord dependencies, simplify to stdin/stdout IPC reader/writer
- [ ] **voice/voice_listener.py** — Strip to thin facade over Rust IPC (no VoiceProtocol, no `change_voice_state` calls)
- [ ] **voice/voice_output_manager.py** — Already routes through Rust, verify no py-cord voice refs
- [ ] Test: full voice flow with zero py-cord voice involvement

### Rust deps to add
- `serenity` (with `gateway` feature, no `voice` or `model`) or `twilight-gateway`
- `tokio-tungstenite` (already transitive via songbird)

### Risks / Notes
- Sharding math: py-cord must be told explicitly `shard_id=0, shard_count=2`. Check current config for `shard_count`.
- Must share session_id space — both shards use the same bot token.
- Discord allows multiple shards per token; this is standard practice for large bots.
