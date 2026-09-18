# Plan: tandem remediation-loop implementation

**Status:** approved sequencing reference for future workers. Design docs remain authoritative for contracts; this doc owns milestone order and the packet-access rule.

**Design sources:**

- Community: `docs/design-file-bug-remediation.md` (simplified; PR [community-repair-workshop#72](https://github.com/mingjianjzhang/community-repair-workshop/pull/72))
- Crew: `docs/design-remediation-debugging-agent.md` (simplified; PR [crew#2](https://github.com/mingjianjzhang/crew/pull/2))
- Phase 0: `docs/remediation-loop-gap-map.md`

**Job:** sequence Community filing + Crew Debugging Agent work so workers share one roadmap, and keep bug packets on a single durable root instead of trapped in a disposable worktree.

---

## Packet access decision (locked)

### Rejected: same worktree as the coding agent

Same-worktree spawn is **not** how Crew works today, and it is a poor fit:

- `bin/spawn` always creates `state/worktrees/<id>/` on branch `crew/<id>`; there is no attach-to-existing-worktree flag.
- One worktree can check out only one branch. A Debugging Agent needs its own `crew/<debug-id>` for a stacked fix PR while the coding agent stays on `crew/<feature-id>`.
- Teardown removes the worktree - co-locating packets there couples evidence lifetime to the wrong task.
- Two writers in one tree fight over dirty git state, ports, and AXI sessions.

### Chosen: shared playtest root (single source of truth, no copy)

| Rule | Detail |
| --- | --- |
| SoT location | Crew home `state/playtest/<share-id>/` (mirrors `state/share/<share-id>/`) |
| Writers | Community servers (`serve.mjs` / scenario) whose task has that share |
| Readers | Debugging Agents (and humans) via **absolute path** in the brief |
| Duplication | **None** - do not copy packets into the debug worktree or `.crew/input/` for the happy path |
| Lifetime | Survives coding-agent and debug-agent teardown; manual delete / later retention policy |
| Fallback | `--share none` or no share → keep today's worktree-local `.playtest/` |

**Crew spawn change (Milestone A1):** when a task has a share id, export:

```text
PLAYTEST_DIR=<crew-home>/state/playtest/<share-id>
```

into the worker environment (and document it in `WORKER.md` / brief overlay). Teardown must **not** delete this root.

**Community change (Milestone A2):** `scripts/serve.mjs` already accepts `createServer({ playtestDir })` for tests; wire CLI / `npm start` / scenario to honor `PLAYTEST_DIR` (absolute path only, create if missing, retain path-safety checks). Log the resolved absolute playtest dir at server start.

### Hosted debug session (primary playtest path)

A human may ask the primary to **start a debugging session** for Community with a branch, share, and intent (`fix` or `investigate`) but no packet path. The primary does not block on path discovery: it spawns a Debugging Agent with the same `--share` and a hosted-session brief. The agent starts Community itself on its task `PORT`, honors `PLAYTEST_DIR` from `.crew/env`, and reports the absolute playtest root and loopback URL.

Before investigating, the agent writes a short ready note to task status and `.crew/report.md` (a share update may mirror it) containing:

- `PORT` and the loopback URL;
- the absolute `PLAYTEST_DIR`;
- where filings will land: `$PLAYTEST_DIR/bugs/<id>/` once File bug exists, with recordings under `$PLAYTEST_DIR` today; and
- an instruction for the human to playtest and file bugs against **this** `PORT`, then tell the primary to resume the agent.

The agent then stops with `needs-decision`. It does not poll, invent a reproduction, or diagnose while waiting. After the human files bugs and tells the primary, the primary resumes the task through the Crew answer flow (`bin/answer`). Only then does the agent list/read `PLAYTEST_DIR` (including `bugs/` when present), run the available summary or recording digest, and enter the existing evidence-first gate.

### Packet-path handoff (when evidence already exists)

When a human already has an absolute packet from another task, the primary may use the packet-path mode instead. It puts the absolute packet path in the Debugging Agent brief, e.g. `/…/state/playtest/<share>/bugs/<id>/`. The worker reads it in place and writes digests/reports under its own `.crew/` only; it must not copy the packet into its worktree.

```text
Hosted debug session (primary playtest path)
Human asks primary to start a session (branch / share / fix or investigate)
        ↓
Primary spawns Debugging Agent with --share (no packet path required)
        ↓
Agent starts Community on task PORT with PLAYTEST_DIR
        ↓
Agent reports PORT / URL / absolute PLAYTEST_DIR → needs-decision wait
        ↓
Human playtests and files bugs on that PORT → tells primary → bin/answer
        ↓
Agent reads PLAYTEST_DIR/bugs and runs summary/digest → evidence gate
        ↓
Fix PR when justified, otherwise findings

Alternate: packet path already exists
Human supplies absolute packet → primary spawns with packet-path brief
        ↓
Agent runs bug:summary / supplied replay against the shared path (no copy)
        ↓
Evidence gate → fix PR or findings
```

---

## Goals and non-goals

**Goals**

1. Ship Community File bug v1 (note + optional recording packet) usable in playtest.
2. Adopt Crew Debugging Agent brief/gate so a human can dispatch fix-or-findings against a packet.
3. Make packet access reliable across tasks via the shared playtest root.
4. Keep a single roadmap document workers can follow without rediscovering sequencing.

**Non-goals**

- Building domain/browser deterministic replay in the first tandem slice (Community design PRs 4–5 / Next).
- Watchers, auto-spawn on packet create, supervisors.
- Same-worktree spawn or packet duplication as the access strategy.

---

## Workstreams and dependency order

Two repos move in tandem. Prefer **vertical slices** that leave a working handoff at each milestone.

```text
Milestone A  Shared playtest root + env wiring          [Crew + Community]
Milestone B  Community packet sink + summary            [Community]
Milestone C  File bug UX                                [Community]
Milestone D  Crew Debugging Agent adoption              [Crew]
Milestone E  Integration smoke (human-directed)         [both]
Milestone F  Domain replay / browser replay (Next)      [Community, then Crew gate tighten]
```

### Milestone A - Shared playtest root (unblocks everything)

**Why first:** without this, every later filing is stranded in `state/worktrees/<coding-id>/.playtest/` and vanishes or becomes awkward on teardown.

| PR | Repo | Delivers |
| --- | --- | --- |
| A1 | Crew | `state/playtest/<share>/` convention; spawn exports `PLAYTEST_DIR` when share is set; short `WORKER.md` / README note; teardown does **not** delete playtest root |
| A2 | Community | Honor `PLAYTEST_DIR` in `serve.mjs` / `scenario.mjs` / recording digest default; docs in `PLAYTEST-RECORDINGS.md`; tests with temp absolute dir |

**Acceptance:** two different worktrees on the same share, two servers (different PORTs), both write recordings under the same `PLAYTEST_DIR`; tearing down one worktree leaves files intact.

### Milestone B - Packet sink + summary (Community design PRs 1–2)

| PR | Delivers |
| --- | --- |
| B1 | `/__bugs*` on `serve.mjs`, `bug-packets.mjs`, layout under `$PLAYTEST_DIR/bugs/<id>/`, seal/incomplete, shared capture lock with `/__recording*` |
| B2 | Attach/move recording into packet; `npm run bug:summary`; operational docs |

**Acceptance:** CLI or thin test client can create note-only and recorded packets on the shared root; `bug:summary` prints note + digest; absolute path is stable across worktrees.

### Milestone C - File bug UX (Community design PR 3)

| PR | Delivers |
| --- | --- |
| C1 | Visit File bug page, note/hints, File note / Record / End & file, HUD mark, honest status labels |

**Acceptance:** human files from Settings → Visit on task PORT; UI shows path; packet appears under shared root; legacy Start/Stop still works.

### Milestone D - Crew Debugging Agent adoption (Crew design adoption PR)

| PR | Delivers |
| --- | --- |
| D1 | Short additions to `AGENTS.md`, `WORKER.md`, `README.md`, share README: intake → brief template → evidence-first gate → fix PR or findings; absolute `PLAYTEST_DIR` packet paths; no invented repro |

Depends on A (path convention) and at least B (readable packet). Can land in parallel with C if briefs use CLI-created packets for smoke.

**Acceptance:** primary can spawn either packet-path work (with an absolute packet) or a hosted debug session without a packet path. In hosted mode, the agent starts the server, reports `PORT` + `PLAYTEST_DIR`, waits for an answer, then reads the shared root; in packet-path mode, the worker reads the shared packet without copying. The findings-only path works when evidence is thin.

### Milestone E - Integration smoke

Human-directed, one afternoon. The primary smoke path is hosted:

1. Human asks the primary to start a Community debugging session with a branch, share, and `fix` or `investigate` intent, but no packet path.
2. Primary spawns the Debugging Agent with `--share`; the agent starts Community on its task `PORT`, honoring `PLAYTEST_DIR`.
3. Agent reports `PORT` + loopback URL + absolute `PLAYTEST_DIR`, records where filings/recordings land, and waits for an answer.
4. Human playtests and files a bug against that `PORT`, then tells the primary.
5. Primary uses `bin/answer`; the agent reads the shared root and `bugs/` when present, runs summary/digest, and does not invent repro.
6. Confirm either a narrow fix PR or clean findings according to the evidence gate; teardown must leave the shared root intact.

The packet-path mode remains the alternate smoke path when evidence already exists: primary supplies the absolute packet path at spawn, and the agent reads it without copying.

**Acceptance:** hosted mode starts the server, reports `PORT` + `PLAYTEST_DIR`, waits for the human answer, then reads the shared root; packet-path mode still reads an existing packet and follows the same evidence gate.

| Smoke check | Result | Additional thoughts |
| --- | --- | --- |
| Hosted agent reports task `PORT`, loopback URL, and absolute `PLAYTEST_DIR` | | |
| Human files a bug under `state/playtest/<share>/bugs/<id>/` on that PORT | | |
| Primary resumes the waiting agent through `bin/answer` | | |
| Agent reads shared root without inventing repro or copying packets | | |
| Teardown of feature worktree leaves the shared root intact | | |
| Packet-path alternate reads an existing absolute packet | | |
| Fix PR or findings-only per gate | | |

### Milestone F - Next (after v1 loop works)

Follow Community design PRs 4–5 (domain, then browser replay). Only then tighten Crew gate language from "recording + exact repro" toward requiring relevant lane MATCH when artifacts exist. Separate design touch only if extension points in the simplified Community doc prove insufficient.

---

## Ownership cheat sheet

| Concern | Owner | Authoritative doc |
| --- | --- | --- |
| File bug UX, packet schema v1, `/__bugs*`, summary | Community | `docs/design-file-bug-remediation.md` |
| Shared playtest root + `PLAYTEST_DIR` export | Crew (path) + Community (server honor) | this plan |
| Debugging Agent brief, gate, fix-or-findings | Crew | `docs/design-remediation-debugging-agent.md` |
| Recording spine | Community (existing) | `docs/PLAYTEST-RECORDINGS.md` |
| Cross-task notes | Share board | `.crew/share` |

---

## Brief evidence fields (workers)

Use the mode that matches the handoff. A hosted brief may keep the packet path pending until the human files a bug:

```text
Mode: hosted-debug-session
Packet path: pending
PLAYTEST_DIR: /absolute/.../state/playtest/<share>   # required; worker reports it
PORT: <task PORT>                                    # required; worker reports it
URL: http://127.0.0.1:<PORT>/                         # worker reports loopback URL
Filings: $PLAYTEST_DIR/bugs/<id>/ once File bug exists; recordings under $PLAYTEST_DIR today
Summary: pending until the human files a bug
```

When evidence already exists, use:

```text
Mode: packet-path
Packet path: /absolute/.../state/playtest/<share>/bugs/<id>/
PLAYTEST_DIR: /absolute/.../state/playtest/<share>
Summary: npm run bug:summary -- <packet path>
```

Do **not** instruct workers to copy the packet into their worktree. Read-only open of the SoT path is enough. Agent outputs stay under `.crew/` (and later replay run dirs only if Community defines them under the same shared root).

---

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| `PLAYTEST_DIR` unset → silent worktree-local packets again | Spawn always sets it when share present; Community logs resolved absolute playtest dir at server start |
| Path traversal / symlink escape on shared root | Reuse serve.mjs containment; only Crew-managed directory |
| Stale packets accumulate | Manual delete for v1; optional later `bin` GC is out of scope |
| Debug agent mutates packet | Brief + WORKER: source packet read-only |
| Parallel capture on two tasks same share | Keep one active capture reservation **per server process**; document that two simultaneous Record sessions on one share need care (separate bug ids OK; shared lock is per process, not global) |

Global cross-process capture lock is **not** required for v1; call out as a known limitation when implementing A/B.
