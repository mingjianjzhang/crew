# Crew worker usage log (`crew-usage/v1`)

Every worker must write `.crew/usage.json` before the primary can tear the task
down (including `--discard`, except unused reservations that never prepared a
checkout). Prefer the `.crew/crew-usage` helper; it validates and writes the file.

On teardown, Crew archives the file under `data/<id>/usage.json` and appends one
JSON line to `state/usage.jsonl` for session rollups.

## Schema

```json
{
  "schema": "crew-usage/v1",
  "taskId": "pt-spots",
  "kind": "ship",
  "harness": "claude",
  "model": "claude-sonnet-5",
  "effort": "max",
  "recordedAt": "2026-09-17T03:00:00Z",
  "source": "harness",
  "pr": {
    "url": "https://github.com/org/repo/pull/55",
    "number": 55
  },
  "tokens": {
    "input": 1200000,
    "output": 45000,
    "cachedRead": 900000,
    "cacheCreation": 80000,
    "reasoning": 12000
  },
  "costUsd": 12.34,
  "notes": "optional one-line context"
}
```

## Field rules

| Field | Required | Notes |
| --- | --- | --- |
| `schema` | yes | Must be `crew-usage/v1` |
| `taskId` | yes | Must match the Crew task id |
| `kind` | yes | `ship` or `scout` |
| `harness` | yes | e.g. `claude`, `pi`, `codex`, `grok` |
| `model` | yes | Model id string used for the run |
| `effort` | no | Effort / thinking level when known |
| `recordedAt` | yes | UTC ISO-8601 timestamp |
| `source` | yes | How numbers were obtained (see below) |
| `pr` | ship preferred | Object with `url` (https) and optional `number`; `null` for scouts or when no PR |
| `tokens.input` | yes | Non-negative number (gross input if your harness reports it that way) |
| `tokens.output` | yes | Non-negative number |
| `tokens.cachedRead` | preferred | Cache hits / cached read tokens; use `0` if unknown |
| `tokens.cacheCreation` | preferred | Cache write / creation tokens; use `0` if unknown |
| `tokens.reasoning` | preferred | Hidden/reasoning tokens when reported; else `0` |
| `costUsd` | preferred | Number or `null` if the harness does not expose $ |
| `notes` | no | Single line, no newlines |

### `source` values

| Value | When |
| --- | --- |
| `harness` | Copied from the agent CLI / session usage API |
| `estimated` | Derived from partial counters or screenshots |
| `unavailable` | Harness exposed nothing usable; token fields may be `0` with an explanation in `notes` |

Workers should prefer `harness`. Use `unavailable` only after a genuine attempt to
read the run's usage. Teardown accepts any of the three values if the schema is
valid - the gate is "emitted a usage record", not "perfect billing data".

## Helper

```sh
.crew/crew-usage --input 1200 --output 300 --cached-read 900 --cost-usd 0.42 \
  --pr-url https://github.com/org/repo/pull/55 --pr-number 55 \
  --source harness
```

Omit unknown optional flags; the helper fills zeros / nulls and reads task id,
kind, harness, model, and effort from `.crew` metadata when present (or from
environment / brief assignment line).

### Claude `--auto`

For Claude workers, prefer letting the helper discover and price the session
itself (no per-agent jq or arithmetic):

```sh
.crew/crew-usage --auto
# or, with no token flags when harness is claude / CLAUDE_CODE_SESSION_ID is set:
.crew/crew-usage --pr-url https://github.com/org/repo/pull/55 --pr-number 55
```

`--auto` resolves the session JSONL at
`~/.claude/projects/<slug-of-$PWD>/$CLAUDE_CODE_SESSION_ID.jsonl` (slug:
replace `/`, `.`, and spaces with `-`), dedups `message.usage` by
`message.id`, sums input/output/cache tokens, and sets `costUsd` from
Anthropic list rates (platform.claude.com), including per-message model rates
for auxiliary calls. Pass `--transcript PATH` to override discovery. If a
model has no rate row, tokens are still written and `costUsd` stays `null`.
