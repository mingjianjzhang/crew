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

**Handoff:** primary puts the absolute packet path in the Debugging Agent brief, e.g. `/…/state/playtest/crew-ipf/bugs/<id>/`. Worker reads in place; writes digests/reports under its own `.crew/` only.

```text
Human / coding agent playtests (PORT from that task)
        ↓
serve.mjs writes sealed packet → state/playtest/<share>/bugs/<id>/   ← SoT
        ↓
Primary spawns Debugging Agent (new worktree, --base tested head, same --share)
        ↓
Brief: Packet path = absolute SoT path (no copy)
        ↓
Agent runs bug:summary / later replays against that path; code edits stay in its worktree
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

**Acceptance:** primary can spawn a ship/scout with packet path; worker reads shared packet without copying; findings-only path works when evidence is thin.

### Milestone E - Integration smoke

Human-directed, one afternoon:

1. Feature worker on a share files a bug while reproducing on its PORT.
2. Primary spawns Debugging Agent with `--base` tested head, same `--share`, absolute packet path.
3. Confirm summary runs; agent does not invent repro; either narrow fix PR or clean findings.
4. Teardown feature worker; confirm packet still on shared root; debug agent still readable.

| Smoke check | Result | Additional thoughts |
| --- | --- | --- |
| File bug lands under `state/playtest/<share>/bugs/<id>/` | | |
| Debug agent reads absolute path without copy | | |
| Teardown of feature worktree leaves packet intact | | |
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

Always prefer:

```text
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
