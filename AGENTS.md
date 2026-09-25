# Crew

Crew dispatches work to isolated Git worktrees through herdr.
The human supervises. The primary acts on requests and then stops.
These primary instructions apply in the Crew home. Worker checkouts
follow `.crew/WORKER.md` and their project instructions.

## Starting a session

Read the task board with `bin/status --ack`.
Report open decisions, pending answers, and tasks needing attention.
Report the unread done or failed events printed by the board.
`--ack` advances the shared `state/seen` cursor for that snapshot.
If `bin/status` or `bin/ext-reply status` shows queued external replies, run `bin/ext-reply drain` (and `bin/ext-reply deliver` when items are pending-delivery).
Do not add a background poller; apply is request-driven inside herdr (including UI-triggered `herdr pane run` of drain).

Never wait for workers, poll their state, or arrange a wake-up.
Do not focus worker panes; preserve herdr's unread indicators.

Outside a herdr-managed pane, read state and task files directly.
Do not run Crew scripts that mutate tasks.
They require `HERDR_ENV=1`.
`bin/ext-reply enqueue` and `bin/ext-reply status` are the exception: they only touch `state/ext-reply/` and may run outside herdr so a local UI can queue answers.
Drain and deliver still require herdr.
See `docs/ext-reply.md`.

## Dispatching work

Resolve the project path, task type, and worker profile.
Classify each task as `ship` (implementation that changes the project)
or `scout` (investigation that produces findings without project changes).
These are Crew task types, not commands, skills, or agent kinds.

Choose a worker profile based on the work:
- `planning`: high-level project planning, Grok 4.5 with High reasoning (Grok).
- `adversarial`: adversarial review, GPT-6-Astra with High reasoning (Pi).
- `mechanics`: domain / rules / envelope / greenfield mechanics implementation,
  GPT-6-Sol with High reasoning (Pi).
- `artwork`: artwork/UI design and art/UI integration, Opus 5.5 with xHigh
  reasoning (Claude).
- `routine`: routine feature implementation with clear specs in an existing
  project, not greenfield, GPT-6-Luna with High reasoning (Pi).
- `default`: everything else, GPT-6-Luna with High reasoning (Pi).

Pi profiles (`default`, `adversarial`, `routine`, `mechanics`) need
`--unattended-bypass` (Pi has no approval sandbox). Grok/`planning` and
Claude/`artwork`/`new-feature` do not need that flag.

Pass `--profile <name>` to spawn. Omission defaults to GPT-6-Luna High via Pi.
Do not infer complex planning merely from the `scout` task type.
Sonnet uses its native effort setting unless the human specifies one.
Honor explicit model or effort overrides with `--model` and `--effort`.
An explicit `--agent` without a profile opts out of profile defaults; use
that native route only when the human requests a different harness.
When stacking work onto a long-lived feature branch, pass `--base <ref>`
(for example `--base crew/ipf`). Spawn resolves `origin/<ref>` when present,
bases the worktree there, and appends a brief note to open the PR against
that branch instead of the default branch.

Write a brief with:
- The outcome or question.
- Explicit non-goals.
- Acceptance criteria and required checks.
- Relevant project instructions.
- Expected delivery and any human browser checks.
When a brief requires a browser check, say to use `chrome-devtools-axi`
on the task `PORT` (WORKER.md already requires that tool).

Keep briefs lean for context cost (see `docs/context-budget.md`).

1. **Zero-Token Closeout** - On human merge (or any done-only closeout):
   use `bin/finish`, never `bin/answer`. Finish resolves the decision,
   appends done, and teardowns **without prompting the worker**. Tip-sync
   the worktree to the merged head first when needed. `bin/answer` refuses
   farewell-shaped notes unless `--force` plus an explicit continue reason.


Call `bin/spawn` with the brief.
Optionally print `bin/status`, report the dispatch, and end your turn.

Prefer workers for parallel or substantial work and work that should
be isolated from the user's checkout. Small project changes may be
completed directly when authorized.

## Reading results and answering decisions

Status files are the durable record. herdr state is a live hint.
A herdr agent marked done has stopped working; only a done event in
the task log means its deliverable is complete.

When the human supplies a decision that requires the **worker to continue**,
use `bin/answer` (fix PR, redesign, etc.).
If delivery remains pending, report why. Retry only on a later request.
Never send other prompts, steering messages, or keystrokes to workers.
Do not use `bin/answer` for merge/done-only notes ("merged", "emit done",
"refresh usage") - that is the farewell tax. `bin/answer` refuses those
shapes; rewrite with an explicit continue reason or use `bin/finish`.

When the human has **merged** (or otherwise wants closeout with no further
worker work), use `bin/finish ID [--decision KEY] NOTE` instead of answering.
Finish never calls `herdr agent prompt`. It requires an existing valid
`.crew/usage.json`, appends done, and runs teardown. Do not wake Opus,
Astra, Sol, Grok, or any other model just to emit done/usage.

## Removing tasks

Prefer `bin/finish` for merge/done-only closeout (zero agent tokens).
Use `bin/teardown` directly when the task is already done in the status
log. Do not remove worktrees or branches manually.
Never pass `--discard` without an explicit human instruction to discard
that task in the current conversation.

Teardown requires a valid `.crew/usage.json` (`crew-usage/v1`) even with
`--discard` (unused reservations with no checkout are the only exception).
If a finished worker omitted usage, have it write metrics with
`.crew/crew-usage` before teardown, or write an `unavailable` record
yourself only when the human authorizes collecting zeros. Rollups land in
`state/usage.jsonl` and `state/usage/<id>.json` (gitignored with `state/`).
See `docs/usage-schema.md`.

## Boundaries

Follow the project's own instructions and the brief's delivery rules.
Use no-mistakes only when the human requests it.
Do not merge worker branches from the primary. A worker may merge a PR
only when a human operator instructs that directly in the brief or via
`bin/answer`.

Keep Crew small: no supervisors, polling loops, automatic retries,
harness extensions, or additional orchestration layers.
The external-reply inbox is drained only on explicit `bin/ext-reply drain` (or deliver) under herdr — never by a silent Crew watcher.
