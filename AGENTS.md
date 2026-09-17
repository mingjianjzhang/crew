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

Call `bin/spawn` with the brief.
Optionally print `bin/status`, report the dispatch, and end your turn.

Prefer workers for parallel or substantial work and work that should
be isolated from the user's checkout. Small project changes may be
completed directly when authorized.

## Reading results and answering decisions

Status files are the durable record. herdr state is a live hint.
A herdr agent marked done has stopped working; only a done event in
the task log means its deliverable is complete.

When the human supplies a decision, use `bin/answer`.
If delivery remains pending, report why. Retry only on a later request.
Never send other prompts, steering messages, or keystrokes to workers.

## Removing tasks

Use `bin/teardown`; do not remove worktrees or branches manually.
Never pass `--discard` without an explicit human instruction to discard
that task in the current conversation.

## Boundaries

Follow the project's own instructions and the brief's delivery rules.
Use no-mistakes only when the human requests it.
Do not merge worker branches from the primary. A worker may merge a PR
only when a human operator instructs that directly in the brief or via
`bin/answer`.

Keep Crew small: no supervisors, polling loops, automatic retries,
harness extensions, or additional orchestration layers.
