# Primary finish (zero-token closeout)

Instrument #1 from `docs/crew-instruments.md`.

## Problem

`bin/teardown` itself is shell-only and costs **$0** model tokens.

The ~$0.60 burn on `community-demo-orb2` after merge came from **`bin/answer`**: it always runs `herdr agent prompt` so the worker can "read the decision and continue." For a merge/done-only note that only asks for usage refresh + done, Astra still reloaded ~450k cache tokens and wrote a small completion - about **$0.58** on that ship (usage rose ~$7.20 → ~$7.78).

High-cost models must not pay for a farewell turn. That is a process bug
with a receipt.

## Fix

`bin/finish ID [--decision KEY] [--discard] NOTE`

1. Requires existing valid `.crew/usage.json` (no agent refresh).
2. Optionally writes `.crew/answers/<KEY>.md` and appends `resolved` **without** `herdr agent prompt`.
3. Appends `done` with NOTE.
4. Runs `bin/teardown`.

Primary tip-syncs merged ship tips **before** finish when local HEAD ≠ merged `headRefOid`.

Use `bin/answer` only when the worker must **continue** (code fix, redesign, hosted-session resume).

## Guardrail

`bin/answer` refuses notes that look like done-only closeout (merged /
emit done / refresh usage / goodbye / close out) unless:

- the note also names an explicit continue reason (fix, redesign, resume,
  "worker must continue", …), or
- you pass `--force` (still wakes the agent; prefer finish when you can).

`--deliver` of a previously saved farewell-shaped answer is also refused
without `--force`.
