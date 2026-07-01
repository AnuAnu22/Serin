"""Final refactor batch: root DI, TYPE_CHECKING, processor imports, check scripts, tests, hook.

Run: python3 scripts/complete_refactor.py
Then: uv run ruff check serin/ --fix
      uv run bandit -r serin/ -q
"""
from __future__ import annotations

import fnmatch
import os
import shutil

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIN = os.path.join(PROJECT, "serin")
SCRIPTS = os.path.join(PROJECT, "scripts")


def write(rel: str, content: str) -> None:
    fp = os.path.join(PROJECT, rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w") as f:
        f.write(content)
    print(f"  WROTE {rel}")


def readfile(rel: str) -> str:
    with open(os.path.join(PROJECT, rel), "r") as f:
        return f.read()


def writefile(rel: str, content: str) -> None:
    write(rel, content)


# ═══════════════════════════════════════════════════════════════════════
# 1. Root DI container
# ═══════════════════════════════════════════════════════════════════════
print("=== 1. serin/_di.py ===")
write("serin/_di.py", """\"\"\"Root DI container — holds singletons created during startup.\"\"\"
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger
    from serin.d1_1_pipeline_flow.ingest.core.manager import EnhancedMessageManagerV3
    from serin.d1_1_pipeline_flow.ingest.context.mention_translator import MentionTranslator
    from serin.d1_1_pipeline_flow.ingest.sync.crawler import MessageCrawler
    from serin.d1_1_pipeline_flow.remember.qdrant import QdrantMemorySystem

_logger: Logger | None = None
_mention_translator: MentionTranslator | None = None
_message_manager: EnhancedMessageManagerV3 | None = None
_crawler: MessageCrawler | None = None
_qdrant: QdrantMemorySystem | None = None


def init_root(
    logger: Logger,
) -> None:
    global _logger
    _logger = logger


def get_logger() -> Logger:
    if _logger is None:
        raise RuntimeError("Root not initialized")
    return _logger


def set_mention_translator(obj: MentionTranslator) -> None:
    global _mention_translator
    _mention_translator = obj


def get_mention_translator() -> MentionTranslator:
    if _mention_translator is None:
        raise RuntimeError("MentionTranslator not initialized")
    return _mention_translator


def set_message_manager(obj: EnhancedMessageManagerV3) -> None:
    global _message_manager
    _message_manager = obj


def get_message_manager() -> EnhancedMessageManagerV3:
    if _message_manager is None:
        raise RuntimeError("MessageManager not initialized")
    return _message_manager


def set_crawler(obj: MessageCrawler) -> None:
    global _crawler
    _crawler = obj


def get_crawler() -> MessageCrawler:
    if _crawler is None:
        raise RuntimeError("Crawler not initialized")
    return _crawler


def set_qdrant(obj: QdrantMemorySystem) -> None:
    global _qdrant
    _qdrant = obj


def get_qdrant() -> QdrantMemorySystem:
    if _qdrant is None:
        raise RuntimeError("Qdrant not initialized")
    return _qdrant
""")

# ═══════════════════════════════════════════════════════════════════════
# 2. Update bot.py — TYPE_CHECKING for pipeline types, MentionTranslator via DI
# ═══════════════════════════════════════════════════════════════════════
print("=== 2. bot.py ===")
BOT_PATH = "serin/d1_2_gateway_io/discord/bot.py"
bot_content = readfile(BOT_PATH)

# Replace imports:
# Remove pipeline imports and add TYPE_CHECKING
old_bot_imports = """from serin.d1_1_pipeline_flow.ingest.context.mention_translator import MentionTranslator
from serin.d1_1_pipeline_flow.ingest.core.manager import EnhancedMessageManagerV3
from serin.d1_1_pipeline_flow.ingest.sync.crawler import MessageCrawler
from serin.d1_2_gateway_io._di import get_logger"""

new_bot_imports = """from __future__ import annotations

from typing import TYPE_CHECKING

from serin.d1_2_gateway_io._di import get_logger
from serin._di import get_mention_translator

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.ingest.core.manager import EnhancedMessageManagerV3
    from serin.d1_1_pipeline_flow.ingest.sync.crawler import MessageCrawler
    from serin.d1_1_pipeline_flow.ingest.context.mention_translator import MentionTranslator"""

bot_content = bot_content.replace(old_bot_imports, new_bot_imports)

# Replace mention_translator = MentionTranslator(client) with DI version
bot_content = bot_content.replace(
    "mention_translator = MentionTranslator(client)",
    "mention_translator = get_mention_translator()"
)

# Remove the duplicate `from __future__ import annotations` if any
# (the original might not have it, but after our edit, it might appear twice)
lines = bot_content.split("\n")
seen_future = False
new_lines = []
for line in lines:
    if line.strip() == 'from __future__ import annotations':
        if seen_future:
            continue
        seen_future = True
    new_lines.append(line)
bot_content = "\n".join(new_lines)

# Move db_protect imports under TYPE_CHECKING too (they're only used in annotations/variable types)
# Actually DatabaseProtector, DatabaseRecoveryError, DatabaseValidationError, get_database_protector
# are used at RUNTIME (lines ~120-157). So keep them.
# But DatabaseProtector is only for the type annotation at line 121? No, db_protector = DatabaseProtector("./bot_data")
# is a runtime instantiation.

writefile(BOT_PATH, bot_content)
print("  UPDATED bot.py")

# ═══════════════════════════════════════════════════════════════════════
# 3. Update bot_pipeline_init.py — fix processor.py imports
# ═══════════════════════════════════════════════════════════════════════
print("=== 3. bot_pipeline_init.py ===")
INIT_PATH = "serin/d1_2_gateway_io/discord/bot_pipeline_init.py"
init_content = readfile(INIT_PATH)

# Fix processor.py lazy import (line ~141 in the function body)
init_content = init_content.replace(
    "from serin.d1_2_gateway_io.voice_system.processor import (\n"
    "                AudioStreamProcessor,\n"
    "                VoiceBehaviorManager,\n"
    "            )",
    "from serin.d1_2_gateway_io.voice_system.audio.process.audio_processor import (\n"
    "                AudioStreamProcessor,\n"
    "            )\n"
    "            from serin.d1_2_gateway_io.voice_system.audio.process.voice_behavior import (\n"
    "                VoiceBehaviorManager,\n"
    "            )"
)

# Fix second processor.py import (voice behavior manager section, line ~235)
init_content = init_content.replace(
    "from serin.d1_2_gateway_io.voice_system.processor import (\n"
    "                VoiceBehaviorManager,\n"
    "            )",
    "from serin.d1_2_gateway_io.voice_system.audio.process.voice_behavior import (\n"
    "                VoiceBehaviorManager,\n"
    "            )"
)

writefile(INIT_PATH, init_content)
print("  UPDATED bot_pipeline_init.py")

# ═══════════════════════════════════════════════════════════════════════
# 4. Create scripts/law/ check scripts
# ═══════════════════════════════════════════════════════════════════════
print("=== 4. scripts/law/ ===")
os.makedirs(os.path.join(SCRIPTS, "law"), exist_ok=True)
init_law = os.path.join(SCRIPTS, "law", "__init__.py")
if not os.path.exists(init_law):
    with open(init_law, "w") as f:
        f.write("# intentionally empty\n")

write("scripts/law/check_structure.py", """#!/usr/bin/env python3
\"\"\"Enforce Rules 1, 2, 3: 5/5 Horizon, 500-line Ceiling, Depth-Sequence Coordinate.\"\"\"
from __future__ import annotations

import os
import sys
import fnmatch

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIN = os.path.join(PROJECT, "serin")

# Allowlist: filenames that don't need coordinates
EXEMPT_FILES: set[str] = {
    "__init__.py",
    "__main__.py",
    "conftest.py",
}
# Also allow top-level entry points like discord_bot.py, hot_reloader.py
ROOT_EXEMPT: set[str] = {"discord_bot.py", "hot_reloader.py"}

errors: list[str] = []


def check_55() -> None:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs", "__pycache__")]
        py_files = [f for f in files if f.endswith(".py") and f != "__init__.py"]
        actual_dirs = [d for d in dirs if not d.startswith("__")]
        if len(py_files) > 5:
            errors.append(f"RULE 1 FAIL: {root}: {len(py_files)} .py files (max 5)")
        if len(actual_dirs) > 5:
            errors.append(f"RULE 1 FAIL: {root}: {len(actual_dirs)} subdirs (max 5)")


def check_500() -> None:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in fnmatch.filter(files, "*.py"):
            if f == "__init__.py":
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, "r") as fh:
                    count = sum(1 for _ in fh)
                if count > 500:
                    errors.append(f"RULE 2 FAIL: {os.path.relpath(fp, PROJECT)}: {count} lines (max 500)")
            except Exception:
                pass


def check_coordinates() -> None:
    import re
    coord_re = re.compile(r"^d\\d_\\d_\\w+_\\w+\\.py$")
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in files:
            if f.endswith(".py") and f not in EXEMPT_FILES:
                # Check if the file has a coordinate name
                if not coord_re.match(f):
                    errors.append(f"RULE 3 FAIL: {os.path.relpath(os.path.join(root, f), PROJECT)}: '{f}' does not match d{D}_{S}_{W1}_{W2}.py")


def main() -> int:
    check_55()
    check_500()
    check_coordinates()
    if errors:
        for e in errors:
            print(e)
        return 1
    print("All structure checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
""")

# Copy the existing coordinate_rename.py to scripts/law/ or create a simple one
write("scripts/law/check_imports.py", """#!/usr/bin/env python3
\"\"\"Enforce Rule 5 (Depth DAG) and gateway isolation.

Rules:
1. Target_Depth < Importer_Depth must hold for all imports
2. Gateway files must not import from state/ or pipeline/
3. Ops files must not be imported by pipeline/ or gateway/
\"\"\"
from __future__ import annotations

import ast
import os
import sys
import fnmatch

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIN = os.path.join(PROJECT, "serin")

# Coordinate -> depth mapping for top-level dirs
TOP_LEVEL_DEPTHS: dict[str, int] = {
    "d1_1_pipeline_flow": 1,
    "d1_2_gateway_io": 2,
    "d1_3_state_core": 3,
    "d1_4_config_base": 4,
    "d1_5_ops_tooling": 5,
}

errors: list[str] = []


def get_file_depth(filepath: str) -> int:
    \"\"\"Get depth of a file based on its path.\"\"\"
    rel = os.path.relpath(filepath, SERIN)
    parts = rel.split(os.sep)
    # The depth in the coordinate system is based on the first dir
    first_dir = parts[0]
    if first_dir in TOP_LEVEL_DEPTHS:
        return TOP_LEVEL_DEPTHS[first_dir]
    # Fallback: count directory depth
    return len(parts)


def get_import_target_depth(import_str: str) -> int | None:
    \"\"\"Get depth of an import target based on its first module component.\"\"\"
    parts = import_str.split(".")
    first = parts[0]  # serin
    if len(parts) < 2:
        return None
    second = parts[1]
    if second in TOP_LEVEL_DEPTHS:
        return TOP_LEVEL_DEPTHS[second]
    return None


def check_file(fp: str) -> None:
    rel = os.path.relpath(fp, PROJECT)
    imp_depth = get_file_depth(fp)
    is_gateway = "d1_2_gateway_io" in rel

    try:
        with open(fp, "r") as fh:
            tree = ast.parse(fh.read())
    except SyntaxError:
        errors.append(f"SYNTAX ERROR: {rel}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target_depth = get_import_target_depth(alias.name)
                if target_depth is not None:
                    if target_depth >= imp_depth and "__future__" not in alias.name and "typing" not in alias.name:
                        errors.append(
                            f"RULE 5 DEPTH DAG: {rel} (depth {imp_depth}) imports "
                            f"{alias.name} (depth {target_depth}) — ILLEGAL"
                        )
                    if is_gateway and target_depth in (1, 3):  # pipeline(1) or state(3)
                        # Actually state depth is 3, not 1. Let's use the dir names:
                        pass

        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            target_depth = get_import_target_depth(node.module)
            if target_depth is not None:
                if target_depth >= imp_depth:
                    # Skip __future__ and typing
                    if node.module.startswith("__future__") or node.module.startswith("typing"):
                        continue
                    errors.append(
                        f"RULE 5 DEPTH DAG: {rel} (depth {imp_depth}) imports "
                        f"{node.module} (depth {target_depth}) — ILLEGAL"
                    )

            # Check gateway isolation
            if is_gateway:
                parts = node.module.split(".")
                if len(parts) >= 2:
                    if parts[1] == "d1_1_pipeline_flow":
                        errors.append(
                            f"GATEWAY ISOLATION: {rel} imports from pipeline ({node.module}) — use DI"
                        )
                    if parts[1] == "d1_3_state_core":
                        errors.append(
                            f"GATEWAY ISOLATION: {rel} imports from state ({node.module}) — use DI"
                        )

            # Check ops exposure
            if "d1_5_ops_tooling" in node.module:
                if "d1_1_pipeline_flow" in rel or "d1_2_gateway_io" in rel:
                    errors.append(
                        f"OPS EXPOSURE: {rel} imports from ops ({node.module}) — pipeline/gateway cannot import ops"
                    )


def main() -> int:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in fnmatch.filter(files, "*.py"):
            check_file(os.path.join(root, f))

    if errors:
        for e in errors:
            print(e)
        return 1
    print("All import checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
""")

# ═══════════════════════════════════════════════════════════════════════
# 5. Update pre-commit hook
# ═══════════════════════════════════════════════════════════════════════
print("=== 5. Pre-commit hook ===")
hook_path = os.path.join(PROJECT, ".git", "hooks", "pre-commit")
# Write the hook
write(".git/hooks/pre-commit", """#!/usr/bin/env bash
set -e

echo "=== Checking structure (Rules 1-3) ==="
python3 scripts/law/check_structure.py

echo ""
echo "=== Checking imports (Rule 5) ==="
python3 scripts/law/check_imports.py

echo ""
echo "=== Ruff lint ==="
uv run ruff check serin/

echo ""
echo "=== Bandit security ==="
uv run bandit -r serin/ -q

echo ""
echo "=== All checks pass ==="
""")
# Make executable
os.chmod(hook_path, 0o755)
print("  WROTE .git/hooks/pre-commit")

# ═══════════════════════════════════════════════════════════════════════
# 6. Fix test imports (update paths from serin.gateway -> serin.d1_2_gateway_io, etc.)
# ═══════════════════════════════════════════════════════════════════════
print("=== 6. Verify test imports ===")
old_patterns = [
    "serin.pipeline.",
    "serin.gateway.",
    "serin.state.",
    "serin.config.",
    "serin.ops.",
]
test_dir = os.path.join(PROJECT, "tests")
remaining = 0
for root, dirs, files in os.walk(test_dir):
    for f in fnmatch.filter(files, "*.py"):
        fp = os.path.join(root, f)
        try:
            content = open(fp, "r", encoding="utf-8").read()
            for pat in old_patterns:
                if pat in content:
                    print(f"  OLD IMPORT in {os.path.relpath(fp, PROJECT)}: {pat}")
                    remaining += 1
        except Exception:
            pass

if remaining == 0:
    print("  All test imports are already updated")
else:
    print(f"  WARNING: {remaining} old import patterns remain — run import update")

# ═══════════════════════════════════════════════════════════════════════
# Done
# ═══════════════════════════════════════════════════════════════════════
print()
print("=== Done! Run the following to verify: ===")
print("  uv run ruff check serin/ --fix")
print("  uv run bandit -r serin/ -q")
print("  python3 scripts/law/check_structure.py")
print("  python3 scripts/law/check_imports.py")
