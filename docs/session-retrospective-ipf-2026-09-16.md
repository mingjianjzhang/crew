# Session retrospective: IPF via Crew (brutal)

**Session:** primary Grok Build `01a0ac66-…0e45` in Crew home  
**Wall clock (usage turns):** ~3.25 hours (`2026-09-16 22:52` → `2026-09-17 02:07` UTC)  
**Project outcome:** Invention / Production / Factions stack on `crew/ipf` through PR #54; PR6 (librarian hook-up) in flight  
**This document:** primary + Crew performance only. Worker model bills are **not** in the primary `usage.json`.

---

## Executive scorecard

| Dimension | Grade | One-line |
| --- | --- | --- |
| Delivery of the PR plan | **B+** | 10 stacked PRs (#45–#54) landed on `crew/ipf` in one evening; design DAG mostly honored |
| Cost efficiency (primary) | **D** | ~**$30** and **16.3M input tokens** (~88% cache) for an orchestrator that barely edits code |
| Time efficiency (human) | **C+** | Parallel waves helped; ~half of user turns were cleanup, discard, model, or teardown ops |
| Primary judgment | **C** | Strong wave drafting and stack discipline; weak on model/CLI readiness, merge ownership, and permission reality |
| Crew product fitness | **B-** | Spawn/base/share/teardown matured mid-flight; still missing cost visibility, model validation, and merge affordances |
| Adversarial review ROI | **A-** | Astra/Sol reviews on #45/#46 caught real foundation bugs before parallel tracks amplified them |

**Bottom line:** Crew *worked* as a multi-agent factory for a well-specified PR DAG. The primary was an expensive, chatty air-traffic controller. Too much money and attention went into replaying context, recovering from preventable spawn failures, and paying ultracode rates for last-mile merges the harness could not finish.

---

## What actually shipped

On `origin/crew/ipf` (relative to `main`): **26 commits**, PRs **#45–#54** merged:

| PR | Topic | Notes |
| --- | --- | --- |
| #45 | Shared contracts (PR1) | Adv review → fix-forward → merge |
| #46 | v4 envelope (PR2a0) | Adv review → Luna fix → merge |
| #47–#49 | Visuals (PR2b/3b/4b) | Parallel Fable; Luna merge coordinator |
| #50–#51 | Factions + invention mech | Sol; ordered merge onto stack |
| #52 | Production mech (PR3a) | Sol |
| #53 | Invention hook-up (PR5) | Sol |
| #54 | Factions hook-up (PR7) | Sol; conflicted; human merged after Sonnet ultracode resolve |

**Archived Crew tasks with `ipf*` prefix: 19.** Roughly **1.9 tasks per merged PR** once you count wrong-model discards, CLI respawns, adv scouts, fix-forward, viz-merge, and the #54 resolver. That overhead ratio is the real tax of the session.

Mid-session Crew product work (good, but stolen from the game):

- `--base` / `--share` shared board (`state/share/crew-ipf`)
- Teardown `release-resources.sh` (port block kill + task-scoped `chrome-devtools-axi` stop)
- Profile fixes (`openai-codex/` prefix), `mechanics` profile, docs/WORKER updates

---

## Primary cost anatomy (Grok only)

From session `usage.json` (primary model `grok-4.5-build`):

| Metric | Value |
| --- | --- |
| Turns / model calls | 31 / 154 |
| Gross input | **16,262,233** |
| Cached read | **14,283,136** (**87.8%**) |
| Fresh input | **1,979,097** |
| Output / reasoning | 97,001 / 60,872 |
| Est. primary $ | **~$30.11** (`costUsdTicks / 1e9`) |

### Brutal reading of the millions

The “millions of input tokens” are mostly **the same session transcript being replayed under cache**. That is not free: top turns still cost $1–$3 each because fresh prefixes and tool I/O keep moving.

Heaviest turns by estimated $:

| Turn | ~$ | Fresh in | Likely work (from timeline) |
| --- | --- | --- | --- |
| 27 | 3.22 | 153k | Wave-3 / hook-up orchestration, large context |
| 4 | 2.25 | 106k | Early PR1 / feature-branch setup |
| 18 | 2.04 | 119k | Share-board design + mech spawn wave |
| 30 | 1.74 | 127k | Token breakdown / wrap-adjacent |
| 28 | 1.55 | 171k | Ultracode #54 resolve spawn + docs brief |

**Missing from this bill:** every Pi/Claude/Fable/Sol/Astra/Sonnet worker. Ultracode on #54 alone may dominate primary spend. **Crew currently cannot answer “what did this stack cost?”** That is a product failure for cost-efficient use.

---

## Human attention tax (user-query timeline)

Roughly **30 supervisory messages** in the compacted session. A large fraction were not “build the next pillar” - they were operational corrections:

1. **Discard wrong model** (`openai-codex/` prefix missing) - primary shipped a broken Pi launch on first try  
2. **Feature branch, not main** - primary nearly aimed incremental merges at `main` until corrected  
3. **Discard three visuals** - CLI version issue; full parallel wave paid twice  
4. **Explain adv findings / spawn fix / dismiss extras** - review loop worked, but needed explicit human pacing  
5. **Invent share board** - correct product gap; implemented mid-session while workers were live  
6. **Dismiss / nominate merge reviewer / leave brief only** - primary over-eager to spawn scouts  
7. **Pane still open after teardown** - herdr/Crew lifecycle leak in UX  
8. **Ports + chrome-devtools-axi leaks** - fixed programmatically only after human noticed waste  
9. **Ultracode merge resolver** - did conflict/docs work, then **blocked on `gh pr merge` permission**; human merged and discarded  
10. **Token breakdown ask** - symptom that spend felt opaque and high  

Crew’s philosophy (“primary acts, then stops; human supervises”) is sound. In practice the human became the **retry loop, permission layer, and cost conscience** the tools lack.

---

## What the primary did well

1. **Respected the design DAG** after the feature-branch correction: PR1 → PR2a0 → parallel viz/mech → hook-ups; PR6 held until #54.  
2. **Adversarial reviews on foundations paid off.** #45/#46 `request-changes` findings (sparse vs complete material maps; live XP copy; passive catch-up scaling; stale manual plan) were worth a scout each.  
3. **Brief quality improved.** Wave2/wave3 briefs were reusable, scoped, and named non-goals (especially “do not merge to main”).  
4. **Stacked delivery model** (`crew/ipf` + later `--share`) matched the problem better than PR-to-main.  
5. **Stopped polling** per AGENTS.md - did not burn turns waiting on workers.

## What the primary did poorly

1. **Shipped the first worker with a known-bad model string class.** One smoke (`pi` model list vs `profiles.tsv`) would have saved a discard cycle and human interrupt.  
2. **Asked multi-option “how should we start?”** after the human already said begin implementing. That is classic primary over-clarification on a clear request.  
3. **Defaulted toward more agents** (extra scouts, merge reviewers) when the human often wanted a brief or a single nominated pane.  
4. **Treated Crew product gaps as chat topics for too long** (ports, axi, share) before writing the small scripts - then wrote them under pressure. Better: spike Crew affordances in a dedicated hour *before* a 10-PR factory run.  
5. **Ultracode for a merge the harness could not complete.** Conflict resolution + docs dedupe was valuable; paying ultracode *and* leaving merge to the human (permission classifier) was a bad bet. A cheaper model + human `gh pr merge` would have matched reality.  
6. **No running cost ledger.** When the human asked about millions of tokens, the answer was available in `usage.json` the whole time - but never surfaced proactively as “orchestration is at $X; consider ending the primary session and dispatching from a fresh one.”  
7. **Context bloat as operating mode.** 16M gross input for dispatch is indefensible long-term. Compaction helped once; the primary still re-derived stack state instead of treating `state/share/crew-ipf` + `bin/status` as the only sources of truth.

---

## Crew product: strengths and gaps exposed

### Strengths

- Worktree isolation + port blocks + profiles made true parallel visuals/mechanics possible.  
- `--base` / `pr_base` stacking is the right primitive for “feature branch contains the epic.”  
- Shared board (`--share`) is the correct answer to cross-worktree amnesia - once workers actually write updates (they mostly did for landed PRs).  
- Teardown resource release (ports + axi session) closes a real money/attention leak.

### Gaps (ordered by how much they hurt this session)

1. **No spawn-time model validation** against the live harness. Wrong Pi model = silent stuck agent.  
2. **No aggregated $ / token view across primary + workers.** You cannot steer Luna vs Sol vs Fable vs Sonnet ultracode without it.  
3. **Merge/permission story is dishonest under `auto`.** Workers open PRs fine; finishing merges often needs human `gh` / classifier exemptions. Briefs that say “merge into `crew/ipf`” set workers up to `needs-decision` at the goal line (#54).  
4. **Dismiss/teardown UX still leaves panes / mental residue.** Human had to ask whether manual pane close was OK.  
5. **Parallel ship on one integration branch still produces keep-both docs sludge.** Share notes do not replace a designated integration owner with a docs-coherence checklist.  
6. **Crew home itself had no commits yet** while being actively extended - fine for a prototype, risky as the control plane for paid workers.

---

## Cost-efficiency verdict

**Primary orchestration at ~$30 / 3 hours** for a successful epic is not absurd if worker spend is similar or lower - but it is **high for a process that is mostly `spawn`, `status`, `teardown`, and brief editing.** Fresh input (~2M) is the part that matters; much of it was re-reading design text, re-listing tasks, and mid-session Crew scripting.

Where money was well spent:

- Foundation adv reviews  
- Parallel Fable visuals (wall-clock win)  
- Sol mechanics after Astra downgrade (explicit human cost control)

Where money was poorly spent:

- Failed first spawns (model, CLI)  
- Ultracode merge that could not merge  
- Keeping a fat primary session alive for ops chatter instead of thin dispatch turns  
- Unknown: any worker left idle in a pane after “dismiss” intent without teardown

**Worker cost is the blind spot.** Until Crew records per-task usage, every “use Sonnet max / ultracode” decision is vibes.

---

## Time-efficiency verdict

**Wall-clock win:** parallelizing PR2b/3b/4b and later mech/hook-up waves compressed what would be days of serial work into an evening.

**Human-time loss:** each discard/respawn and each “please make teardown also kill X” stole a supervisory turn. The primary rarely batched “teardown A,B,C + spawn D,E with briefs already on disk” into one move without being asked.

**Best human moves this session:**

- Force feature branch early  
- Downgrade mechanics Astra → Sol xHigh  
- Demand share board and programmatic resource cleanup  
- Merge #54 yourself when the agent hit the permission wall  

**Worst human+primary combo:** launching an ultracode resolver whose acceptance criteria included a merge the harness policy would refuse.

---

## Recommendations (5)

### 1. Preflight the factory; do not discover harness bugs on paid workers

Before any multi-PR wave: one **live smoke per profile** you plan to use (`mechanics`, `new-feature`, Fable custom, etc.). Fail spawn if the model id is not in the harness’s known list. Keep a checked-in `profiles.tsv` that has already survived smoke that day.

**Why:** the first discard and the triple visual discard were pure waste - no design learning, only CLI/config.

### 2. Put dollars on the board next to status

Extend Crew so `bin/status` (or a `bin/cost`) shows **per-task and stack totals**: input/cached/output/$ by harness, plus primary session ticks. Gate expensive efforts (`max`, `ultracode`, Astra) on an explicit human “spend ack” when the stack already exceeds a threshold.

**Why:** you asked about millions of tokens because spend was opaque. You cannot optimize Luna vs Sol vs Sonnet without numbers.

### 3. Split “integrate” from “implement”; never brief a worker to merge if `auto` cannot merge

For stacked epics, run a standing **integration profile** (cheap Luna or human): rebase/merge to `crew/ipf`, docs coherence pass, conflict composition. Implementers stop at “PR open + share note + check green.” Merges are human or a harness with proven merge permission.

**Why:** #54’s ultracode agent did the hard conflict/docs work, then `needs-decision` on `gh pr merge`. That is the most expensive possible failure mode - smart model, blocked on policy.

### 4. Use the primary as a thin dispatcher; recycle context aggressively

Operating rules for the next epic:

- Prefer **one spawn/teardown/status turn**, then stop  
- Treat `state/share/<stack>/` + task `status` as canonical; do not re-ingest the full design doc every turn  
- When primary `usage` crosses ~$15 or ~10M gross input, **start a fresh primary session** with a short handoff note (stack tip SHA, open tasks, next brief path)  
- Batch dismissals; never narrate teardown theory when a script can do it  

**Why:** ~$30 of primary spend was mostly cache replay of orchestration. That does not compound into better code.

### 5. Buy review on foundations; buy parallelism on leaves; buy one merge owner for docs

A practical playbook that matched the evidence:

| Layer | Spend |
| --- | --- |
| PR1 / envelope | Adv scout (Astra/Sol) + fix-forward |
| Parallel visuals / mech | Cheapest model that meets the brief; many workers |
| Hook-ups | Mid-tier implementer; browser check required |
| Stack merge + README master | One owner, checklist against retired paths; human merges |

**Why:** adv ROI was high on #45/#46 and would be low on every leaf PR. Keep-both docs on #54 were a predictable parallel-ship failure mode - prevent with an integration checklist, not another ultracode hero pass.

---

## Suggested Crew backlog (from this session, not implemented here)

1. Spawn-time model existence check  
2. `bin/cost` / status columns for usage  
3. Brief linter: reject “merge the PR” acceptance criteria unless profile is known merge-capable  
4. Share board template prompt that requires `updates/<task>-ready.md` before `done`  
5. Integration checklist doc for stacked bases (compose app.js, dedupe README, retired-path grep)

---

## Final judgment

Crew proved it can run a real multi-track game systems epic against an integration branch with human supervision and without a polling supervisor. That is non-trivial.

Crew and this primary also proved they can **burn ~$30 of orchestrator tokens, ~2× task overhead per PR, and an ultracode merge agent** on problems that are mostly config validation, permission honesty, and thin dispatch discipline.

The stack on `crew/ipf` is a success. The operating cost profile is not yet something you should scale casually. Fix visibility and preflight first; then the same factory pattern gets much cheaper.
