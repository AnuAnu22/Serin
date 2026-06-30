# Serin Architecture

## System Overview

Serin is a Discord AI companion with real-time voice, long-term memory, and multi-modal LLM support (text, vision, audio). It runs as a single Python asyncio process with a companion Rust subprocess for voice handling.

## Package Map

| Package | Owns |
|---|---|
| `serin/core/` | Config, logging — imported by everything |
| `serin/memory/` | I/O: `store.py` (Qdrant + SQLite), `evidence.py` (FactStore), `beliefs.py` (BeliefStore), BM25, hybrid search |
| `serin/messaging/` | Message pipeline — all text response logic |
| `serin/messaging/stages/` | 10 independently testable pipeline stages |
| `serin/personality/` | Personality traits, conversation mood |
| `serin/models/` | LLM connectors (vLLM, LM Studio, SGLang) |
| `serin/utils/` | Background jobs, passive monitor, database protector |
| `serin/control_panel/` | Flask web dashboard |
| `voice/` | Voice: Rust bridge, VAD, TTS, transcription |
| `models/` | Model factory, interface, adapters |
| `serin_core/` | PyO3 Rust module: text processing utilities |

## Data Flow: Text Message

```
1. Discord Gateway Event
       │
       ▼
2. discord_bot.py:on_message()
       │
       ├── PassiveMonitor may write observation to memory
       │
       ▼
3. MessagePipeline.process(ctx)     ← serin/messaging/pipeline.py
       │
        ├── 1. ResponseDecisionStage   — Check mention, rate limit, DM rules
        ├── 2. MemoryRetrievalStage    — Qdrant hybrid search + facts + beliefs
        ├── 3. ResponsePlannerStage    — Read beliefs + intent → stance + constraints
        ├── 4. TemporalStage           — Resolve "yesterday", "next week"
        ├── 5. PersonalityStage        — Inject tone modifier + traits
        ├── 6. PromptAssemblyStage     — Build system + context + history
        ├── 7. LLMCallStage            — Call model via factory
        ├── 8. ResponseCleaningStage   — Filter thinking tags, naturalize
        ├── 9. SendStage               — Typing indicator + channel.send()
        └── 10. MemoryWriteStage       — Store interaction + update facts/beliefs
       │
       ▼
4. Discord Message Sent
```

## Data Flow: Voice Message

```
1. User speaks in voice channel
       │
       ▼
2. Discord sends encrypted Opus frames
       │
       ▼
3. Rust subprocess (voice/rust_receiver/)
   - DAVE decrypt → Opus decode → PCM → stdout
       │
       ▼
4. voice/bridge.py reads stdout
       │
       ▼
5. voice/processor.py:process_audio_chunk()
   - Per-user buffer (dict of bytearrays)
   - RMS-based VAD (threshold=150)
   - Silence counting (75 frames = 1.5s)
   - Noise burst filter (<25 frames ignored)
       │
       ▼  (after silence threshold reached)
6. _queue_for_transcription()
   → _set_lock(30s) prevents new transcriptions
       │
       ├── Gemma (direct audio): raw PCM → input_audio field
       └── Other models: Whisper STT → text
       │
       ▼
7. LLM generates response
       │
       ▼
8. Edge-TTS synthesizes WAV
       │
       ▼
9. Rust subprocess plays in voice channel
       │
       ▼
10. TrackEvent::End → TTS_DONE → Python _release_lock()
```

## Memory Decomposition

The memory layer was split from a single 1,900-line monolith (`qdrant.py`) into three domain-separated modules:

| Module | Owns |
|---|---|
| `memory/store.py` | Qdrant client, SQLite connection, BM25 index — I/O only. Owns schema creation, memory CRUD, hybrid search, user profiles, recent messages cache. |
| `memory/evidence.py` | `FactStore` — atomic verifiable facts with auto-supersede (board states, game results). Keyword-based retrieval (not embedding). Source-type reliability tiers. |
| `memory/beliefs.py` | `BeliefStore` — state machine (`PENDING` → `SUPPORTED` → `CONTESTED` → `SUPERSEDED` → `UNKNOWN`) with Bayesian confidence. Inference from facts. |

The old `qdrant.py` survives as a 4-line re-export shim so all existing imports (`from serin.memory.qdrant import QdrantMemorySystem`) continue to work without changes.

**Rule:** if you're adding logic about *beliefs* or *evidence*, it goes in `beliefs.py` or `evidence.py`, not in `store.py`. The store talks to databases; it doesn't know what a belief *means*.

## Key Design Decisions

### Why Rust for voice?
Discord uses DAVE encryption for voice since 2024. No Python library handles it. The Rust subprocess uses vendored songbird 0.6.0 with a custom DAVE patch.

### Why subprocess IPC instead of FFI?
Safer crash isolation. If the Rust voice process dies, Python keeps running (albeit without voice). FFI panics kill the whole process. The supervisor implements rate-limited restarts (max 5 per 60s).

### Why a pipeline for messaging?
The original god object (`enhanced_message_manager.py`, 1021 lines) made every change risky. The pipeline makes stages independently testable and replaceable.

### Why Qdrant + BM25 hybrid search?
Neither alone is sufficient. BM25 is great for keyword matches ("that thing we discussed about Python") but bad for semantic similarity. Qdrant vectors capture meaning but miss exact keywords. Hybrid gives both.

### Why Gemma direct audio input?
Audio transcription loses tone, emphasis, and emotional nuance. Gemma 12B supports raw PCM via `input_audio` field, preserving full audio context. Only available when model type contains "gemma".

### Why 1.5s silence threshold?
Discord voice gaps between sentences are typically 0.3-1.0s. A 1.5s threshold prevents mid-sentence chunking while keeping response latency acceptable. The burst filter (25 frames = <0.5s) prevents brief noises from resetting the silence counter.

### Why Edge-TTS instead of Bark/XTTS?
Bark and XTTS are GPU-heavy and add 3-5s latency per generation. Edge-TTS runs on CPU, streams audio, and completes in <1s for typical responses. The trade-off is less natural prosody.

## Adding a Feature

### New pipeline behavior:
Add a `PipelineStage` subclass in `serin/messaging/stages/yourfeature.py`.
Insert it into `MessagePipeline.build()` in the right position.

### New memory type:
Add to `serin/memory/store.py` (Qdrant/SQLite I/O) or `serin/memory/evidence.py` (facts) or `serin/memory/beliefs.py` (beliefs) depending on the domain. Follow existing patterns.

### New LLM provider:
Add a connector in `models/`. Implement `ModelInterface`. Register in `models/factory.py`.

### New voice feature:
Modify `voice/processor.py` (VAD/buffering) or `voice/pipeline.py` (post-transcription).

## Logging Convention

All log messages follow the pattern `{component}.{event}` with structured `extra` dict fields. See `docs/LOGGING.md` for the full spec.

Examples:
- `pipeline.start` — message pipeline begins
- `memory.search_complete` — Qdrant hybrid search finished
- `voice.process_died` — Rust voice subprocess exited unexpectedly
- `llm.fallback_used` — Primary LLM unavailable, fallback active

## Safety Mechanisms

| Mechanism | Location | Description |
|---|---|---|
| Processing lock (30s) | voice/processor.py | Prevents concurrent transcriptions; expired by TTS_DONE or timeout |
| Buffer overflow (5.7MB/50MB) | voice/processor.py | Forces transcription if buffer exceeds model limit |
| Min buffer (192KB ~1s) | voice/processor.py | Discards audio under 1 second (noise) |
| Rust crash supervisor | voice/bridge.py | Max 5 restarts per 60s window |
| Passive monitor | serin/utils/passive_monitor.py | Rate-limits observation writes |
| Database protector | serin/utils/database_protector.py | Validates SQLite integrity before writes |
