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

Never wait for workers, poll their state, or arrange a wake-up.
Do not focus worker panes; preserve herdr's unread indicators.

Outside a herdr-managed pane, read state and task files directly.
Do not run Crew scripts. They require `HERDR_ENV=1`.

## Dispatching work

Resolve the project path, task type, and worker profile.
Classify each task as `ship` (implementation that changes the project)
or `scout` (investigation that produces findings without project changes).
These are Crew task types, not commands, skills, or agent kinds.

Choose a worker profile based on the work:
- `planning`: complex planning or adversarial review, GPT-6-Astra with High
  reasoning (Pi).
- `mechanics`: domain / envelope / greenfield mechanics implementation,
  GPT-5.6-Sol with xHigh reasoning (Pi).
- `routine`: routine feature implementation with clear specs in an existing
  project, not greenfield, Luna with High reasoning (Pi).
- `new-feature`: well-specified new feature implementation, Sonnet 5 (Claude).
- `default`: everything else, Luna with High reasoning (Pi).

OpenAI profiles (`default`, `planning`, `routine`, `mechanics`) use Pi, not Codex.
Pass `--unattended-bypass` whenever spawning those profiles (Pi has no
approval sandbox). Claude/`new-feature` does not need that flag.

Pass `--profile <name>` to spawn. Omission defaults to Luna High via Pi.
Do not infer complex planning merely from the `scout` task type.
Sonnet uses its native effort setting unless the human specifies one.
Honor explicit model or effort overrides with `--model` and `--effort`.
An explicit `--agent` without a profile opts out of profile defaults; use
that native route only when the human requests a different harness.
When stacking work onto a long-lived feature branch, pass `--base <ref>`
(for example `--base crew/ipf`). Spawn resolves `origin/<ref>` when present,
bases the worktree there, and appends a brief note to open the PR against
that branch instead of the default branch.
Pass `--share <id>` so siblings share one board (symlinked as `.crew/share`).
If `--share` is omitted and `--base` is not the default branch, spawn derives
the share id from that base name (`crew/ipf` → `crew-ipf`). When basing on a
PR head instead of the integration branch, pass the stack share explicitly
(for example `--base crew/ipf-pr2a0 --share crew-ipf`). Use `--share none` to
disable. Workers must not poll the share; the primary still coordinates.

Write a brief with:
- The outcome or question.
- Explicit non-goals.
- Acceptance criteria and required checks.
- Relevant project instructions.
- Expected delivery and any human browser checks.
When a brief requires a browser check, say to use `chrome-devtools-axi`
on the task `PORT` (WORKER.md already requires that tool).

Keep briefs lean for context cost (see `docs/context-budget.md`).
Crew instruments after the isometric-demo wave (`docs/crew-instruments.md`):

1. **Zero-Token Closeout** - On human merge (or any done-only closeout):
   use `bin/finish`, never `bin/answer`. Finish resolves the decision,
   appends done, and teardowns **without prompting the worker**. Tip-sync
   the worktree to the merged head first when needed. `bin/answer` refuses
   farewell-shaped notes unless `--force` plus an explicit continue reason.
2. **Anti-Goal Block** - Contested UI implement briefs after a visual scout
   must list concrete anti-goals (footprint, must-not-obscure, banned chrome
   families). Scout approval alone does not carry constraints.
3. **Edit-Map Brief** - Name exact files/line ranges and call sites; ban
   whole-file discovery-cat of `app.js` / DEMO / sibling modules. Weak
   "modules you need" allowlists are non-compliant.
4. **Thin TDD Contract** - Before expensive ships, publish must-stay-green
   cites, tests to add, run commands, and seam refs. Worker starts
   red/green, not archaeology.
5. **Taste Freeze Gate** - Do not spawn Astra/Fable xhigh for contested
   chrome/plate until an owner wireframe or plate-ref pack exists on the
   share board. Ban Imagine comps as apply briefs; escalate to xhigh only
   when a written fidelity gate fails.

Also: pin an allowlist of files/sections; do not say "read COMMON / UX /
ARCHITECTURE in full" unless that doc is the task. Defer browser checks
to a short end pass; Rules-only ships omit AXI unless the happy path is
truly UI. Prefer a new short follow-up task over extending a long session.

Call `bin/spawn` with the brief.
Optionally print `bin/status`, report the dispatch, and end your turn.

Prefer workers for parallel or substantial work and work that should
be isolated from the user's checkout. Small project changes may be
completed directly when authorized.

## Remediation and debugging sessions

For an explicit human debugging request, resolve the intent before spawning:

- **Hosted session:** if the human asks to **start a debugging session** for
  Community without a packet path, use `Mode: hosted-debug-session`. Keep the
  packet path `pending`, pass the tested branch/head and share, and let the
  worker start Community on its task `PORT` with the shared `PLAYTEST_DIR`.
- **Packet path:** if an absolute packet already exists, use
  `Mode: packet-path` and put that source-of-truth path in the brief. The worker
  reads it in place; do not copy it into the worktree.
- Resolve `fix` (`ship`) versus `investigate` (`scout`). A bare packet path is
  not authorization to fix; ask when the intent is unclear.

Hosted sessions use one spawn and then stop. For example:

```sh
bin/spawn --id community-debug-session1 \
  --project /absolute/path/to/community-repair-workshop \
  --kind ship --profile mechanics --unattended-bypass \
  --base crew/ipf --share crew-ipf \
  --brief state/community-debug-session1.md
```

The brief must record the expected tested SHA, intent, scope, share, and
`Mode`; use the design's thin brief contract rather than inventing fields.
After the hosted worker reports `PORT`, URL, absolute `PLAYTEST_DIR`, filing
locations, and `needs-decision` key `hosted-session-ready`, the human
playtests and files bugs on that port. Resume **only** through the answer flow,
for example `bin/answer community-debug-session1 hosted-session-ready 'Bugs filed; continue.'`
Do not poll, focus the pane, or send an out-of-band prompt. The worker then
reads `PLAYTEST_DIR/bugs` and runs the available summary/digest. See
[`docs/design-remediation-debugging-agent.md`](docs/design-remediation-debugging-agent.md)
and [`docs/plan-remediation-loop.md`](docs/plan-remediation-loop.md).

## Reading results and answering decisions

Status files are the durable record. herdr state is a live hint.
A herdr agent marked done has stopped working; only a done event in
the task log means its deliverable is complete.

When the human supplies a decision that requires the **worker to continue**,
use `bin/answer` (fix PR, redesign, hosted-session resume, etc.).
If delivery remains pending, report why. Retry only on a later request.
Never send other prompts, steering messages, or keystrokes to workers.
Do not use `bin/answer` for merge/done-only notes ("merged", "emit done",
"refresh usage") - that is the farewell tax. `bin/answer` refuses those
shapes; rewrite with an explicit continue reason or use `bin/finish`.

When the human has **merged** (or otherwise wants closeout with no further
worker work), use `bin/finish ID [--decision KEY] NOTE` instead of answering.
Finish never calls `herdr agent prompt`. It requires an existing valid
`.crew/usage.json`, appends done, and runs teardown. Do not wake Fable,
Astra, or any other model just to emit done/usage.

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

## Retiring a share board

Task teardown archives the worker under `data/<id>/` and removes the
worktree. It does **not** retire `state/share/<share-id>/` or
`state/playtest/<share-id>/` (playtest is the packet source of truth).

When a stack or project wave is done, wrap the share explicitly:

1. Tear down every live task that still references that share.
2. `bin/share-retire SHARE_ID --init` writes `CURRENT.md` plus a suggested
   `RETIRE.manifest` (study/frames/evidence/shots, `updates/`, log junk).
3. Edit the manifest so packet trees and owner freezes stay on the board.
4. `bin/share-retire SHARE_ID` moves listed paths to
   `data/share-retired/SHARE_ID/<utc>/` and appends `RETIRED.md`.

Primary session default for a finished stack: read `CURRENT.md` (and
`bin/status --ack`), not the whole share archaeology.

## Boundaries

Follow the project's own instructions and the brief's delivery rules.
Use no-mistakes only when the human requests it.
Do not merge worker branches from the primary. A worker may merge a PR
only when a human operator instructs that directly in the brief or via
`bin/answer`.

Keep Crew small: no supervisors, polling loops, automatic retries,
harness extensions, or additional orchestration layers.
The one exception is `bin/lane watch` (`docs/lane-rules-completion.md`):
one process, started by `bin/lane assign` and stopped from `bin/lane cancel`.
It may subscribe to herdr pane events and stall-tick `herdr agent get`
for its own lane panes. It does not focus panes, prompt workers, answer,
finish, or merge.
