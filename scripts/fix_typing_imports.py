"""Replace deprecated typing imports with built-in equivalents."""
import re
from pathlib import Path

SERIN_DIR = Path(__file__).resolve().parent.parent / "serin"

ANNOTATION_MAP = {
    "Dict": "dict",
    "List": "list",
    "Set": "set",
    "Tuple": "tuple",
    "Type": "type",
    "FrozenSet": "frozenset",
}

OPTIONAL_PATTERN = re.compile(r'Optional\[')


def replace_optional(text: str) -> str:
    """Replace `Optional[X]` with `X | None` handling nested brackets."""
    result: list[str] = []
    i = 0
    while i < len(text):
        idx = text.find('Optional[', i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        depth = 1
        j = idx + 9
        while j < len(text) and depth > 0:
            if text[j] == '[':
                depth += 1
            elif text[j] == ']':
                depth -= 1
            j += 1
        inner = text[idx + 9 : j - 1]
        result.append(f'{inner} | None')
        i = j
    return ''.join(result)


def fix_file(filepath: Path) -> bool:
    with open(filepath) as f:
        content = f.read()
    original = content

    # 1. Replace Dict[...] → dict[...] etc.
    for old, new in ANNOTATION_MAP.items():
        content = content.replace(f'{old}[', f'{new}[')

    # 2. Replace Optional[X] → X | None
    if 'Optional[' in content:
        content = replace_optional(content)

    # 3. Clean up import lines
    lines = content.split('\n')
    new_lines: list[str] = []
    for line in lines:
        m = re.match(r'( *)from typing import (.+)', line)
        if m:
            imports = [x.strip() for x in m.group(2).split(',')]
            # Remove names that have been replaced
            to_remove = set(ANNOTATION_MAP.keys()) | {'Optional'}
            kept = [x for x in imports if x not in to_remove]
            if kept:
                new_lines.append(f"{m.group(1)}from typing import {', '.join(kept)}")
            # If nothing kept, skip the line
        else:
            new_lines.append(line)

    content = '\n'.join(new_lines)

    # Also handle `import typing` usage
    for old, new in ANNOTATION_MAP.items():
        content = content.replace(f'typing.{old}', f'{new}')

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False


def main() -> None:
    changed = 0
    for f in sorted(SERIN_DIR.rglob('*.py')):
        if fix_file(f):
            print(f"  Fixed: {f.relative_to(SERIN_DIR.parent)}")
            changed += 1
    print(f"\nFixed {changed} files.")


if __name__ == '__main__':
    main()
