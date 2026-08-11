# TESTING_PIPELINE.md — Pipeline Inspector

`tools/pipeline_inspector/` is a dev tool that drives the **real** 10-stage
`MessagePipeline` with synthetic input and lets you inspect, dump, diff, assert,
and mutate the context at any stage boundary — fully offline in dry-run mode.

It sits between the pytest suite (which tests stages *in isolation* with mocks)
and live smoke-testing (which needs the bot + Discord + LLM). It is a third
thing: **run the real pipeline end-to-end with fake infrastructure, and watch
every hop.** It exists to catch wiring bugs — planner constraints silently
dropped between stages, system prompts rebuilt and discarding upstream work,
dead call paths — that only show up when the whole real pipeline runs once.

**What is real, what is faked.** Every stage class and `MessagePipeline.process()`
control flow are the unmodified production classes, imported directly. Only the
*external dependencies* they were injected with are swapped: the LLM (canned
response), memory/Qdrant (in-memory dicts), Discord client (None), affect/mood
(per-scenario snapshots). So `dry` mode needs **zero running infrastructure.**

---

## Quick start

```bash
# One-shot: run a scenario, dump the FINAL post-run state as production JSON,
# and run the standard checks.
uv run python -m tools.pipeline_inspector \
  --content "hey serin, what's the move tonight" \
  --response "saw your message, let's do it" \
  --checks planner_constraints_survive,no_stage_error
```

The dump is emitted through production's own encoder (`make_json_safe`), the
same cipher the control panel uses — not a decorative pretty-printer. It shows
the **actual final state after the pipeline ran**, including
`halt_reason`, `final_response`, `stage_timings`, and `metadata`.

Run the whole test suite:

```bash
uv run python -m pytest tests/inspector/ -q
```

---

## CLI reference

| Flag | Meaning |
|------|---------|
| `--content TEXT` | Inline message content for the scenario. |
| `--scenario-path FILE` | Load a scenario from JSON (see below). |
| `--mode dry\|real` | `dry` = fakes everywhere (default). `real` = real stores via overrides. |
| `--force-reply / --no-force-reply` | Force a reply via the real creator hard-override (default on). |
| `--response TEXT` | Canned LLM response. |
| `--diff` | Print per-stage diffs (entry → after each stage). |
| `--checks A,B` | Comma-separated check names (see Checks). |
| `--interactive` | Step-mode (see below). |
| `--json-out PATH` | Also write the final-state dump to PATH. |

### Scenario JSON

```json
{
  "content": "did you catch that last play?",
  "user_id": "42",
  "username": "Rin",
  "is_mentioned": false,
  "affect": { "valence": 0.6, "familiarity": 0.8, "impression": "" },
  "facts": [
    { "claim": "Rin plays table tennis", "belief": 0.9, "variance": 0.05 }
  ],
  "beliefs": [
    {
      "content": "Rin handles losses well",
      "state": "SUPPORTED",
      "confidence": 0.9
    }
  ],
  "recent_messages": [
    { "role": "user", "content": "rough night yesterday" }
  ],
  "user_profile": { "name": "Rin", "interests": ["table tennis"] }
}
```

The `facts`/`beliefs` shapes above are the **contract the real stages read**:
`PromptAssemblyStage` requires each belief to carry a `content` key and each
fact to carry `claim`/`belief`/`variance`. A `SUPPORTED` belief with
`confidence >= 0.7` is what makes `ResponsePlannerStage` emit response
constraints — used by the known-broken test (`tests/inspector/test_known_broken.py`).

---

## Checks

Reusable assertions that run against a (post-run) `MessageContext` and return
an error string on the first failure:

| Check | Fails when |
|-------|-----------|
| `planner_constraints_survive` | a constraint recorded in `response_plan` is absent from `system_prompt` (the dropped-constraints bug). |
| `no_stage_error` | the pipeline halted on an uncaught stage exception (`halt_reason` starts `stage_error:`). |
| `llm_produced_response` | the pipeline decided to respond but produced no LLM output. |

All three run by default. Add your own via
`tools.pipeline_inspector.checks.register(name, fn)` where
`fn(ctx) -> str | None`.

---

## Interactive step-mode

Breakpoints let you stop at a stage boundary, inspect, **mutate ctx**, and
continue — the "watch state at every hop" part.

```bash
uv run python -m tools.pipeline_inspector \
  --content "hey serin, test me" \
  --interactive
```

```
n0/10> step      # run one stage, show the diff it caused
n1/10> dump      # full production-JSON dump of current ctx
n3/10> set system_prompt="You are Serin."   # mutate between stages
n4/10> continue  # run to completion, dump final state
```

Commands: `step`, `continue|c`, `set <field>=<value>`, `dump`, `diff`,
`exit|quit|q`.

---

## How it works

`PipelineInspector` mirrors `MessagePipeline.process()`'s control flow by hand
(calling each real `stage.run(ctx)`), so it reproduces the exact halt semantics:

- per-stage try/except; on exception → `ctx.halt_reason = "stage_error:<name>"` + break;
- break when `ctx.halt_reason` is set;
- the tail still runs `MemoryWriteStage` on halt (facts must still be extracted).

It deep-copies a snapshot of `MessageContext` at **every stage boundary**, so
diff can compare stage N vs N+1 without the live ctx's in-place mutations
having overwritten the earlier state.

---

## This is a real-fact discovery tool

Running the tool surfaced facts that static analysis missed:

- `SendStage` preserves `final_response` and sets `metadata["message_sent"]=true`
  even with a null Discord client.
- The real Boltzmann decision stage, given a synthetic *first* message from a
  stranger, **ignores it by default** (ambient/unaddressed traffic is filtered
  hard). It only ever fires a reply via a hard override (`force_reply=True`
  unioning the author into `creator_ids`). `force_reply` does **not** bypass
  `ResponseDecisionStage`'s logic — it still advances the dynamics engine,
  computes salience, and reads valence/familiarity; only the final Boltzmann
  `decide_action` sampling is skipped. To observe the real selectivity path,
  run with `--no-force-reply` and inspect `ctx.halt_reason` / `ctx.should_respond`.

This is the tool paying for itself: plumbing bugs get caught by running the
pipeline once, not by six rounds of static archaeology.

## Validation

`tests/inspector/test_known_broken.py` proves the checks catch a real bug class:
it reintroduces the dropped-planner-constraints defect (via the inspector's
mutate hook, without touching real stages) and asserts `planner_constraints_survive`
fires. A throwaway-branch check confirmed that dropping the actual
`_add_response_plan_constraints` call from the real `PromptAssemblyStage` is
also caught — the branch was discarded.