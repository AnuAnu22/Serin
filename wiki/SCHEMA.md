# Serin Wiki Schema (SCHEMA.md)

This file is the constitution of the wiki at `wiki/`. Every future LLM session that
touches the wiki reads this first, then follows it. You (the human) curate sources and
ask questions; the LLM writes and maintains everything in `wiki/`.

## Three layers (never mix them)

| Layer | Path | Who writes | Rule |
|---|---|---|---|
| Raw sources | `docs/`, `serin/`, `tests/`, git history, `docs/wiki/` | humans/code | **Immutable input.** The LLM reads, never edits. |
| The wiki | `wiki/**/*.md` | the LLM, in conversation | The compiled, interlinked knowledge base. |
| This schema | `wiki/SCHEMA.md` | human + LLM (co-evolved) | The rules. |

## Page types (one page = one type, in frontmatter)

| type | What it is | Example |
|---|---|---|
| `overview` | Cross-cutting map: architecture, flows, testing, debt | `overviews/architecture.md` |
| `entity` | A concrete component/class/module: what it is, real path, responsibilities, key methods, who consumes/writes it | `entities/message_pipeline.md` |
| `concept` | An idea/principle/pattern: definition, why it matters, where it shows up, status | `concepts/bayesian_beliefs.md` |
| `source` | A raw document distilled into the wiki: provenance (real path), key contents, what it informs | `sources/subsystem_act.md` |
| `query` | A filed answer/analysis from a question session — good answers become pages | `queries/2026-08-16_why_two_cleaning_paths.md` |

## File naming

- Lowercase snake_case (`message_pipeline.md`), one concept per file, no `d-` coordinates —
  the depth-sequence law governs `serin/` code, not the wiki layer. Every page name must be
  guessable: a reader should find `concepts/bayesian_beliefs.md` without the index.
- Every page carries the canonical **real code path** in its body where applicable
  (e.g. `serin/d1_1_pipeline_flow/d2_1_flow_act/d3_1_act_runners/d4_2_runners_pipeline.py`),
  so wiki ↔ code navigation is bidirectional.

## Frontmatter (every page, light)

```yaml
---
type: entity            # overview | entity | concept | source | query
tags: [pipeline, act]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/ARCHITECTURE.md]     # real paths or [[wikilinks]]
status: seed            # seed | live | stale
---
```

## Conventions

- `[[wikilinks]]` everywhere — entities mention concepts, concepts mention entities, both
  cite sources, and *every* page links back to `[[index]]`. No orphan pages.
- One `#` title per page; sections `## What it is`, `## Where it lives` (entities),
  `## Why it matters` (concepts), `## Notes / Known issues`.
- **Flag contradictions, never silently resolve them.** Serin's docs contain known ones —
  e.g. THE_LAW's idealized `pipeline/gateway/state/...` tree vs. ARCHITECTURE.md's verified
  `d1_1…d1_5` tree. Where a wiki page must state something and a source disagrees, say so
  and `[[wikilink]]` both sides (e.g. `concepts/the_law_rule5.md` → "Rule set" + "actual
  layout per ARCHITECTURE.md"). Note new contradictions on `overviews/known_debt.md` and in the log.
- **Stale claims get marked, not silently edited.** When a newer source supersedes an older
  one, annotate (`> ⚠️ SUPERSEDED by …`) and update `status: stale`.
- Every wiki edit decision is **caused by a source** — cite the real path it came from
  (this mirrors the project's own "causality, not performance" value).

## Operations (workflows the LLM runs on request)

### INGEST — "add source X"
1. Read X in full.
2. Summarize key takeaways with you; agree on emphases.
3. Write a `source` page for X (or update an existing one).
4. Update every entity/concept page X touches (cross-refs, new facts, contradictory notes).
5. Update `index.md` (catalog) — add/refresh entries.
6. Append `log.md` entry: `## [YYYY-MM-DD] <op> | <title>` — one line of what changed.

### QUERY — "answer Q against the wiki"
1. Read `index.md` first; pick candidate pages; drill into them.
2. Synthesize with `[[wikilink]]` citations back to pages.
3. **File valuable answers back** as `queries/YYYY-MM-DD_<slug>.md` + index/log entries —
  explorations must compound, not vanish into chat.

### LINT — "health-check the wiki"
Scan for: contradictions between pages, stale claims, orphan pages (no inbound links),
concepts mentioned but lacking pages, missing cross-refs, data gaps a web search could
fill. Report findings on `overviews/known_debt.md` + a log entry. Suggest new questions.

## Special files

- `index.md` — **content catalog**, organized by category (overviews/entities/concepts/
  sources/queries), each page linked with a one-line summary. Updated on every ingest/query/
  lint. The LLM reads this first for any query.
- `log.md` — **append-only chronology**, entries start `## [YYYY-MM-DD] <op> | <title>`
  so `grep "^## \[" log.md | tail -5` works. Records ingests, queries, lint passes, and
  structural decisions.

## Wiki sessions

On "open the wiki" / "continue the wiki", the LLM: reads SCHEMA.md → reads log.md tail
(what's recent) → reads index.md (what exists) → reports current state and proposes next
actions. On every edit burst, keep pages under ~120 lines; split when a page grows past it.
