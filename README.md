# Crew

Small, request-driven dispatch on herdr. A primary writes a brief, launches
an isolated worker, and ends its turn. The human supervises through herdr
and asks the primary for updates. There is no polling service or automatic wake-up.

## Remediation / debugging sessions

Crew supports two explicit Debugging Agent intake modes. The role lives in the
brief; it is not a new profile, service, or task kind.

| Mode | Primary intake | Worker handoff |
| --- | --- | --- |
| `hosted-debug-session` | Human asks to start a Community session without a packet; pass the tested `--base`, `--share`, and `fix`/`investigate` intent. | Worker starts Community on task `PORT`, honors `PLAYTEST_DIR`, reports URL/root and filing locations, then waits on `hosted-session-ready`. Human playtests and the primary resumes with `bin/answer`. |
| `packet-path` | Human supplies an absolute existing packet and explicit `fix` or `investigate` intent. | Worker reads the packet at its shared source-of-truth path, without copying it or inventing a reproduction, then applies the evidence gate. |

For hosted mode, the primary spawns once and stops; after the human files a
bug under `$PLAYTEST_DIR/bugs/<id>/` (recordings are under
`$PLAYTEST_DIR` today), the primary answers the waiting task. The worker then
summarizes the evidence and delivers a fix PR or findings. See the
[Debugging Agent design](docs/design-remediation-debugging-agent.md) and
[remediation plan](docs/plan-remediation-loop.md) for the brief contract and
phase details.

## Requirements

- Bash 3.2 or newer, Git with `rev-parse --path-format`, and jq 1.6 or newer.
- herdr 0.8.2, a running server, and a primary inside a herdr-managed pane.
- A project checkout with an `origin` remote and a discoverable default branch.
- The worker CLI installed, authenticated, and its herdr integration current.
- GitHub CLI `gh` authenticated for ship teardown. The landing check needs JSON
  fields that `gh-axi` does not expose; worker delivery may use `gh-axi` normally.
- Python 3.9 or newer only for the local integration tests.

Crew does not install integrations, log into agents, or bypass startup trust
screens. `herdr integration status` shows which integrations need human setup.
CLI help remains available outside herdr; actual commands refuse there.

`harnesses.tsv` contains Claude, Grok, Codex, and Pi permission arguments
and model/effort argument templates. When changing a harness or model, use
the short live smoke below to check model access and launch behavior.
Cursor is omitted until installed and verified. Pi has no approval layer, so
Crew requires an explicit `--unattended-bypass` for that kind. Worktree isolation
is not a security sandbox. Guarded modes may reject an operation rather than
allow it unattended; test the operations your brief needs.

Codex uses workspace-write with network enabled for delivery. Verify that the
installed CLI can write linked-worktree Git metadata, commit, and push under
that sandbox before relying on it for ship tasks. Crew does not silently widen
its filesystem permissions to solve a sandbox restriction.

## First task

Open a herdr pane, then work from this repository:

```sh
cd ~/workspace/crew
mkdir -p state
cat > state/first-scout.md <<'BRIEF'
Kind: scout
Project: ~/workspace/community-repair-workshop
Question: Where does Community allocate preview and scenario server ports?
Read: AGENTS.md, docs/ARCHITECTURE.md
Non-goals: Do not edit project files, install dependencies, or run browser checks.
Delivery: A short .crew/report.md citing the relevant files and current behavior.
BRIEF

bin/spawn --id first-scout \
  --project ~/workspace/community-repair-workshop \
  --kind scout --brief state/first-scout.md \
  --unattended-bypass
```

Spawn prints the worktree, returned herdr workspace ID, agent name, and port
block, then exits. Startup readiness has herdr's bounded timeout; task completion
is never awaited. You can also open a primary CLI in this directory, tell it to
read `AGENTS.md`, and describe the task conversationally.

A `ship` task implements a change. A `scout` task writes findings without
changing project code or making commits. These are task types, not agent kinds.
Use a different ID for every task, including after teardown.

## Worker models

With no model options, spawn uses **Luna, High, through Pi**. The primary
selects a profile from the task's needs; scripts do not guess from brief text.
Task type (`ship` or `scout`) is independent of model profile.

| Profile | Use | Harness | Model | Reasoning effort |
| --- | --- | --- | --- | --- |
| `default` | Unspecified or other work | Pi | GPT-5.6-Luna | High |
| `planning` | Complex planning or adversarial review | Pi | GPT-6-Astra | High |
| `mechanics` | Domain / envelope / greenfield mechanics | Pi | GPT-5.6-Sol | xHigh |
| `routine` | Clear-spec feature implementation in an existing project, not greenfield | Pi | GPT-5.6-Luna | High |
| `new-feature` | Well-specified new feature implementation | Claude | Sonnet 5 | Native default |

OpenAI profiles use Pi, not Codex. Pi has no approval sandbox, so pass
`--unattended-bypass` for `default`, `planning`, `routine`, and `mechanics`. Codex remains
available only via an explicit `--agent codex` custom route.

```sh
# Add to your usual spawn command:
# --profile planning --unattended-bypass
# --profile mechanics --unattended-bypass
# --profile routine --unattended-bypass
# --profile new-feature
# --profile planning --effort xhigh --unattended-bypass
```

`profiles.tsv` owns this mapping, using explicit model IDs rather than moving
aliases. `--model` and `--effort` override the selected profile. `--effort default`
leaves effort to the CLI. Sonnet has no Crew effort override because none was
specified for that profile.

`--base REF` bases the worker on a non-default ref (for stacked feature branches).
Prefer a shared remote branch such as `crew/ipf`; spawn stores `origin/crew/ipf`
when that remote-tracking ref exists, records `pr_base` for PR targeting, and
appends a stacked-delivery note to the brief.

`--share ID` attaches the worker to a Crew-home shared board at
`state/share/<ID>/`, symlinked into the worktree as `.crew/share`. Sibling
workers on the same stack read and write short Markdown notes there (landed
PRs, review reports, contract gotchas). Omitted `--share` with a non-default
`--base` derives the id from the base branch name; use `--share none` to skip.
When basing on a PR head, pass the integration stack id explicitly
(`--share crew-ipf`). Teardown does not delete the share directory; use
`bin/share-retire` when the stack itself is finished.

A shared task also gets the durable Crew-home playtest root
`state/playtest/<ID>/`, exposed to the worker as the absolute `PLAYTEST_DIR`.
Community servers and recording/digest tools should use it as the packet source
of truth; teardown intentionally retains it. With no share (or `--share none`),
`PLAYTEST_DIR` is unset and Community keeps its worktree-local `.playtest/`.

For backward compatibility and explicit harness choices, `--agent KIND` without
`--profile` keeps that CLI's native model and effort defaults. Add `--model` and
`--effort` to set them explicitly. This route opts out of automatic model selection.
An explicit profile and conflicting `--agent` are rejected before worktree creation.

The chosen profile, model, effort, and full launch arguments are stored in task
metadata before launch. `--resume` reuses them, even if defaults later change.
Older tasks without model fields retain their original launch arguments.

## Read results, answer, and remove

```sh
bin/status
bin/status --ack
bin/answer first-scout scope 'Limit the investigation to the preview server.'
bin/answer first-scout scope @/path/to/answer.md
bin/answer first-scout scope --deliver
bin/ext-reply enqueue '{"schema":"crew-ext-reply/v1","id":"r1","type":"answer","taskId":"first-scout","decisionKey":"scope","text":"Limit to preview."}'
bin/ext-reply drain
bin/finish first-scout --decision pr-review 'Merged; primary closeout.'
bin/teardown first-scout
```

Trusted local callers (for example Crew View) may enqueue answers into
`state/ext-reply/inbox/` without `HERDR_ENV`, then trigger
`bin/ext-reply drain` inside a herdr-managed pane (or via `herdr pane run`).
There is no silent Crew poller. See [`docs/ext-reply.md`](docs/ext-reply.md).

`status` reads durable events and one live herdr hint per task without focusing
worker tabs. `--ack` prints the board and saves event counts from that same
snapshot in `state/seen`. All primaries in this home share the cursor. Open
questions and pending answers remain visible after acknowledgement.

Only answer a decision the worker recorded. Keys contain letters, digits,
underscores, or hyphens. An answer is saved atomically before one prompt delivery
attempt. A working, blocked, unknown, or absent agent receives no prompt; the
answer remains pending until you explicitly use `--deliver`. Repeating delivery
can cause another worker turn, so do not retry an already confirmed answer.
A transport failure can also leave delivery uncertain; inspect the pane before
retrying. Crew never retries or wakes the primary on its own.

Use `bin/answer` when the worker must **continue**. For merge/done-only
closeout, use `bin/finish` instead - it never prompts the agent. Farewell-shaped
answer notes are refused (override with `--force` only if you truly need a wake).
See `docs/crew-instruments.md` and `docs/finish-no-agent-closeout.md`.

Teardown archives the record in `data/<id>/` and removes the worktree and local
branch. It refuses dirty worktrees, live or unknown agents, unlanded ship work,
scouts without a report or with outstanding decisions, and **any task whose
`.crew/usage.json` is missing or invalid**. For a squash merge, the merged PR's
head must equal the local tip. If no PR exists, a fresh origin fetch must show
an identical default-branch tree. GitHub lookup errors refuse cleanup. Remote
branches are never removed.

Workers write usage with `.crew/crew-usage` before `done` (schema
`docs/usage-schema.md`: tokens, cache, cost, PR link). Teardown copies the
record into `data/<id>/`, `state/usage/<id>.json`, and appends `state/usage.jsonl`
for session rollups.

`--discard` deliberately bypasses the landing, dirty-tree, and live-worker
checks, but **still requires usage metrics**. Use it only after an explicit
decision to discard that task. It can terminate a worker and destroy
uncommitted project files; the archive preserves Crew records, not a backup of
discarded project changes.

## Files worth reading

| File | Responsibility |
| --- | --- |
| `AGENTS.md` | Primary instructions |
| `WORKER.md` | Instructions copied to every worker |
| `profiles.tsv` | Task-to-harness, model, and effort defaults |
| `harnesses.tsv` | Permission and model argument templates, never shell-evaluated |
| `bin/spawn` | Preflight, port reservation, worktree creation, agent launch |
| `bin/status` | Durable board plus live hints |
| `bin/answer` | Save a human answer and wake the worker to continue |
| `bin/ext-reply` | External reply inbox: enqueue outside herdr; drain/deliver inside |
| `bin/finish` | Zero-token merge/done-only closeout (no agent prompt) |
| `bin/teardown` | Landing checks, archive, and removal |
| `bin/share-retire` | Wrap a finished share board; archive disposable paths |
| `docs/ext-reply.md` | External reply queue contract (`crew-ext-reply/v1`) |
| `docs/crew-instruments.md` | Post-wave brief/closeout instruments |
| `lib/common.sh` | Shared locking, JSON metadata, Git identity checks, log reduction |
| `lib/crew-status` | Tiny append helper copied into each worktree |
| `lib/crew-usage` | Writes validated `.crew/usage.json` (`crew-usage/v1`) |
| `docs/usage-schema.md` | Required worker usage / cost log format |

Live JSON metadata lives in `state/<id>.meta`. Worktrees live under
`state/worktrees/<id>/`, each with an ignored `.crew/` directory containing the
brief, overlay, events, answers, report, and append helper. Spawn adds `/.crew/`
to the project's shared Git exclude; it does not edit the project's `.gitignore`.
`state/` and `data/` are local and excluded from this repository. Back them up if
you need durability beyond this disk. Do not move the Crew home while tasks are live.

## Ports and interrupted launches

Spawn acquires a short, fail-fast allocation lock, chooses an unused block of
10 ports from 5100 upward, and atomically writes its reservation before releasing
the lock. Agent startup happens afterward. Another simultaneous command may
report `Busy`; rerun it when the first command returns. There is no lock polling.
A second lock prevents simultaneous mutations of the same task.

Reservations survive failed launches and remain allocated until teardown.
The allocator coordinates tasks in this Crew home; it does not bind OS sockets
or coordinate unrelated applications or separate Crew homes.

The worker receives `PORT`, `CREW_PORT_BASE`, and `CHROME_DEVTOOLS_AXI_SESSION`
(the task id) through its pane shell and its brief. `.crew/env` provides the
same exports if the harness filters tool-shell environment variables. Additional
servers use offsets within the assigned block. Browser checks should keep that
AXI session so each worker gets its own bridge/Chrome.

`bin/teardown` best-effort stops the task's `chrome-devtools-axi` session and
kills listeners on the reserved ten-port block before removing the worktree.
This is programmatic cleanup; workers should not spend turns on shutdown.

```sh
bin/spawn --resume first-scout
```

Resume continues a partial creation or setup without making another worktree.
A startup blocked by trust or login resumes only after you settle it in herdr.
A dispatched task is never prompted again by `--resume`.

If a process dies across initial prompt submission, the phase remains
`dispatching`: delivery is uncertain. Inspect the saved `state/<id>.prompt.json`
and the pane. Once a human has confirmed what happened, repair the metadata
phase to `dispatched` if delivered, or `ready` if definitely not delivered,
using an atomic JSON file replacement. Only then resume. This intentionally
requires judgment rather than risking duplicate work.

A failed startup's `failed` event remains visible according to the draft's
terminal-event precedence until the worker records a newer `done` or `failed`.
Read the spawn phase and live hint alongside it during recovery.

Normal exits release locks. A forced kill can leave a lock directory with an
`owner` file containing PID and start time. Confirm the command is no longer
running before removing that owner file and empty lock directory. Never remove
an active lock. An incomplete spawn with no worktree or branch can be released
with an explicitly authorized `bin/teardown <id> --discard`.

A missing worktree is `lost`; a server error is `unknown`, not proof that an agent
is gone. Crew refuses mutations when returned workspace identity no longer
matches the recorded checkout, including after a server reset or session change.

## Checks

```sh
make check
```

This checks Bash syntax and runs CLI integration tests with real temporary Git
repositories and a fake herdr/GitHub boundary. Tests exercise isolation, port
allocation, partial failure recovery, decision delivery, unread status, and
safe cleanup. They do not launch models or touch your herdr session.

## Brief live smoke plan

Run these from herdr, using disposable tasks. No extended playtesting is needed.
The fake-boundary tests cannot establish live CLI readiness, permissions, or
whether a prompt is accepted by a particular harness.

| Check | Result | Additional thoughts |
| --- | --- | --- |
| Launch the scout above; primary ends its turn and worker writes its report without approval stalls | | |
| Launch planning, routine/default, and new-feature profiles; confirm the CLI shows the requested model and effort | | |
| Repeat with another installed worker kind and another primary CLI | | |
| Confirm a worker's tool shell sees its assigned `PORT` and `CREW_PORT_BASE` | | |
| Ask a scout brief to record a decision and stop; answer from the primary and confirm continuation | | |
| Confirm a working worker's answer stays pending until an explicit later delivery | | |
| Spawn two disposable tasks, launch their preview servers, and confirm distinct port blocks | | |
| For ship use, verify commit and push permissions, required checks, and teardown of a squash-merged tip | | |
| Read the board after closing test workers; durable results remain and missing agents show gone | | |

Browser inspection belongs in visual work when practical, and whenever a brief
requires a browser check. Workers use `chrome-devtools-axi` on the task `PORT`
for those checks. Ordinary functionality otherwise gets the project's required
checks and the brief's verification, without additional browser playtesting by
default. Workers report what they actually checked and any meaningful limitation.
