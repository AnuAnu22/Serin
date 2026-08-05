"""Runtime integrity — every module under serin/ must import, and
no file may contain undefined variables in string literals.

Two layers of defense:
  1. Import test: every .py file loads without errors
  2. Undefined var scan: Rust binary finds {identifier} in non-f-strings
     where the identifier doesn't exist anywhere in the file
"""
from __future__ import annotations

import asyncio
import importlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIN_DIR = PROJECT_ROOT / "serin"
SCANNER_BIN = PROJECT_ROOT / "scripts" / "undef-var-scanner" / "target" / "release" / "undef-var-scanner"


# ── Layer 1: Module import ──────────────────────────────────────────────

def _discover_modules() -> list[str]:
    modules: list[str] = []
    for pyfile in sorted(SERIN_DIR.rglob("*.py")):
        if pyfile.name in ("__init__.py", "__main__.py"):
            continue
        rel = pyfile.relative_to(PROJECT_ROOT)
        modules.append(str(rel.with_suffix("")).replace("/", "."))
    return modules


_ALL_SERIN_MODULES = _discover_modules()


@pytest.mark.parametrize("module_name", _ALL_SERIN_MODULES)
def test_module_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)


# ── Layer 2: Undefined variable scan (Rust binary) ─────────────────────

def _run_scanner() -> tuple[int, str]:
    """Run the Rust scanner and return (exit_code, stderr)."""
    if not SCANNER_BIN.exists():
        pytest.skip("Rust scanner not built — run: cargo build --release in scripts/undef-var-scanner/")
    result = subprocess.run(
        [str(SCANNER_BIN), str(SERIN_DIR)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stderr


def _parse_scanner_output(stderr: str) -> list[tuple[str, int, str]]:
    """Parse scanner output into (file, line, varname) tuples."""
    issues: list[tuple[str, int, str]] = []
    for line in stderr.splitlines():
        line = line.strip()
        if " — {" in line and " not defined" in line:
            # Format: "file.py:42 — {varname} not defined"
            parts = line.split(" — ")
            if len(parts) == 2:
                file_line = parts[0]
                var_part = parts[1].replace(" not defined", "").strip("{}")
                if ":" in file_line:
                    filepath, lineno = file_line.rsplit(":", 1)
                    issues.append((filepath, int(lineno), var_part))
    return issues


_UNDEFINED_SCAN = _run_scanner()
_UNDEFINED_ISSUES = _parse_scanner_output(_UNDEFINED_SCAN[1]) if _UNDEFINED_SCAN[0] != 0 else []


@pytest.mark.parametrize(
    "filename,line,varname",
    _UNDEFINED_ISSUES,
    ids=[f"{i[0]}:{i[1]} {{{i[2]}}}" for i in _UNDEFINED_ISSUES],
)
def test_string_var_defined(filename: str, line: int, varname: str) -> None:
    filepath = SERIN_DIR / filename
    source = filepath.read_text(errors="replace")
    lines = source.splitlines()
    context = lines[line - 1].strip() if line <= len(lines) else ""
    assert False, (
        f"{{{varname}}} in {filename}:{line} — "
        f"variable '{varname}' not found in file. Line: {context}"
    )


def test_undefined_scan_runs() -> None:
    """The Rust scanner must execute and report results."""
    exit_code, stderr = _run_scanner()
    # Exit 0 = clean, exit 1 = issues found — both are valid
    # Exit 2+ = scanner crashed
    assert exit_code <= 1, f"Scanner crashed with exit code {exit_code}:\n{stderr}"


def test_voice_available() -> None:
    from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import voice_available
    assert voice_available is True


# ── Layer 3: Attribute contract — standalone `self: Any` functions  ──────
# Must only access attributes that exist on their target class.
# Catches "NoneType has no attribute" errors at test time.

import ast  # noqa: E402 — import after module-level code

# Only list functions that are actually imported and used at runtime.
_SELF_MAP: dict[str, dict[str, str | list[str]]] = {
    "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_5_message_process.py": {
        "class_file": "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_4_core_manager.py",
        "class_name": "EnhancedMessageManagerV3",
        "functions": ["process_voice_input"],
    },
    "d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_2_bridge_commands.py": {
        "class_file": "d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_4_process_watch/d5_1_process_watch.py",
        "class_name": "RustVoiceBridge",
        "functions": ["send_tts_audio", "interrupt"],
    },
}


def _get_class_members(filepath: str, class_name: str) -> set[str]:
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    members: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self":
                    members.add(item.attr)
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
    return members


def _get_self_accesses_in_funcs(filepath: str, func_names: list[str]) -> set[str]:
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    accesses: set[str] = set()
    func_set = set(func_names)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in func_set:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Attribute) and isinstance(stmt.value, ast.Name) and stmt.value.id == "self":
                    accesses.add(stmt.attr)
    return accesses


_ATTR_ISSUES: list[tuple[str, str, set[str]]] = []
for func_rel, mapping in _SELF_MAP.items():
    class_name = mapping["class_name"]
    func_names = mapping["functions"]
    class_rel = mapping["class_file"]
    assert isinstance(class_name, str) and isinstance(class_rel, str) and isinstance(func_names, list)
    class_members = _get_class_members(class_rel, class_name)
    func_accesses = _get_self_accesses_in_funcs(func_rel, func_names)
    missing = func_accesses - class_members
    if missing:
        _ATTR_ISSUES.append((func_rel, class_name, missing))


@pytest.mark.parametrize(
    "func_file,class_name,missing",
    _ATTR_ISSUES,
    ids=[f"{p[0]}: {','.join(sorted(p[2]))[:60]}" for p in _ATTR_ISSUES],
)
def test_self_attrs_exist_on_target(func_file: str, class_name: str, missing: set[str]) -> None:
    m = _SELF_MAP[func_file]
    assert isinstance(m, dict)
    pytest.fail(
        f"Functions in {func_file} ({', '.join(m['functions'])})\n"
        f"access `self.xxx` not defined on {class_name} (in {m['class_file']}).\n"
        f"Missing: {{ {', '.join(sorted(missing))} }}\n\n"
        "Fix: add attributes/methods to the class, or use getattr() in the function."
    )


def test_no_missing_self_attrs() -> None:
    if not _ATTR_ISSUES:
        return
    msg_lines: list[str] = []
    for func_rel, class_name, missing in _ATTR_ISSUES:
        m = _SELF_MAP[func_rel]
        assert isinstance(m, dict)
        msg_lines.append(
            f"  {func_rel} \u2192 {class_name} ({m['class_file']}):\n"
            f"    Functions: {', '.join(m['functions'])}\n"
            f"    Missing: {{ {', '.join(sorted(missing))} }}"
        )
    pytest.fail(
        "Attribute contract violations found:\n\n" + "\n".join(msg_lines) + "\n\n"
        "Fix: add the missing attributes to the class, or use getattr() in the function."
    )


# ── Layer 4: Dict contract — returned dict keys must match consumer accesses ──

# Each entry: (provider_file, provider_func, consumer_file, consumer_func,
#              provider_keys (from return dict), consumer_keys (bracket accesses))
_DICT_CONTRACTS: list[dict[str, Any]] = []


def _get_return_dict_keys(filepath: str, func_name: str) -> set[str]:
    """Get the string literal keys from a `return { ... }` dict."""
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    keys: set[str] = set()
                    for k in stmt.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
                    return keys
    return set()


def _get_dict_bracket_accesses(filepath: str, func_name: str, param_name: str = "context") -> set[str]:
    """Get dict keys accessed via bracket notation `d[key]` on a named parameter inside a function."""
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Subscript):
                    # dict['key'] — value is Name(id=param_name), slice is Constant(value=str)
                    if (isinstance(stmt.value, ast.Name) and stmt.value.id == param_name
                            and isinstance(stmt.slice, ast.Constant) and isinstance(stmt.slice.value, str)):
                        keys.add(stmt.slice.value)
    return keys


def _build_dict_contracts() -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []

    # build_context ↔ format_context_for_llm
    provider_keys = _get_return_dict_keys(
        "d1_1_pipeline_flow/d2_2_flow_ingest/d3_1_ingest_context/d4_1_context_builder.py",
        "build_context"
    )
    consumer_accesses = _get_dict_bracket_accesses(
        "d1_1_pipeline_flow/d2_2_flow_ingest/d3_1_ingest_context/d4_1_context_builder.py",
        "format_context_for_llm",
        param_name="context"
    )
    missing = consumer_accesses - provider_keys
    if missing:
        contracts.append({
            "provider": "ContextBuilder.build_context",
            "consumer": "ContextBuilder.format_context_for_llm",
            "provider_keys": sorted(provider_keys),
            "consumer_keys": sorted(consumer_accesses),
            "missing": sorted(missing),
        })

    # recall_image dict keys → process_voice_input consumer
    provider_keys2 = _get_return_dict_keys(
        "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_2_core_vision/d5_1_visual_memory.py",
        "recall_image"
    )
    _get_dict_bracket_accesses(
        "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_5_message_process.py",
        "process_voice_input",
        param_name="context"
    )
    # Also check top_match['xxx'] accesses in process_voice_input
    source2 = (SERIN_DIR / "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_5_message_process.py").read_text(errors="replace")
    tree2 = ast.parse(source2)
    top_match_keys: set[str] = set()
    for node in ast.walk(tree2):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "process_voice_input":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Subscript):
                    if (isinstance(stmt.value, ast.Name) and stmt.value.id == "top_match"
                            and isinstance(stmt.slice, ast.Constant) and isinstance(stmt.slice.value, str)):
                        top_match_keys.add(stmt.slice.value)
    missing2 = top_match_keys - provider_keys2
    if missing2:
        contracts.append({
            "provider": "VisualMemory.recall_image",
            "consumer": "process_voice_input (via top_match)",
            "provider_keys": sorted(provider_keys2),
            "consumer_keys": sorted(top_match_keys),
            "missing": sorted(missing2),
        })

    return contracts


_DICT_CONTRACT_ISSUES = _build_dict_contracts()


@pytest.mark.parametrize(
    "issue",
    _DICT_CONTRACT_ISSUES,
    ids=[f"{i['provider']} \u2192 {i['consumer']}" for i in _DICT_CONTRACT_ISSUES],
)
def test_dict_keys_exist(issue: dict[str, Any]) -> None:
    pytest.fail(
        f"Dict contract violation: {issue['provider']} \u2192 {issue['consumer']}\n"
        f"  Provider returns keys: {issue['provider_keys']}\n"
        f"  Consumer accesses keys: {issue['consumer_keys']}\n"
        f"  Missing from provider: {issue['missing']}\n\n"
        "Fix: add the missing keys to the provider's return dict, or use .get() in the consumer."
    )


def test_no_missing_dict_keys() -> None:
    if not _DICT_CONTRACT_ISSUES:
        return
    msg_lines: list[str] = []
    for issue in _DICT_CONTRACT_ISSUES:
        msg_lines.append(
            f"  {issue['provider']} \u2192 {issue['consumer']}:\n"
            f"    Missing keys: {issue['missing']}"
        )
    pytest.fail(
        "Dict contract violations found:\n\n" + "\n".join(msg_lines) + "\n\n"
        "Fix: add keys to provider return dict or use .get() in consumer."
    )


# ── Layer 5: Voice TTS pipeline contracts ─────────────────────────────

VOICE_PROCESSOR_FILE = (
    "d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_5_message_process.py"
)
VOICE_PIPELINE_FILE = (
    "d1_2_gateway_io/d2_3_voice_transcribe/d3_3_transcribe_pipeline.py"
)


def test_process_voice_input_accepts_guild_id() -> None:
    """process_voice_input must have a guild_id parameter to avoid context fallback."""
    source = (SERIN_DIR / VOICE_PROCESSOR_FILE).read_text(errors="replace")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "process_voice_input":
            param_names = {arg.arg for arg in node.args.args}
            assert "guild_id" in param_names, (
                "process_voice_input missing 'guild_id' parameter — "
                "TTS playback falls back to fragile context.get('guild_id') + get_channel()"
            )
            # Verify default is None (backward-compatible)
            defaults = node.args.defaults
            has_none_default = any(
                isinstance(d, ast.Constant) and d.value is None
                for d in defaults
            )
            assert has_none_default, "guild_id must default to None for backward compatibility"
            return
    pytest.fail("process_voice_input function not found")


def test_caller_passes_guild_id() -> None:
    """The voice pipeline must pass guild_id to process_voice_input."""
    source = (SERIN_DIR / VOICE_PIPELINE_FILE).read_text(errors="replace")
    tree = ast.parse(source)
    # Look for the call to _process_voice_input
    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            if isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg == "guild_id":
                        return
    pytest.fail(
        "process_voice_input called without guild_id=guild_id in "
        "d3_3_transcribe_pipeline.py — TTS playback can't determine guild"
    )


def test_voice_output_manager_none_not_silent() -> None:
    """When voice_output_manager is None, a warning must be logged — not silent."""
    source = (SERIN_DIR / VOICE_PROCESSOR_FILE).read_text(errors="replace")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "process_voice_input":
            for stmt in ast.walk(node):
                # Match `if self.voice_output_manager is None:`
                if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
                    cmp = stmt.test
                    if (len(cmp.ops) == 1 and isinstance(cmp.ops[0], ast.Is)
                            and isinstance(cmp.left, ast.Attribute)
                            and cmp.left.attr == "voice_output_manager"
                            and len(cmp.comparators) == 1
                            and isinstance(cmp.comparators[0], ast.Constant)
                            and cmp.comparators[0].value is None):
                        for body_stmt in stmt.body:
                            if (isinstance(body_stmt, ast.Expr)
                                    and isinstance(body_stmt.value, ast.Call)
                                    and isinstance(body_stmt.value.func, ast.Attribute)
                                    and body_stmt.value.func.attr == "warning"):
                                return
    pytest.fail(
        "process_voice_input must log a warning when voice_output_manager is None. "
        "Without this, the response is silently dropped with no trace."
    )


# ── Layer 6: Logging coverage — no silent error swallowing ────────────

_VOICE_PIPELINE_FILES: list[str] = [
    "d1_2_gateway_io/d2_2_voice_system/d3_1_system_audio/d4_1_audio_process/d5_1_audio_processor.py",
    "d1_2_gateway_io/d2_2_voice_system/d3_1_system_audio/d4_2_audio_transcribe.py",
    "d1_2_gateway_io/d2_2_voice_system/d3_1_system_audio/d4_4_audio_vad.py",
    "d1_2_gateway_io/d2_2_voice_system/d3_4_system_output.py",
    "d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_2_bridge_commands.py",
    "d1_2_gateway_io/d2_3_voice_transcribe/d3_3_transcribe_pipeline.py",
    "d1_2_gateway_io/d2_3_voice_transcribe/d3_4_transcribe_transcriber.py",
]

# Files in the voice pipeline that are allowed to have silent except blocks
# (e.g. a one-line except: pass that just guards a best-effort operation)
_ALLOWED_SILENT_EXCEPT: set[tuple[str, int]] = set()


def _calls_logger(body: list[ast.stmt]) -> bool:
    """Check if any statement in body calls .logger or .get_logger()."""
    for stmt in ast.walk(ast.Module(body=[], type_ignores=[])):
        pass
    # Walk the actual body
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("info", "warning", "error", "exception", "debug", "success"):
                return True
    return False


def _collect_silent_excepts(filepath: str) -> list[tuple[int, str]]:
    """Find except handlers with no logging AND no flow control (raise, return, break, continue)."""
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    silent: list[tuple[int, str]] = []
    _body = ast.Module(body=[], type_ignores=[])
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            has_log = _calls_logger(node.body)
            has_flow = any(
                isinstance(s, (ast.Raise, ast.Return, ast.Break, ast.Continue))
                for s in ast.walk(ast.Module(body=node.body, type_ignores=[]))
            )
            if not has_log and not has_flow:
                name = node.name or ""
                type_name = node.type
                label = "bare except:" if type_name is None else f"except {name}:"
                lineno = node.lineno or 0
                if (filepath, lineno) not in _ALLOWED_SILENT_EXCEPT:
                    silent.append((lineno, label))
    return silent


@pytest.mark.parametrize("filepath", _VOICE_PIPELINE_FILES)
def test_no_silent_except_in_voice_pipeline(filepath: str) -> None:
    """Every except block in the voice pipeline must log, raise, or return."""
    silent = _collect_silent_excepts(filepath)
    if silent:
        lines = "\n".join(f"  L{lineno}: {label}" for lineno, label in silent)
        pytest.fail(
            f"Silent except blocks found in {filepath}:\n{lines}\n\n"
            "Every except must log (error/warning), re-raise, or return. "
            "Silent except: hides failures and makes debugging impossible."
        )


def _collect_silent_resource_check(filepath: str) -> list[tuple[int, str]]:
    """Find `if self.X:` with no `else:` — resource availability check that
    silently skips when the resource is unavailable.

    This catches the pattern: 'if voice_output_manager: speak()' with no
    else to log when it's None. Only flags when:
      - Test is `self.X` (attribute access)
      - No `else` branch
      - Body does something (not just a guard clause)
    """
    source = (SERIN_DIR / filepath).read_text(errors="replace")
    tree = ast.parse(source)
    issues: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and not node.orelse:
            test = node.test
            # Match `self.X` (truthiness check on an attribute)
            if (isinstance(test, ast.Name) and test.id.startswith("self")
                    and not node.body):
                continue
            if isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name) and test.value.id == "self":
                # Skip simple guard clauses: if self.X: return early
                body_ends_with = None
                if node.body and isinstance(node.body[-1], (ast.Return, ast.Break, ast.Continue)):
                    body_ends_with = type(node.body[-1]).__name__.lower()
                if body_ends_with and len(node.body) <= 2:
                    continue
                # Skip cleanup patterns: if self.X: X.cancel() / X.close()
                if len(node.body) == 1 and isinstance(node.body[0], ast.Expr):
                    call = node.body[0].value
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                        if call.func.attr in ("cancel", "close", "stop"):
                            continue
                if not _calls_logger(node.body):
                    lineno = node.lineno or 0
                    issues.append((lineno, f"self.{test.attr} check — no else, no log"))
    return issues


@pytest.mark.parametrize("filepath", _VOICE_PIPELINE_FILES)
def test_no_silent_resource_check_in_voice_pipeline(filepath: str) -> None:
    """`if self.X:` without `else:` must log when the resource is missing.

    Catches the pattern: 'if voice_output_manager: speak()' with no else
    to warn when it's None — responses silently dropped.
    """
    issues = _collect_silent_resource_check(filepath)
    if issues:
        lines = "\n".join(f"  L{lineno}: {msg}" for lineno, msg in issues)
        pytest.fail(
            f"Silent resource checks found in {filepath}:\n{lines}\n\n"
            "Every `if self.X:` must have an `else:` that logs when X is missing."
        )
