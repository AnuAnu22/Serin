"""Command-line entry point for the Pipeline Inspector.

One-shot mode runs a scenario end-to-end, dumps the FINAL context (production
JSON), prints optional per-stage diffs and check results, and exits non-zero on
any check failure. ``--interactive`` steps stage-by-stage, allowing ctx
mutation between stages.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from tools.pipeline_inspector.checks import get_check
from tools.pipeline_inspector.diff import diff_contexts
from tools.pipeline_inspector.dump import dump_context
from tools.pipeline_inspector.inspector import PipelineInspector
from tools.pipeline_inspector.scenario import Scenario, _Snap

DEFAULT_RESPONSE = "lol yeah that tracks honestly"
DEFAULT_CHECKS = "planner_constraints_survive,no_stage_error,llm_produced_response"


def _load_scenario(args: argparse.Namespace) -> Scenario:
    if args.scenario_path:
        with open(args.scenario_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if "content" not in data:
            raise ValueError("scenario JSON must contain a 'content' field")
        affect = data.get("affect")
        if affect is not None:
            affect = _Snap(
                valence=float(affect.get("valence", 0.0)),
                familiarity=float(affect.get("familiarity", 0.0)),
                impression=str(affect.get("impression", "")),
            )
        return Scenario(
            content=data["content"],
            user_id=str(data.get("user_id", "1234")),
            username=str(data.get("username", "Sam")),
            channel_id=str(data.get("channel_id", "inspector")),
            guild_id=data.get("guild_id"),
            is_mentioned=bool(data.get("is_mentioned", False)),
            affect=affect,
            facts=list(data.get("facts", [])),
            beliefs=list(data.get("beliefs", [])),
            recent_messages=list(data.get("recent_messages", [])),
            user_profile=dict(data.get("user_profile", {})),
        )
    return Scenario(content=args.content or "hey serin, test me")


def _print_stage_diffs(inspector: PipelineInspector) -> None:
    """Print what each executed stage changed (entry -> after each stage)."""
    for i in range(min(len(inspector.snapshots) - 1, len(inspector.stages))):
        if i == 0:
            continue  # snapshots[0] is the entry state
        label = inspector.events[i - 1]["stage"] if i - 1 < len(inspector.events) else f"stage{i}"
        lines = diff_contexts(inspector.snapshots[i - 1], inspector.snapshots[i])
        if not lines:
            continue
        print(f"\n== {label} ==")
        print("\n".join(lines))


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def _run_checks(ctx: Any, names: list[str]) -> int:
    failures = 0
    for name in names:
        fn = get_check(name)
        if fn is None:
            print(f"CHECK ERROR: unknown check {name!r}")
            failures += 1
            continue
        err = fn(ctx)
        if err is not None:
            print(f"CHECK FAIL [{name}]: {err}")
            failures += 1
        else:
            print(f"CHECK PASS [{name}]")
    return failures


async def _one_shot(args: argparse.Namespace) -> int:
    scenario = _load_scenario(args)
    inspector = PipelineInspector.from_scenario(
        scenario,
        force_reply=args.force_reply,
        response=args.response or DEFAULT_RESPONSE,
    )
    ctx = await inspector.run_until(scenario.build_context())

    if args.diff:
        _print_stage_diffs(inspector)

    output = dump_context(ctx)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
        print(f"[wrote final-state dump to {args.json_out}]")
    print(output)

    check_names = [t.strip() for t in (args.checks or DEFAULT_CHECKS).split(",") if t.strip()]
    failures = await _run_checks(ctx, check_names)
    return 0 if failures == 0 else 1


async def _interactive(args: argparse.Namespace) -> int:
    scenario = _load_scenario(args)
    inspector = PipelineInspector.from_scenario(
        scenario,
        force_reply=args.force_reply,
        response=args.response or DEFAULT_RESPONSE,
    )
    ctx = scenario.build_context()
    stages = inspector.stages
    print("Commands: step | continue | set <field>=<value> | dump | diff | exit")

    while True:
        cmd = input(f"n{inspector._pos}/{len(stages)}> ").strip()
        if cmd in ("exit", "quit", "q"):
            break
        if cmd in ("continue", "c"):
            ctx = await inspector.run_until(ctx)
            print(dump_context(ctx))
            break
        if cmd == "step":
            if inspector._pos >= len(stages):
                print("all stages done")
                continue
            before = inspector.state_after(inspector._pos - 1)
            ctx = await inspector.run_until(ctx, stop_after=inspector._pos)
            after = dump_context(ctx)
            stage = stages[inspector._pos - 1].name
            print(f"\n== {stage} ==")
            for line in diff_contexts(before, after):
                print(line)
            continue
        if cmd == "dump":
            print(dump_context(ctx, include_message=True))
            continue
        if cmd.startswith("set "):
            field, _, raw = cmd[4:].partition("=")
            if not raw:
                print("usage: set <field>=<value>")
                continue
            setattr(ctx, field.strip(), _parse_value(raw))
            print(f"set {field.strip()}={_parse_value(raw)!r}")
            continue
        if cmd == "diff":
            _print_stage_diffs(inspector)
            continue
        print("unknown command")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline-inspector",
        description="Drive the real MessagePipeline offline and inspect final + boundary state.",
    )
    parser.add_argument("--content", help="inline message content for the scenario")
    parser.add_argument("--scenario-path", help="path to a JSON scenario file")
    parser.add_argument("--mode", choices=["dry", "real"], default="dry",
                        help="dry = fakes everywhere (default); real = real stores via overrides")
    parser.add_argument("--force-reply", action=argparse.BooleanOptionalAction, default=True,
                        help="force a reply via the real creator hard-override (default on)")
    parser.add_argument("--response", help="canned LLM response")
    parser.add_argument("--break-at", action="append", type=int, help="(future) stop at stage index")
    parser.add_argument("--diff", action="store_true", help="print per-stage diffs")
    parser.add_argument("--checks", default=DEFAULT_CHECKS, help="comma-separated check names")
    parser.add_argument("--interactive", action="store_true", help="enter step-mode")
    parser.add_argument("--json-out", help="write the final-state dump to PATH")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.interactive:
            return asyncio.run(_interactive(args))
        return asyncio.run(_one_shot(args))
    except FileNotFoundError as exc:
        parser.error(f"scenario file not found: {exc.filename}")
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2


__all__ = ["main"]
