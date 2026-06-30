# SERIN AUTONOMOUS REFACTOR — MASTER EXECUTION PROMPT

> **Send this entire prompt to your AI agent (Claude, Cursor, etc.) with codebase access.
> The AI should work autonomously for as long as needed. Do not interrupt it.**

---

## WHO YOU ARE

You are a staff-level engineer — think ex-Google/Meta/Netflix — hired to transform the
Serin Discord AI bot codebase from a working-but-sprawling prototype into a
world-class, maintainable production codebase. You have full autonomy. You make
decisions. You do not ask for permission on judgment calls.

The codebase is at: https://github.com/AnuAnu22/Serin
Clone it locally before doing anything else.

```bash
git clone https://github.com/AnuAnu22/Serin.git
cd Serin
```

---

## YOUR PRIME DIRECTIVE

Transform Serin so that:
1. Any developer (or AI) can open any file and immediately know what it owns
2. Bugs are locatable in under 2 minutes by reading structure alone
3. New features slot in without touching unrelated files
4. Logs tell a story — every log line answers: what, who, why, outcome
5. Zero mystery files, zero dead code, zero undocumented globals
6. The pipeline architecture makes the flow of data self-evident
7. Tests exist and actually test the right things

**You are NOT changing Serin's behavior. You are changing how the code is organized,
named, structured, and observed. The bot must work identically before and after.**

---

## CRITICAL RULES — READ BEFORE TOUCHING ANYTHING

1. **Commit after every completed task group.** Use descriptive commit messages:
   `refactor(memory): extract qdrant.py from qdrant_memory_system.py`

2. **No logic changes.** If you find yourself changing what code DOES (not where it
   lives or how it's named), STOP. Make a note in `CHANGES_DEFERRED.md` and move on.

3. **Context budget.** You are working inside a context window. When you feel it
   filling up (you've done 60%+ of your work in this session), use sub-agents or
   spawn a new task for the remaining items. Write `PROGRESS.md` before context gets
   tight so the next session knows exactly where to resume.

4. **Verify before moving on.** After each phase, run:
   ```bash
   python -c "import discord_bot" 2>&1 | head -20
   ```
   If there are import errors, fix them before proceeding.

5. **Never delete a file without confirming it's dead.** For each file you plan to
   delete, search all .py files for its name first:
   ```bash
   grep -r "filename_without_extension" --include="*.py" .
   ```
   If anything imports it: do NOT delete it. Move it and fix imports instead.

6. **PROGRESS.md is your memory.** Update it after every task. It should always
   answer: "If I had to hand this off right now, what would I write?"

---

## PHASE 0 — RECONNAISSANCE (Do this before writing a single line)

**Task 0.1 — Clone and survey**
```bash
git clone https://github.com/AnuAnu22/Serin.git
cd Serin
find . -name "*.py" | head -80
find . -name "*.rs" | head -20
wc -l *.py
```

**Task 0.2 — Create your working documents**

Create `PROGRESS.md` at the repo root:
```markdown
# Serin Refactor Progress

## Status: PHASE 0 — Reconnaissance
## Last completed task: 0.2
## Next task: 0.3
## Blockers: none
## Notes:
```

Create `CHANGES_DEFERRED.md` at the repo root:
```markdown
# Deferred Changes (logic changes found during refactor — do not implement now)

## Format: [file] — [what was found] — [recommended fix later]
```

**Task 0.3 — Dead code audit**

For each file in this list, run the grep check and mark it DEAD or ALIVE:
- `memory_system.py` (legacy ChromaDB)
- `voice/voice_output_queue.py`
- `audio_config_manager.py`
- `check_qdrant_methods.py`
- `gpu.py`
- `visual_memory_system.py`
- `debug_backfilling_detailed.py`
- `final_backfilling_verification.py`
- `reproduce_fts_error.py`
- `memory_system_demo.py`
- `memory_testing_framework.py`
- `simple_test.py`
- `test_output.txt`
- `=2.6.1` (this is likely a malformed file — check it)
- `desktop.ini`
- `requirements1.txt`
- `setup_environment_fixed.sh`
- `implementation_guide.md`, `implementation_summary.md`, `improvements_summary.md`
- `memory_system_strategy.md`, `qdrant_migration_plan.md`
- `deployment_checklist.md`, `start_guide.md`, `troubleshooting_guide.md`
- `todo.md`

**Task 0.4 — Read key files in full before restructuring**

Read these files completely — you need to understand them before moving anything:
- `discord_bot.py` (entry point + initialization order)
- `enhanced_message_manager.py` (the god object you will pipeline-ize)
- `config.py` (globals everything imports)
- `logger_config.py` (logger every module uses)
- `qdrant_memory_system.py` (memory system core)
- `voice/rust_voice_bridge.py` (Rust IPC)
- `voice/audio_stream_processor.py` (VAD pipeline)
- `passive_monitor.py` (was a missing file in audit — read it now)
- `memory_sync_monitor.py` (was missing in audit — read it now)

Write a one-sentence description of each in `PROGRESS.md`. This will be your map.

**Task 0.5 — Verify the bot actually runs before touching it**
```bash
# Don't actually start the bot (needs Discord token), just check imports
python -c "
import sys
sys.path.insert(0, '.')
try:
    import config
    print('config: OK')
    import logger_config
    print('logger_config: OK')
    import qdrant_memory_system
    print('qdrant_memory_system: OK')
except Exception as e:
    print(f'IMPORT ERROR: {e}')
"
```

Record results in PROGRESS.md. Fix any import errors you find before phase 1.

---

## PHASE 1 — CLEAN THE ROOT (Housekeeping)

**Goal:** The repo root should contain only entry points and config. Everything else
lives in a package. This phase is pure file moves + import updates. No logic changes.

**Task 1.1 — Create the docs folder and move planning docs**

```bash
mkdir -p docs
```

Move these files into `docs/` (they are reference material, not code):
- `implementation_guide.md`
- `implementation_summary.md`
- `improvements_summary.md`
- `memory_system_strategy.md`
- `qdrant_migration_plan.md`
- `qdrant_migration_setup.sh`
- `deployment_checklist.md`
- `start_guide.md`
- `troubleshooting_guide.md`
- `todo.md`
- `SERIN_VISION.md`
- `CODING_GUIDELINES.md`

Keep at root: `README.md`, `.env.example`, `.gitignore`, `pyproject.toml`,
`requirements.txt`, `uv.lock`

**Task 1.2 — Delete confirmed dead files**

Only delete files confirmed DEAD in Task 0.3. For each deletion:
```bash
grep -r "filename" --include="*.py" . | grep -v "^Binary"
# If zero results: safe to delete
# If any results: DO NOT DELETE, move to appropriate package instead
```

Files that are almost certainly safe to delete (verify first):
- `=2.6.1` (malformed filename, not a Python file)
- `desktop.ini` (Windows artifact)
- `requirements1.txt` (duplicate)
- `test_output.txt` (test artifact)
- `memory_system.py` (legacy ChromaDB, not imported anywhere per audit)
- `voice/voice_output_queue.py` (empty, zero imports)
- `debug_backfilling_detailed.py`, `final_backfilling_verification.py` (one-time scripts)
- `reproduce_fts_error.py` (one-time debug script)
- `memory_system_demo.py`, `memory_testing_framework.py` (move to tests/ instead)

**Task 1.3 — Move test files into tests/**

Any file at root matching `test_*.py` or `verify_*.py` or `*_test.py` belongs in
`tests/`. Move them:
```bash
mkdir -p tests
mv test_active_search_init.py tests/
mv test_active_search_loop.py tests/
mv test_database_protection.py tests/
mv test_datetime_fixes.py tests/
mv test_decode_refactor.py tests/
mv test_fix_fts.py tests/
mv test_human_responses.py tests/
mv test_qdrant_migration.py tests/
mv verify_active_search.py tests/
mv verify_active_search_live.py tests/
mv simple_test.py tests/
```

After moving, update any imports inside those test files that reference root-level modules.

**Task 1.4 — Consolidate the two hot-reloaders**

There are two: `dev.py` (simple watchfiles) and `hot_reloader.py` (full rebuild with
Rust support). `hot_reloader.py` is the intended one.

Action: Add a comment to the top of `dev.py`:
```python
# DEPRECATED: Use hot_reloader.py instead.
# This file does not rebuild Rust components on change.
# Kept for reference only.
```

Do NOT delete `dev.py` yet — it may be in someone's workflow.

**Task 1.5 — Consolidate requirements files**

Check if `requirements.txt` and `pyproject.toml` are in sync:
```bash
cat requirements.txt
cat pyproject.toml
```

If `pyproject.toml` has all dependencies, add a comment to `requirements.txt`:
```
# This file is kept for pip compatibility.
# Primary dependency management is via pyproject.toml + uv.
# To update: uv sync
```

**Task 1.6 — Commit Phase 1**
```bash
git add -A
git commit -m "chore: clean root — move docs, delete dead files, consolidate test files"
```

---

## PHASE 2 — PACKAGE RESTRUCTURE

**Goal:** Move Python source files into a proper package hierarchy.
This is the most mechanical phase. The new structure is defined below exactly.
Follow it precisely.

### Target Package Structure

```
serin/                          ← NEW: main package (create __init__.py in each)
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py               ← MOVE from: config.py
│   └── logger.py               ← MOVE from: logger_config.py
│
├── memory/
│   ├── __init__.py
│   ├── qdrant.py               ← MOVE from: qdrant_memory_system.py
│   ├── retrieval.py            ← MOVE from: enhanced_memory_retrieval.py
│   ├── context.py              ← MOVE from: enhanced_memory_context.py
│   ├── sync_monitor.py         ← MOVE from: memory_sync_monitor.py
│   └── temporal.py             ← MOVE from: temporal_context.py
│
├── messaging/
│   ├── __init__.py
│   ├── manager.py              ← MOVE from: enhanced_message_manager.py
│   ├── context_builder.py      ← MOVE from: conversation_context_builder.py
│   ├── response_generator.py   ← MOVE from: natural_response_generator.py
│   ├── response_controller.py  ← MOVE from: response_controller.py
│   ├── mention_translator.py   ← MOVE from: mention_translator.py
│   ├── correction_handler.py   ← MOVE from: correction_handler.py
│   ├── fillers.py              ← MOVE from: conversational_fillers.py
│   ├── typos.py                ← MOVE from: realistic_typos.py
│   ├── long_message.py         ← MOVE from: long_message_handler.py
│   └── crawler.py              ← MOVE from: message_crawler.py
│
├── personality/
│   ├── __init__.py
│   ├── bot_personality.py      ← MOVE from: bot_personality.py
│   ├── conversation_analyzer.py ← MOVE from: conversation_analyzer.py
│   └── topic_fatigue.py        ← MOVE from: topic_fatigue.py
│
├── voice/                      ← RESTRUCTURE existing voice/ package
│   ├── __init__.py
│   ├── bridge.py               ← RENAME from: voice/rust_voice_bridge.py
│   ├── processor.py            ← RENAME from: voice/audio_stream_processor.py
│   ├── pipeline.py             ← RENAME from: voice/voice_memory_pipeline.py
│   ├── output.py               ← RENAME from: voice/voice_output_manager.py
│   ├── transcriber.py          ← RENAME from: voice/whisper_transcriber.py
│   ├── listener.py             ← RENAME from: voice/voice_listener.py
│   ├── behavior.py             ← RENAME from: voice/voice_behavior_manager.py
│   ├── tracker.py              ← RENAME from: voice/voice_tracker.py
│   ├── decider.py              ← RENAME from: voice/voice_action_decider.py
│   ├── profiles.py             ← RENAME from: voice/voice_profiles.py
│   └── rust_receiver/          ← UNCHANGED (Rust binary, do not touch)
│
├── models/                     ← RESTRUCTURE existing models/ package
│   ├── __init__.py
│   ├── factory.py              ← RENAME from: models/model_factory.py
│   ├── interface.py            ← RENAME from: models/model_interface.py
│   ├── adapter.py              ← RENAME from: models/model_adapter.py
│   ├── vllm.py                 ← RENAME from: models/vllm_connector.py
│   ├── lm_studio.py            ← RENAME from: models/lm_studio_connector.py
│   └── sglang.py               ← RENAME from: models/sglang_connector.py
│
├── utils/
│   ├── __init__.py
│   ├── background.py           ← MOVE from: background_processor.py
│   ├── passive_monitor.py      ← MOVE from: passive_monitor.py
│   ├── thinking_filter.py      ← MOVE from: thinking_filter.py
│   ├── debug_logger.py         ← MOVE from: debug_logger.py
│   └── database_protector.py   ← MOVE from: database_protector.py
│
├── control_panel/
│   ├── __init__.py
│   ├── server.py               ← MOVE from: web_server.py
│   └── routes.py               ← MOVE from: enhanced_api_routes.py
│
└── serin_core/                 ← UNCHANGED (PyO3 Rust module — do not touch)
```

**Remaining at root (do not move these):**
- `discord_bot.py` — entry point, stays at root
- `hot_reloader.py` — dev launcher, stays at root
- `dev.py` — deprecated but stays at root
- `config.py` — keep a shim here for backwards compat (see Task 2.2)
- `pyproject.toml`, `requirements.txt`, `uv.lock`, `.env.example`, `.gitignore`, `README.md`

### Task 2.1 — Create all package directories and `__init__.py` files

```bash
mkdir -p serin/core serin/memory serin/messaging serin/personality
mkdir -p serin/utils serin/control_panel

# Create __init__.py for each
touch serin/__init__.py
touch serin/core/__init__.py
touch serin/memory/__init__.py
touch serin/messaging/__init__.py
touch serin/personality/__init__.py
touch serin/utils/__init__.py
touch serin/control_panel/__init__.py
```

The `voice/` and `models/` dirs already exist — just add `__init__.py` if missing.

### Task 2.2 — Move files one package at a time

**Do each package as a separate sub-task. After each package move, fix imports and
verify python import works before moving to the next package.**

#### Sub-task 2.2a — serin/core/

```bash
cp config.py serin/core/config.py
cp logger_config.py serin/core/logger.py
```

In `serin/core/logger.py`, rename the module reference if it says `serin_ai`:
```python
# Change: logging.getLogger('serin_ai')
# To:     logging.getLogger('serin')
```

Create backward-compat shims at root so nothing breaks yet:
```python
# config.py (keep at root, becomes a shim)
"""Backwards compatibility shim. Import from serin.core.config directly."""
from serin.core.config import *  # noqa: F401, F403
from serin.core.config import config, BotConfig  # explicit re-exports
```

```python
# logger_config.py (keep at root, becomes a shim)
"""Backwards compatibility shim. Import from serin.core.logger directly."""
from serin.core.logger import *  # noqa: F401, F403
from serin.core.logger import logger  # explicit re-export
```

Verify:
```bash
python -c "from serin.core.config import config; print('core.config OK')"
python -c "from serin.core.logger import logger; print('core.logger OK')"
python -c "from config import config; print('shim OK')"
```

#### Sub-task 2.2b — serin/memory/

```bash
cp qdrant_memory_system.py serin/memory/qdrant.py
cp enhanced_memory_retrieval.py serin/memory/retrieval.py
cp enhanced_memory_context.py serin/memory/context.py
cp memory_sync_monitor.py serin/memory/sync_monitor.py
cp temporal_context.py serin/memory/temporal.py
```

In each new file, update internal imports:
- `from logger_config import logger` → `from serin.core.logger import logger`
- `from config import config` → `from serin.core.config import config`
- Cross-references between memory files update to `from serin.memory.X import Y`

Add to `serin/memory/__init__.py`:
```python
"""Serin memory subsystem — Qdrant vector store, hybrid search, context assembly."""
from serin.memory.qdrant import QdrantMemorySystem
from serin.memory.retrieval import EnhancedMemoryRetrieval
from serin.memory.context import EnhancedMemoryContext

__all__ = ["QdrantMemorySystem", "EnhancedMemoryRetrieval", "EnhancedMemoryContext"]
```

Verify:
```bash
python -c "from serin.memory import QdrantMemorySystem; print('memory OK')"
```

#### Sub-task 2.2c — serin/messaging/

```bash
cp enhanced_message_manager.py serin/messaging/manager.py
cp conversation_context_builder.py serin/messaging/context_builder.py
cp natural_response_generator.py serin/messaging/response_generator.py
cp response_controller.py serin/messaging/response_controller.py
cp mention_translator.py serin/messaging/mention_translator.py
cp correction_handler.py serin/messaging/correction_handler.py
cp conversational_fillers.py serin/messaging/fillers.py
cp realistic_typos.py serin/messaging/typos.py
cp long_message_handler.py serin/messaging/long_message.py
cp message_crawler.py serin/messaging/crawler.py
```

Update imports in each file. Add to `serin/messaging/__init__.py`:
```python
"""Serin messaging subsystem — message processing, context building, response generation."""
from serin.messaging.manager import EnhancedMessageManagerV3
from serin.messaging.response_generator import get_response_natural

__all__ = ["EnhancedMessageManagerV3", "get_response_natural"]
```

Verify:
```bash
python -c "from serin.messaging import EnhancedMessageManagerV3; print('messaging OK')"
```

#### Sub-task 2.2d — serin/personality/

```bash
cp bot_personality.py serin/personality/bot_personality.py
cp conversation_analyzer.py serin/personality/conversation_analyzer.py
cp topic_fatigue.py serin/personality/topic_fatigue.py
```

Update imports. Add to `serin/personality/__init__.py`:
```python
"""Serin personality subsystem — traits, tone, conversation mood."""
from serin.personality.bot_personality import BotPersonality
from serin.personality.conversation_analyzer import ConversationAnalyzer

__all__ = ["BotPersonality", "ConversationAnalyzer"]
```

#### Sub-task 2.2e — serin/voice/ (rename within existing package)

The `voice/` directory already exists. Rename files within it:
```bash
cd voice
cp rust_voice_bridge.py bridge.py
cp audio_stream_processor.py processor.py
cp voice_memory_pipeline.py pipeline.py
cp voice_output_manager.py output.py
cp whisper_transcriber.py transcriber.py
cp voice_listener.py listener.py
cp voice_behavior_manager.py behavior.py
cp voice_tracker.py tracker.py
cp voice_action_decider.py decider.py
cp voice_profiles.py profiles.py
cd ..
```

Update all internal voice imports to use the new short names. Update any outside
references in `discord_bot.py` from `voice.rust_voice_bridge` → `voice.bridge`, etc.

Add to `voice/__init__.py`:
```python
"""Serin voice subsystem — Rust bridge, VAD, transcription, TTS output."""
from voice.bridge import RustVoiceBridge
from voice.listener import VoiceListener
from voice.output import VoiceOutputManager
from voice.processor import AudioStreamProcessor

__all__ = ["RustVoiceBridge", "VoiceListener", "VoiceOutputManager", "AudioStreamProcessor"]
```

#### Sub-task 2.2f — serin/models/ (rename within existing package)

```bash
cd models
cp model_factory.py factory.py
cp model_interface.py interface.py
cp model_adapter.py adapter.py
cp vllm_connector.py vllm.py
cp lm_studio_connector.py lm_studio.py
cp sglang_connector.py sglang.py
cd ..
```

Update factory.py to import from new short names. Add to `models/__init__.py`:
```python
"""Serin model layer — LLM connectors, adapter, factory."""
from models.factory import get_model_connector
from models.interface import ModelInterface

__all__ = ["get_model_connector", "ModelInterface"]
```

#### Sub-task 2.2g — serin/utils/

```bash
cp background_processor.py serin/utils/background.py
cp passive_monitor.py serin/utils/passive_monitor.py
cp thinking_filter.py serin/utils/thinking_filter.py
cp debug_logger.py serin/utils/debug_logger.py
cp database_protector.py serin/utils/database_protector.py
```

#### Sub-task 2.2h — serin/control_panel/

```bash
cp web_server.py serin/control_panel/server.py
cp enhanced_api_routes.py serin/control_panel/routes.py
```

### Task 2.3 — Update discord_bot.py imports

`discord_bot.py` is the entry point and imports almost everything. Update it to use
the new package paths. Do a full read of the file first, then update every import.

Example pattern:
```python
# BEFORE
from enhanced_message_manager import EnhancedMessageManagerV3
from voice.rust_voice_bridge import RustVoiceBridge
from qdrant_memory_system import QdrantMemorySystem
from logger_config import logger
from config import config

# AFTER
from serin.messaging.manager import EnhancedMessageManagerV3
from voice.bridge import RustVoiceBridge
from serin.memory.qdrant import QdrantMemorySystem
from serin.core.logger import logger
from serin.core.config import config
```

Do this for EVERY import in discord_bot.py. Do not leave old-style imports.

### Task 2.4 — Full import verification pass

```bash
python -c "
packages = [
    'serin.core.config',
    'serin.core.logger',
    'serin.memory.qdrant',
    'serin.memory.retrieval',
    'serin.memory.context',
    'serin.messaging.manager',
    'serin.messaging.response_generator',
    'serin.personality.bot_personality',
    'voice.bridge',
    'voice.processor',
    'voice.output',
    'models.factory',
    'serin.utils.background',
    'serin.control_panel.server',
]
for pkg in packages:
    try:
        __import__(pkg)
        print(f'OK: {pkg}')
    except Exception as e:
        print(f'FAIL: {pkg} — {e}')
"
```

Fix every FAIL before continuing.

### Task 2.5 — Keep the old files as shims temporarily

For every file you moved (not the dead ones), replace the original with a one-line
deprecation shim. This prevents any code you might have missed from breaking silently:

```python
# Example: old qdrant_memory_system.py becomes:
"""
DEPRECATED: This module has moved to serin.memory.qdrant.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.memory.qdrant import *  # noqa
from serin.memory.qdrant import QdrantMemorySystem  # explicit
import warnings
warnings.warn(
    "qdrant_memory_system is deprecated. Use serin.memory.qdrant instead.",
    DeprecationWarning, stacklevel=2
)
```

### Task 2.6 — Commit Phase 2
```bash
git add -A
git commit -m "refactor: restructure into serin/ package hierarchy with proper modules"
```

---

## PHASE 3 — THE GOD OBJECT PIPELINE REFACTOR

**Goal:** Transform `enhanced_message_manager.py` (1021 lines, 15+ subsystems) into a
clean pipeline architecture. This is the highest-leverage change in the entire refactor.

**Before touching anything, read the current `serin/messaging/manager.py` completely.
Map out every logical step that `process_message()` does.**

### Task 3.1 — Define MessageContext

Create `serin/messaging/context.py` (not to be confused with memory context):

```python
"""
serin.messaging.context
-----------------------
MessageContext is the data envelope that flows through the message pipeline.
Every stage reads from it and writes to it. No stage has side effects
outside of what it writes into the context.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import discord


@dataclass
class MessageContext:
    # ── Input (set at pipeline entry, never mutated) ──────────────────────────
    message: discord.Message
    user_id: str
    username: str
    channel_id: str
    guild_id: str | None
    raw_content: str

    # ── Decision ──────────────────────────────────────────────────────────────
    should_respond: bool = False
    halt_reason: str = ""        # non-empty = pipeline halted early

    # ── Memory retrieval ──────────────────────────────────────────────────────
    memories: list[dict] = field(default_factory=list)
    recent_messages: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)

    # ── Temporal / context ────────────────────────────────────────────────────
    temporal_refs: list[str] = field(default_factory=list)
    personality_context: str = ""
    tone_modifier: str = ""

    # ── Prompt assembly ───────────────────────────────────────────────────────
    system_prompt: str = ""
    context_block: str = ""
    built_messages: list[dict] = field(default_factory=list)  # [{role, content}]

    # ── LLM response ──────────────────────────────────────────────────────────
    raw_response: str = ""
    final_response: str = ""

    # ── Observability ─────────────────────────────────────────────────────────
    stage_timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)  # catch-all for stage extras
```

### Task 3.2 — Define PipelineStage base class

Create `serin/messaging/stages/__init__.py`:

```python
"""
serin.messaging.stages
----------------------
Each stage in the message pipeline. Stages are:
- Stateless with respect to MessageContext (they read + write ctx, nothing else)
- Independently instantiable
- Independently testable

Stages signal early exit by setting ctx.halt_reason to a non-empty string.
They do NOT raise exceptions for expected early exits (e.g. "should not respond").
They DO raise exceptions for unexpected failures (handled by the pipeline runner).
"""
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from serin.messaging.context import MessageContext


class PipelineStage(ABC):
    """Base class for all message pipeline stages."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def run(self, ctx: MessageContext) -> MessageContext:
        start = time.perf_counter()
        ctx = await self._run(ctx)
        ctx.stage_timings[self.name] = round((time.perf_counter() - start) * 1000, 2)
        return ctx

    @abstractmethod
    async def _run(self, ctx: MessageContext) -> MessageContext:
        """Implement the stage logic here."""
        ...
```

### Task 3.3 — Extract each stage into its own file

Create `serin/messaging/stages/` directory. For each stage below, extract the
corresponding logic from `serin/messaging/manager.py` into its own file.

**DO NOT change what the logic does. Copy it. Clean up the code style. Nothing else.**

#### Stage 1: `serin/messaging/stages/decision.py`
Extracts: `_should_respond()` logic from the manager.
What it does: checks ResponseController, rate limits, mention detection, DM handling.
Sets: `ctx.should_respond = True/False`, `ctx.halt_reason` if not responding.

```python
"""
ResponseDecisionStage
---------------------
Decides whether Serin should respond to this message at all.
Sets ctx.should_respond. If False, sets ctx.halt_reason and pipeline halts.
"""
from serin.messaging.stages import PipelineStage
from serin.messaging.context import MessageContext
from serin.core.logger import logger


class ResponseDecisionStage(PipelineStage):
    def __init__(self, response_controller):
        self.controller = response_controller

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # [EXTRACT LOGIC FROM manager._should_respond() HERE]
        # Set ctx.should_respond = True or False
        # If False: set ctx.halt_reason = "rate_limited" / "not_mentioned" / etc.
        logger.debug("pipeline.decision", extra={
            "user": ctx.username,
            "channel_id": ctx.channel_id,
            "decision": ctx.should_respond,
            "reason": ctx.halt_reason or "will_respond",
        })
        return ctx
```

#### Stage 2: `serin/messaging/stages/memory_retrieval.py`
Extracts: memory search portion of `_build_context()`.
Sets: `ctx.memories`, `ctx.recent_messages`, `ctx.user_profile`.

#### Stage 3: `serin/messaging/stages/temporal.py`
Extracts: `TemporalContext.resolve_dates()` call from `_build_context()`.
Sets: `ctx.temporal_refs`.

#### Stage 4: `serin/messaging/stages/personality.py`
Extracts: `_get_tone_modifier()` and personality context building.
Sets: `ctx.personality_context`, `ctx.tone_modifier`.

#### Stage 5: `serin/messaging/stages/prompt_assembly.py`
Extracts: prompt construction — system message + context block + message history.
Sets: `ctx.system_prompt`, `ctx.context_block`, `ctx.built_messages`.

#### Stage 6: `serin/messaging/stages/llm_call.py`
Extracts: `get_response_natural()` invocation.
Sets: `ctx.raw_response`.

```python
"""
LLMCallStage
------------
Calls the LLM with the assembled prompt. Sets ctx.raw_response.
This is the most expensive stage — always check timings here.
"""
from serin.messaging.stages import PipelineStage
from serin.messaging.context import MessageContext
from serin.core.logger import logger


class LLMCallStage(PipelineStage):
    def __init__(self, response_generator):
        self.generator = response_generator

    async def _run(self, ctx: MessageContext) -> MessageContext:
        ctx.raw_response = await self.generator.get_response_natural(
            messages=ctx.built_messages,
            tone_modifier=ctx.tone_modifier,
        )
        logger.info("pipeline.llm_response", extra={
            "user": ctx.username,
            "response_len": len(ctx.raw_response),
            "duration_ms": ctx.stage_timings.get("LLMCallStage"),
        })
        return ctx
```

#### Stage 7: `serin/messaging/stages/response_cleaning.py`
Extracts: thinking filter, contraction application, natural variations, fillers.
Sets: `ctx.final_response`.

#### Stage 8: `serin/messaging/stages/send.py`
Extracts: `send_with_typing()` — typing delay calculation, channel.typing(), channel.send().
After send: sets `ctx.metadata["message_sent"] = True`.

#### Stage 9: `serin/messaging/stages/memory_write.py`
Extracts: `memory_system.add_memory()` call after response.
Writes the interaction to Qdrant.

### Task 3.4 — Build the pipeline runner

Create `serin/messaging/pipeline.py`:

```python
"""
serin.messaging.pipeline
------------------------
MessagePipeline is the entry point for all text message processing.
It runs stages in order, passing MessageContext through each.

Stages signal early exit via ctx.halt_reason (non-empty string).
Unexpected exceptions are caught, logged, and halt the pipeline.

Usage:
    pipeline = MessagePipeline.build(memory_system, model, personality, ...)
    ctx = MessageContext(message=msg, ...)
    ctx = await pipeline.process(ctx)
"""
from __future__ import annotations
import discord
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage
from serin.core.logger import logger


class MessagePipeline:
    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    @classmethod
    def build(cls, *, response_controller, memory_system, retrieval,
              personality, temporal_context, response_generator,
              thinking_filter, mention_translator) -> "MessagePipeline":
        """
        Factory method — wires all dependencies into stages.
        Call this once at bot startup. Keep the instance for the bot's lifetime.
        """
        from serin.messaging.stages.decision import ResponseDecisionStage
        from serin.messaging.stages.memory_retrieval import MemoryRetrievalStage
        from serin.messaging.stages.temporal import TemporalStage
        from serin.messaging.stages.personality import PersonalityStage
        from serin.messaging.stages.prompt_assembly import PromptAssemblyStage
        from serin.messaging.stages.llm_call import LLMCallStage
        from serin.messaging.stages.response_cleaning import ResponseCleaningStage
        from serin.messaging.stages.send import SendStage
        from serin.messaging.stages.memory_write import MemoryWriteStage

        return cls(stages=[
            ResponseDecisionStage(response_controller),
            MemoryRetrievalStage(memory_system, retrieval),
            TemporalStage(temporal_context),
            PersonalityStage(personality),
            PromptAssemblyStage(mention_translator),
            LLMCallStage(response_generator),
            ResponseCleaningStage(thinking_filter),
            SendStage(),
            MemoryWriteStage(memory_system),
        ])

    async def process(self, ctx: MessageContext) -> MessageContext:
        logger.info("pipeline.start", extra={
            "user": ctx.username,
            "channel_id": ctx.channel_id,
            "content_preview": ctx.raw_content[:60],
        })

        for stage in self.stages:
            try:
                ctx = await stage.run(ctx)
            except Exception as e:
                logger.error(f"pipeline.stage_error", extra={
                    "stage": stage.name,
                    "user": ctx.username,
                    "error": str(e),
                }, exc_info=True)
                ctx.halt_reason = f"stage_error:{stage.name}"
                break

            if ctx.halt_reason:
                logger.debug("pipeline.halted", extra={
                    "stage": stage.name,
                    "reason": ctx.halt_reason,
                })
                break

        logger.info("pipeline.complete", extra={
            "user": ctx.username,
            "responded": bool(ctx.final_response),
            "halt_reason": ctx.halt_reason or None,
            "total_ms": sum(ctx.stage_timings.values()),
            "stage_timings": ctx.stage_timings,
        })
        return ctx
```

### Task 3.5 — Update discord_bot.py to use the pipeline

In `discord_bot.py`, replace the call to `message_manager.process_message(message)`
with:

```python
# In on_ready, build the pipeline once:
pipeline = MessagePipeline.build(
    response_controller=response_controller,
    memory_system=memory_system,
    retrieval=enhanced_retrieval,
    personality=bot_personality,
    temporal_context=temporal_ctx,
    response_generator=response_gen,
    thinking_filter=thinking_filter,
    mention_translator=mention_translator,
)

# In on_message:
ctx = MessageContext(
    message=message,
    user_id=str(message.author.id),
    username=message.author.display_name,
    channel_id=str(message.channel.id),
    guild_id=str(message.guild.id) if message.guild else None,
    raw_content=message.content,
)
await pipeline.process(ctx)
```

### Task 3.6 — Smoke test the pipeline

The bot should respond to messages identically. If you can run it:
```bash
LOG_LEVEL=DEBUG python discord_bot.py
```

Look for these log lines to confirm the pipeline is running:
```
pipeline.start user=... channel_id=...
pipeline.complete responded=True total_ms=...
```

If you can't run the live bot, at minimum verify:
```bash
python -c "
from serin.messaging.pipeline import MessagePipeline
from serin.messaging.context import MessageContext
print('Pipeline imports OK')
print('Stages:', [s.__class__.__name__ for s in MessagePipeline.__dict__])
"
```

### Task 3.7 — Keep the old manager.py as a thin wrapper

Replace `serin/messaging/manager.py` with a compatibility shim that delegates to
the pipeline. This way any code that still calls `message_manager.process_message()`
continues to work:

```python
"""
serin.messaging.manager
-----------------------
COMPATIBILITY SHIM: EnhancedMessageManagerV3 now delegates to MessagePipeline.
This class exists so old call sites in discord_bot.py continue to work.
New code should use MessagePipeline directly.
"""
import warnings
from serin.messaging.pipeline import MessagePipeline
from serin.messaging.context import MessageContext

class EnhancedMessageManagerV3:
    """Thin wrapper around MessagePipeline for backwards compatibility."""

    def __init__(self, pipeline: MessagePipeline):
        self.pipeline = pipeline

    async def process_message(self, message) -> None:
        ctx = MessageContext(
            message=message,
            user_id=str(message.author.id),
            username=message.author.display_name,
            channel_id=str(message.channel.id),
            guild_id=str(message.guild.id) if message.guild else None,
            raw_content=message.content,
        )
        await self.pipeline.process(ctx)
```

### Task 3.8 — Commit Phase 3
```bash
git add -A
git commit -m "refactor(messaging): extract god object into MessagePipeline + 9 stages"
```

---

## PHASE 4 — LOGGING STANDARDIZATION

**Goal:** Every log line must answer: WHAT happened, WHO triggered it, WHERE in the
system, OUTCOME (success/failure/degraded), and HOW LONG it took for anything >10ms.

### Task 4.1 — Audit current logging patterns

Before standardizing, understand what exists:
```bash
grep -r "logger\." --include="*.py" . | grep -v "shim\|deprecated\|__pycache__" | wc -l
grep -r "logger\.debug\|logger\.info\|logger\.warning\|logger\.error" --include="*.py" . | head -30
```

### Task 4.2 — Define log event naming convention

Establish this convention — document it in `docs/LOGGING.md`:

```markdown
# Serin Logging Convention

## Format: {component}.{event}

Examples:
- pipeline.start
- pipeline.stage_error
- memory.search_complete
- memory.write_failed
- voice.process_died
- voice.tts_sent
- llm.call_start
- llm.call_complete
- llm.fallback_used

## Required extra fields by level:

DEBUG: whatever helps trace the specific item
INFO:  user (or guild_id), channel_id, outcome, duration_ms for >10ms ops
WARNING: same as INFO + degradation_reason
ERROR: same as WARNING + exc_info=True always
CRITICAL: everything + requires_intervention=True

## Level rules:
DEBUG   — per-chunk audio, individual memory hits, token counts, stage internals
INFO    — user-visible actions: message sent, memory stored, voice session events
WARNING — degraded operation: Qdrant slow, fallback used, lock timeout, retries
ERROR   — subsystem failure: LLM down, Rust crash, embedding failed
CRITICAL — bot cannot operate without intervention
```

### Task 4.3 — Standardize logs in each package

Go through each package and update log calls. This is mechanical work.

**Pattern to apply everywhere:**

```python
# BEFORE (bad — no context, no timing, hard to filter):
logger.info(f"Got response for {user}: {response[:50]}")
logger.error("Memory search failed")

# AFTER (good — structured, filterable, contextual):
logger.info("pipeline.response_sent", extra={
    "user": ctx.username,
    "user_id": ctx.user_id,
    "channel_id": ctx.channel_id,
    "response_len": len(response),
    "duration_ms": elapsed_ms,
})
logger.error("memory.search_failed", extra={
    "user_id": user_id,
    "query_preview": query[:50],
    "error": str(e),
}, exc_info=True)
```

Apply to these files in priority order:
1. `serin/messaging/stages/*.py` — all pipeline stages (already structured in Phase 3)
2. `serin/memory/qdrant.py` — every search, write, dedup operation
3. `voice/bridge.py` — Rust process events, audio chunks, TTS sends
4. `voice/processor.py` — VAD decisions, buffer events, lock acquire/release
5. `serin/core/logger.py` — ensure the formatter outputs `extra` fields as JSON
6. `discord_bot.py` — startup sequence, subsystem init, error handlers

### Task 4.4 — Ensure the logger outputs structured fields

Read `serin/core/logger.py` and verify the JSON formatter includes `extra` dict fields.
If it doesn't, add it:

```python
class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Include any extra= fields passed by the caller
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith('_'):
                base[key] = val
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)
```

### Task 4.5 — Add startup banner

In `discord_bot.py` at the very start of `on_ready`:

```python
logger.info("serin.startup", extra={
    "version": "1.0.0",  # or read from pyproject.toml
    "voice_enabled": config.ENABLE_VOICE,
    "tts_enabled": config.ENABLE_TTS,
    "voice_mode": config.VOICE_RECEIVER_MODE,
    "llm_model": config.LLM_MODEL,
    "allowed_channels": len(config.ALLOWED_CHANNEL_IDS),
    "qdrant_host": config.QDRANT_HOST,
})
```

### Task 4.6 — Commit Phase 4
```bash
git add -A
git commit -m "feat(logging): standardize structured logging across all subsystems"
```

---

## PHASE 5 — CODE QUALITY PASS

**Goal:** Every file in the new package structure should meet a consistent quality bar.
This is NOT a rewrite — it's applying consistent style to existing logic.

### Task 5.1 — Add module docstrings everywhere

Every `.py` file should start with a module docstring that answers:
- What does this module own?
- What is its single responsibility?
- What are the key classes/functions?

Template:
```python
"""
serin.memory.qdrant
-------------------
QdrantMemorySystem: owns all Qdrant vector database operations for Serin.

Responsibilities:
- Store memories as 384-dim vectors (all-MiniLM-L6-v2)
- Hybrid search: BM25 keyword (SQLite FTS5) + semantic vector (Qdrant)
- User profile CRUD (SQLite)
- Relationship tracking (SQLite)
- Background job queue for summarization

Does NOT own:
- Context formatting (see serin.memory.context)
- Retrieval orchestration (see serin.memory.retrieval)

Key classes:
- QdrantMemorySystem: main class, instantiate once at startup
- SQLiteBM25Index: internal helper for FTS5 keyword search
"""
```

Do this for every file in: `serin/`, `voice/`, `models/`.

### Task 5.2 — Add type hints to all public method signatures

Read each file and add type annotations to any public method that lacks them.
Focus on: method parameters, return types. Do NOT annotate private internals.

```python
# BEFORE:
async def search_hybrid(self, query, user_id, n_results, **kwargs):

# AFTER:
async def search_hybrid(
    self,
    query: str,
    user_id: str,
    n_results: int = 10,
    channel_id: str | None = None,
    time_range_days: int | None = None,
) -> list[dict]:
```

### Task 5.3 — Extract magic numbers into named constants

Search for hardcoded numbers that have no explanation:
```bash
grep -rn "150\|1\.5\|192000\|5760000\|50000000\|400\|30000\|8081" --include="*.py" serin/ voice/ models/
```

For each magic number found, extract it to a named constant at the top of the file:

```python
# voice/processor.py
VAD_AMPLITUDE_THRESHOLD = 150          # RMS amplitude below which is considered silence
SILENCE_FRAMES_BEFORE_FLUSH = 75       # 1.5s at 50 frames/sec
MIN_BUFFER_BYTES = 192_000             # ~1 second of 48kHz stereo PCM
MAX_BUFFER_BYTES_GEMMA = 5_760_000     # ~30 seconds (Gemma audio limit)
MAX_BUFFER_BYTES_WHISPER = 50_000_000  # ~260 seconds (Whisper limit)
PROCESSING_LOCK_SECONDS = 30           # How long to lock after queueing audio
VOICE_BURST_IGNORE_FRAMES = 25         # Ignore bursts shorter than 0.5s
```

```python
# serin/messaging/response_generator.py
MAX_RESPONSE_CHARS = 400               # Truncate LLM responses beyond this
MAX_CONTEXT_MESSAGES = 8              # Recent messages sent to LLM
```

### Task 5.4 — Fix the PCM buffer overflow bug (from audit item #7)

This IS a logic fix but it's a data safety issue and small enough to do here.

In `voice/processor.py`, in `process_audio_chunk()`, add a buffer cap:

```python
# After: user_buffers[user_id].extend(pcm_chunk)
# Add:
if len(user_buffers[user_id]) >= MAX_BUFFER_BYTES_WHISPER:
    logger.warning("voice.buffer_overflow_forced_flush", extra={
        "user_id": user_id,
        "buffer_bytes": len(user_buffers[user_id]),
        "limit": MAX_BUFFER_BYTES_WHISPER,
    })
    await self._queue_for_transcription(user_id, guild_id, channel_id, username)
    return
```

Note this in CHANGES_DEFERRED.md as a completed safety fix.

### Task 5.5 — Fix the zero-embedding fallback (audit item #9)

In `serin/memory/qdrant.py`, find the zero-embedding fallback and change it
from silent degradation to a logged failure that skips the write:

```python
# BEFORE: creates zero vectors that poison search
# AFTER:
try:
    vector = self.embedding_model.encode(text).tolist()
except Exception as e:
    logger.error("memory.embedding_failed_skipping_write", extra={
        "error": str(e),
        "content_preview": text[:50],
    }, exc_info=True)
    return None  # Do not write garbage to Qdrant
```

### Task 5.6 — Commit Phase 5
```bash
git add -A
git commit -m "chore(quality): docstrings, type hints, magic number constants, safety fixes"
```

---

## PHASE 6 — TESTS

**Goal:** The tests/ directory should give confidence that the core pipeline works.
Focus on unit tests for the pipeline stages — these are the new, highest-value tests.

### Task 6.1 — Set up tests/ structure

```bash
mkdir -p tests/messaging/stages
mkdir -p tests/memory
mkdir -p tests/voice
touch tests/__init__.py
touch tests/messaging/__init__.py
touch tests/messaging/stages/__init__.py
touch tests/memory/__init__.py
touch tests/voice/__init__.py
```

Create `tests/conftest.py`:
```python
"""
Shared pytest fixtures for Serin tests.
"""
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from serin.messaging.context import MessageContext


@pytest.fixture
def mock_message():
    """A minimal discord.Message mock."""
    msg = MagicMock(spec=discord.Message)
    msg.author.id = 12345
    msg.author.display_name = "TestUser"
    msg.channel.id = 67890
    msg.guild.id = 11111
    msg.content = "hey serin what's up"
    return msg


@pytest.fixture
def base_context(mock_message):
    """A MessageContext with sensible defaults for testing."""
    return MessageContext(
        message=mock_message,
        user_id="12345",
        username="TestUser",
        channel_id="67890",
        guild_id="11111",
        raw_content="hey serin what's up",
    )
```

### Task 6.2 — Write pipeline stage unit tests

Create `tests/messaging/stages/test_decision.py`:
```python
"""Tests for ResponseDecisionStage."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from serin.messaging.stages.decision import ResponseDecisionStage
from serin.messaging.context import MessageContext


@pytest.mark.asyncio
async def test_responds_when_mentioned(base_context):
    controller = MagicMock()
    controller.should_respond = MagicMock(return_value=True)
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is True
    assert ctx.halt_reason == ""


@pytest.mark.asyncio
async def test_halts_when_rate_limited(base_context):
    controller = MagicMock()
    controller.should_respond = MagicMock(return_value=False)
    controller.last_reject_reason = "rate_limited"
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is False
    assert ctx.halt_reason != ""


@pytest.mark.asyncio
async def test_stage_timing_recorded(base_context):
    controller = MagicMock()
    controller.should_respond = MagicMock(return_value=True)
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert "ResponseDecisionStage" in ctx.stage_timings
    assert ctx.stage_timings["ResponseDecisionStage"] >= 0
```

Create `tests/messaging/stages/test_pipeline.py`:
```python
"""Integration test for the full MessagePipeline."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from serin.messaging.pipeline import MessagePipeline
from serin.messaging.context import MessageContext


@pytest.mark.asyncio
async def test_pipeline_halts_on_no_respond(base_context):
    """If ResponseDecisionStage sets halt_reason, later stages don't run."""
    # Create a pipeline where decision stage says no
    decision_stage = MagicMock()
    async def halting_run(ctx):
        ctx.should_respond = False
        ctx.halt_reason = "rate_limited"
        ctx.stage_timings["MockDecision"] = 0.1
        return ctx
    decision_stage.run = halting_run
    decision_stage.name = "MockDecision"

    memory_stage = MagicMock()
    memory_stage.run = AsyncMock()

    pipeline = MessagePipeline(stages=[decision_stage, memory_stage])
    ctx = await pipeline.process(base_context)

    assert ctx.halt_reason == "rate_limited"
    memory_stage.run.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_records_all_stage_timings(base_context):
    """All stages should record their timing."""
    from serin.messaging.stages import PipelineStage

    class FastStage(PipelineStage):
        async def _run(self, ctx):
            return ctx

    pipeline = MessagePipeline(stages=[FastStage(), FastStage()])
    ctx = await pipeline.process(base_context)
    assert len(ctx.stage_timings) == 2
```

Create `tests/memory/test_qdrant.py`:
```python
"""
Tests for QdrantMemorySystem.
These tests mock Qdrant and SQLite — they test our logic, not the external services.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.mark.asyncio
async def test_add_memory_skips_on_embedding_failure():
    """If embedding fails, memory write should be skipped, not written with zeros."""
    with patch("serin.memory.qdrant.SentenceTransformer") as mock_st:
        mock_st.return_value.encode.side_effect = RuntimeError("Model not loaded")
        from serin.memory.qdrant import QdrantMemorySystem
        # Should not raise, but should log and return None
        # (exact assertion depends on your implementation)
```

### Task 6.3 — Write a voice pipeline smoke test

Create `tests/voice/test_processor.py`:
```python
"""Tests for AudioStreamProcessor VAD logic."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np


def make_pcm_bytes(amplitude: int, frames: int = 50) -> bytes:
    """Create fake PCM data with given RMS amplitude."""
    samples = np.full(frames * 960, amplitude, dtype=np.int16)
    return samples.tobytes()


@pytest.mark.asyncio
async def test_silent_audio_does_not_queue():
    """Audio below VAD threshold should not queue for transcription."""
    with patch("voice.processor.AudioStreamProcessor._queue_for_transcription") as mock_q:
        from voice.processor import AudioStreamProcessor
        processor = AudioStreamProcessor()
        silent_pcm = make_pcm_bytes(amplitude=10)  # below threshold of 150
        await processor.process_audio_chunk(
            user_id="123", username="test", guild_id="456",
            channel_id="789", pcm_data=silent_pcm
        )
        mock_q.assert_not_called()
```

### Task 6.4 — Run the test suite

```bash
pip install pytest pytest-asyncio
pytest tests/ -v --tb=short 2>&1 | head -60
```

Fix any failures. If a test requires a live Qdrant or Discord connection to run,
add a `@pytest.mark.integration` marker and skip it in the default run:
```bash
pytest tests/ -v -m "not integration"
```

### Task 6.5 — Commit Phase 6
```bash
git add -A
git commit -m "test: add pipeline stage unit tests + memory + voice smoke tests"
```

---

## PHASE 7 — FINAL CLEANUP + DOCUMENTATION

### Task 7.1 — Remove deprecation shims from old root files

Now that imports are updated everywhere and tests pass, remove the old files at root
that became shims. Replace them with a single `MOVED.md` at root:

```markdown
# Module Locations

These root-level files have moved to the serin/ package:

| Old location | New location |
|---|---|
| config.py | serin/core/config.py |
| logger_config.py | serin/core/logger.py |
| qdrant_memory_system.py | serin/memory/qdrant.py |
| enhanced_memory_retrieval.py | serin/memory/retrieval.py |
| enhanced_message_manager.py | serin/messaging/manager.py |
| natural_response_generator.py | serin/messaging/response_generator.py |
| web_server.py | serin/control_panel/server.py |
| ... | ... |
```

### Task 7.2 — Update README.md

The README currently describes an older structure. Update the Project Structure section
to reflect the new package layout. Add a "Architecture" section:

```markdown
## Architecture

Serin is organized as a pipeline:

```
Discord Event
     │
     ▼
MessagePipeline (serin/messaging/pipeline.py)
     │
     ├── ResponseDecisionStage   — should Serin respond?
     ├── MemoryRetrievalStage    — fetch relevant memories from Qdrant
     ├── TemporalStage           — resolve time references
     ├── PersonalityStage        — inject tone + traits
     ├── PromptAssemblyStage     — build LLM prompt
     ├── LLMCallStage            — call the model
     ├── ResponseCleaningStage   — filter + naturalize response
     ├── SendStage               — type + send to Discord
     └── MemoryWriteStage        — store interaction in Qdrant
```

Each stage is in `serin/messaging/stages/`. Adding behavior = adding/modifying one stage.
```

### Task 7.3 — Write ARCHITECTURE.md

Create `docs/ARCHITECTURE.md` — this is the document a new developer or AI reads first:

```markdown
# Serin Architecture

## System Overview

Serin is a Discord AI companion with voice support. It runs as a single Python
process (asyncio) with a companion Rust subprocess for voice handling.

## Package Map

| Package | Owns |
|---|---|
| serin/core/ | Config, logging — imported by everything |
| serin/memory/ | Qdrant vector store, BM25 index, hybrid search |
| serin/messaging/ | Message pipeline — all text response logic |
| serin/personality/ | Personality traits, conversation mood |
| serin/models/ | LLM connectors (vLLM, LM Studio, SGLang) |
| serin/utils/ | Background jobs, passive monitor, database protector |
| serin/control_panel/ | Flask web dashboard |
| voice/ | Voice: Rust bridge, VAD, TTS, transcription |
| serin_core/ | PyO3 Rust module: text processing utilities |

## Data Flow: Text Message

1. `discord_bot.py:on_message()` receives Discord event
2. `serin/utils/passive_monitor.py` may write to memory (observation)
3. `MessagePipeline.process(ctx)` runs 9 stages in sequence
4. Response sent; interaction stored in Qdrant

## Data Flow: Voice Message

1. Discord sends encrypted Opus → Rust subprocess decrypts → PCM to stdout
2. `voice/bridge.py` reads PCM → `voice/processor.py` runs VAD
3. After 1.5s silence: audio queued → transcribed (Whisper or Gemma)
4. Transcript enters `voice/pipeline.py` → same LLM path as text
5. TTS: Edge-TTS → WAV → Rust subprocess plays in voice channel

## Key Design Decisions

### Why Rust for voice?
Discord uses DAVE encryption for voice since 2024. No Python library handles it.
The Rust subprocess uses vendored songbird 0.6.0 with a custom DAVE patch.

### Why subprocess IPC instead of FFI?
Safer crash isolation. If the Rust voice process dies, Python keeps running
(albeit without voice). FFI panics kill the whole process.

### Why a pipeline for messaging?
The original god object (`enhanced_message_manager.py`, 1021 lines) made every
change risky. The pipeline makes stages independently testable and replaceable.

### Why Qdrant + BM25 hybrid search?
Neither alone is sufficient. BM25 is great for keyword matches ("that thing we
discussed about Python") but bad for semantic similarity. Qdrant vectors capture
meaning but miss exact keywords. Hybrid gives both.

## Adding a Feature

### New pipeline behavior:
Add a `PipelineStage` subclass in `serin/messaging/stages/yourfeature.py`.
Insert it into `MessagePipeline.build()` in the right position.

### New memory type:
Add to `serin/memory/qdrant.py`. Follow existing `add_memory_enhanced()` pattern.

### New LLM provider:
Add a connector in `models/`. Implement `ModelInterface`. Register in `models/factory.py`.

### New voice feature:
Modify `voice/processor.py` (VAD/buffering) or `voice/pipeline.py` (post-transcription).
```

### Task 7.4 — Final verification

```bash
# All imports work
python -c "
import serin.core.config
import serin.core.logger
import serin.memory.qdrant
import serin.memory.retrieval
import serin.messaging.pipeline
import serin.messaging.context
import serin.personality.bot_personality
import voice.bridge
import voice.processor
import models.factory
import serin.control_panel.server
print('ALL IMPORTS OK')
"

# Tests pass
pytest tests/ -v -m "not integration" 2>&1 | tail -20

# No obvious dead imports in discord_bot.py
python -c "import discord_bot" 2>&1 | grep -i "error\|warning" | head -10
```

### Task 7.5 — Update PROGRESS.md to mark complete

```markdown
# Serin Refactor Progress

## Status: COMPLETE ✓
## All phases completed.

## What was done:
- Phase 0: Reconnaissance — read all key files, confirmed dead code
- Phase 1: Root cleanup — moved docs, deleted dead files, moved tests
- Phase 2: Package restructure — flat files → serin/ package hierarchy
- Phase 3: God object → MessagePipeline with 9 stages
- Phase 4: Structured logging across all subsystems
- Phase 5: Type hints, docstrings, magic number constants, safety fixes
- Phase 6: Unit tests for pipeline stages
- Phase 7: Documentation + ARCHITECTURE.md

## What was deferred (see CHANGES_DEFERRED.md):
- Control panel auth (web_server.py needs API key middleware)
- Rust crash supervisor (voice/bridge.py needs process watcher)
- BM25 exception alerting (needs write-back to dead-letter store)

## Files deleted:
[list here]

## New file locations (see MOVED.md):
[list here]
```

### Task 7.6 — Final commit
```bash
git add -A
git commit -m "docs: add ARCHITECTURE.md, update README, finalize refactor"
git log --oneline | head -15
```

---

## CONTEXT MANAGEMENT INSTRUCTIONS

**Read this section carefully before you begin.**

You are working in a limited context window. This job will likely exceed one session.
Here is how to handle it:

### When context is getting full (>60% used):

1. **Write PROGRESS.md immediately** — before you forget anything.
   It must contain:
   - Exactly which task you are on (e.g. "Sub-task 2.2c in progress")
   - What you've verified works
   - What imports have been updated
   - Any surprises or deviations from the plan
   - The exact next step

2. **Commit what you have** — even if a phase isn't complete:
   ```bash
   git add -A
   git commit -m "wip: phase 2 partial — core and memory packages complete"
   ```

3. **Spawn a sub-agent for remaining work** by writing a handoff prompt:
   ```
   Continue the Serin refactor. Read PROGRESS.md first.
   The repo is at: https://github.com/AnuAnu22/Serin (or local path).
   Last completed: [exact task ID]
   Next task: [exact task ID]
   All context is in PROGRESS.md.
   ```

### If you realize something in the plan is wrong:

- Do NOT silently deviate. Write what you found and what you did instead in PROGRESS.md.
- If a file has unexpected imports that would break a planned move: note it, work around it, document it.
- If a file you planned to delete turns out to be imported: do NOT delete it, note it.

### What "done" means for each phase:

- Phase 0: PROGRESS.md exists, all key files read, dead code list confirmed
- Phase 1: Root has <15 .py files, docs/ exists, tests/ has test files
- Phase 2: `python -c "from serin.memory.qdrant import QdrantMemorySystem"` succeeds
- Phase 3: `from serin.messaging.pipeline import MessagePipeline` succeeds, stages/ has 9 files
- Phase 4: Every ERROR/WARNING log call includes `exc_info` and `extra={}` dict
- Phase 5: Every file in serin/ starts with a module docstring
- Phase 6: `pytest tests/ -m "not integration"` shows >10 tests, all pass
- Phase 7: ARCHITECTURE.md exists, README updated, PROGRESS.md says COMPLETE

---

## WHAT SUCCESS LOOKS LIKE

When you are done, a developer (or AI) should be able to:

1. **Find any behavior** by reading the package name:
   `serin/messaging/stages/memory_retrieval.py` — obviously fetches memories

2. **Add a feature** by touching ONE file:
   New pipeline behavior = new stage file + one line in `MessagePipeline.build()`

3. **Debug a bug** by reading logs:
   ```
   pipeline.stage_error stage=LLMCallStage user=Alice error=TimeoutError duration_ms=30012
   ```
   → You know immediately: LLM call timed out for Alice after 30 seconds

4. **Understand the system** in 5 minutes:
   Read `docs/ARCHITECTURE.md` → look at `serin/messaging/stages/` → done

5. **Run tests** confidently:
   `pytest tests/ -m "not integration"` → green

That is the standard. Do not stop until it is met.

---

*This prompt was written by a staff engineer who has seen what happens when you don't
do this work early. The codebase is already impressive. This makes it legendary.*
