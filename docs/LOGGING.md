# Serin Logging Convention

## Format: `{component}.{event}`

Every log message uses a dot-separated event name as the first positional argument
to the logger call, followed by a structured `extra={}` dict.

### Examples

```
pipeline.start
pipeline.stage_error
memory.search_complete
memory.write_failed
voice.process_died
voice.tts_sent
llm.call_start
llm.call_complete
llm.fallback_used
```

## Required extra fields by level

| Level    | Required extra fields                                                                 |
|----------|---------------------------------------------------------------------------------------|
| DEBUG    | Whatever helps trace the specific item                                                |
| INFO     | `user` (or `guild_id`), `channel_id`, `outcome`, `duration_ms` for ops > 10ms         |
| WARNING  | Same as INFO + `degradation_reason`                                                    |
| ERROR    | Same as WARNING + `exc_info=True` always                                               |
| CRITICAL | Everything + `requires_intervention=True`                                              |

## Level usage rules

| Level    | When to use                                                                 |
|----------|-----------------------------------------------------------------------------|
| DEBUG    | Per-chunk audio, individual memory hits, token counts, stage internals       |
| INFO     | User-visible actions: message sent, memory stored, voice session events     |
| WARNING  | Degraded operation: Qdrant slow, fallback used, lock timeout, retries       |
| ERROR    | Subsystem failure: LLM down, Rust crash, embedding failed                   |
| CRITICAL | Bot cannot operate without intervention                                     |

## Structured log pattern

### DO this:
```python
logger.info("memory.search_complete", extra={
    "user": ctx.username,
    "user_id": ctx.user_id,
    "channel_id": ctx.channel_id,
    "memories_found": len(results),
    "duration_ms": elapsed_ms,
})
logger.error("memory.search_failed", extra={
    "user_id": user_id,
    "query_preview": query[:50],
    "error": str(e),
}, exc_info=True)
```

### Do NOT do this:
```python
logger.info(f"Got response for {user}: {response[:50]}")
logger.error("Memory search failed")
```

## Event name registry

### Pipeline
- `pipeline.start`
- `pipeline.complete`
- `pipeline.halted`
- `pipeline.stage_error`
- `pipeline.decision`
- `pipeline.memory_retrieval_start`
- `pipeline.memory_retrieval_complete`
- `pipeline.memory_filtered_garbage`
- `pipeline.temporal_resolved`
- `pipeline.personality`
- `pipeline.prompt_assembled`
- `pipeline.llm_response`
- `pipeline.response_cleaned`
- `pipeline.response_sent`
- `pipeline.memory_written`
- `pipeline.memory_write_failed`

### Memory
- `memory.search_start`
- `memory.search_complete`
- `memory.write_start`
- `memory.write_failed`
- `memory.embedding_failed_skipping_write`
- `memory.recent_message_stored`

### Voice
- `voice.process_start`
- `voice.process_died`
- `voice.tts_sent`
- `voice.buffer_overflow_forced_flush`
- `voice.lock_acquired`
- `voice.lock_released`
- `voice.lock_timeout`

### LLM
- `llm.initialize`
- `llm.call_start`
- `llm.call_complete`
- `llm.fallback_used`

### System
- `system.startup`
- `system.shutdown`
- `system.maintenance_start`
- `system.maintenance_complete`
