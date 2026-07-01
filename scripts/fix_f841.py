"""Fix F841 (unused variable) violations by removing dead assignments."""
import re
from pathlib import Path

SERIN_DIR = Path(__file__).resolve().parent.parent / "serin"

FIXES: dict[str, list[dict]] = {
    "serin/gateway/voice_transcribe/decider.py": [
        {"line": 79, "action": "delete"},
        {"line": 80, "action": "delete"},
        {"line": 131, "action": "except_no_e"},
    ],
    "serin/gateway/voice_transcribe/tracker.py": [
        {"line": 44, "action": "delete"},
    ],
    "serin/ops/background.py": [
        {"line": 314, "action": "delete"},
    ],
    "serin/ops/control_panel/panel_lifecycle.py": [
        {"line": 92, "action": "delete"},
    ],
    "serin/pipeline/ingest/sync/crawler.py": [
        {"line": 297, "action": "delete"},
    ],
    "serin/pipeline/perceive/bot_personality.py": [
        {"line": 149, "action": "delete"},
    ],
    "serin/pipeline/remember/core/bm25_index.py": [
        {"line": 64, "action": "delete"},
    ],
    "serin/pipeline/remember/knowledge/beliefs.py": [
        {"line": 214, "action": "delete"},
    ],
    "serin/pipeline/remember/knowledge/evidence.py": [
        {"line": 106, "action": "delete"},
        {"line": 108, "action": "delete"},
    ],
    "serin/pipeline/remember/knowledge/retrieval.py": [
        {"line": 313, "action": "delete"},
        {"line": 344, "action": "delete"},
    ],
    "serin/pipeline/remember/sync_monitor.py": [
        {"line": 115, "action": "delete"},
        {"line": 153, "action": "delete"},
    ],
    "serin/pipeline/remember/temporal.py": [
        {"line": 160, "action": "delete"},
    ],
    "serin/pipeline/think/response_planner.py": [
        {"line": 63, "action": "delete"},
    ],
    "serin/state/db_protect/recovery.py": [
        {"line": 47, "action": "delete"},
    ],
    "serin/state/memory/belief_store.py": [
        {"line": 214, "action": "delete"},
    ],
    "serin/state/memory/evidence_store.py": [
        {"line": 106, "action": "delete"},
        {"line": 108, "action": "delete"},
    ],
    "serin/state/voice/voice_decider.py": [
        {"line": 79, "action": "delete"},
        {"line": 80, "action": "delete"},
        {"line": 131, "action": "except_no_e"},
    ],
    "serin/state/voice/voice_tracker.py": [
        {"line": 44, "action": "delete"},
    ],
}


def fix_file(filepath: Path, fixes: list[dict]) -> bool:
    with open(filepath) as f:
        lines = f.readlines()
    original = lines.copy()

    # Process fixes in reverse line order so line numbers stay valid
    for fix in sorted(fixes, key=lambda x: x["line"], reverse=True):
        idx = fix["line"] - 1  # 0-indexed
        action = fix["action"]

        if action == "delete":
            del lines[idx]
        elif action == "except_no_e":
            line = lines[idx]
            # Change `except (X, Y) as e:` to `except (X, Y):`
            # Change `except X as e:` to `except X:`
            fixed = re.sub(r'except\s+(.+)\s+as\s+\w+\s*:', r'except \1:', line)
            if fixed != line:
                lines[idx] = fixed
            else:
                print(f"  WARN: Could not fix 'as e' on line {fix['line']} in {filepath.relative_to(SERIN_DIR.parent)}")

    if lines != original:
        with open(filepath, 'w') as f:
            f.writelines(lines)
        return True
    return False


def main() -> None:
    changed = 0
    for rel_path_str, fixes in FIXES.items():
        filepath = SERIN_DIR.parent / rel_path_str
        if not filepath.exists():
            print(f"  SKIP: {rel_path_str} not found")
            continue
        if fix_file(filepath, fixes):
            print(f"  Fixed: {rel_path_str}")
            changed += 1
    print(f"\nFixed {changed} files.")


if __name__ == '__main__':
    main()
