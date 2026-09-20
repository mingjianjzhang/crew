# Crew instruments (post isometric-demo wave)

Five process tools earned the hard way. Use them. Do not call the scars
"learnings" and then skip the bandage.

Source of truth for the war stories:
`state/share/community-demo-design/updates/retrospective-isometric-demo-wave-2026-09-20.md`.

---

## 1. Zero-Token Closeout (`bin/finish`)

**Rule:** Merge/done-only closeout never wakes the worker.

- Default: `bin/finish ID [--decision KEY] NOTE`
- Tip-sync the worktree to the merged head first when needed
- `bin/answer` is for decisions where the **worker must continue** (fix,
  redesign, hosted-session resume)
- `bin/answer` refuses notes that look like done-only closeout (merged /
  emit done / refresh usage / goodbye) unless you pass `--force` and the
  note still names why the worker must keep going

Paying Astra ~$0.58 / ~451k cache to wave goodbye is a process bug with a
receipt. Teardown was always free. Answer was not.

Details: `docs/finish-no-agent-closeout.md`.

---

## 2. Anti-Goal Block (contested UI briefs)

**Rule:** Every implement brief that follows a visual scout gets a concrete
**Anti-goals** section. Scout approval alone does not carry constraints.

Required content when the surface is contested chrome/plate/HUD:

- Footprint limits (size relative to satchel icons, panel vs station)
- Must-not-obscure rules (stations, characters, world art)
- Banned chrome families (satchel-clone, oversized enamel, CSS/DOM mockups
  for a Canvas game, graph-paper linen, second rail)
- Positive layout lock ("one compact panel above station" / "panel-less
  timer-anchored" / etc.)

06ar approved direction A for $3.42; 06ai still built an enamel cathedral
over the benches for $15.89. The "don't cover the worktops" constraint
showed up as a *second* implement. That is the failure mode this block
exists to kill.

---

## 3. Edit-Map Brief (path:line allowlist + discovery ban)

**Rule:** Name the seams. Ban the museum tour.

Primary/planner briefs must include:

- Exact files (and line ranges when known)
- Call sites / helpers to reuse
- Explicit ban on whole-file `cat` of `app.js`, DEMO stacks, and sibling
  modules not on the allowlist
- Line: **Open only these; IMPLEMENTATION wins over curiosity**

Weak allowlists that say "pack + modules you need" are permission to wander.
community-demo-09 had a wireframe and still burned ~9.4 minutes / ~39 Bash
tools wholesale-catting demo modules before "Implementing…". Vague plans
do not save expensive models; they subsidize archaeology.

A sharp edit map can replace a separate pre-plan agent when you already
know the seams.

---

## 4. Thin TDD Contract (planner → implementor)

**Rule:** Publish a short authoritative contract before expensive ships.
Worker starts red/green, not explorer.

Contract contents:

- Must-stay-green cites (file + describe/line)
- Tests to add (plain language or stubs)
- Run commands
- Seam code refs
- Explicit out-of-contract items

Worker order: contract + listed refs → failing tests → implement to green
→ build/AXI last. Pixel/taste stays human or AXI. Contract bugs escalate
via `needs-decision`; do not silently rewrite acceptance.

Without this, HUD ships open with "surveying demo modules." With it, the
first status after spawn should already be adding or running named tests.

---

## 5. Taste Freeze Gate (wireframe before xhigh paint)

**Rule:** Contested chrome/plate ships do not spawn Astra/Fable **xhigh**
until an owner-frozen wireframe or plate-ref pack exists on the share
board (layout structure, not invented art).

- Ban Imagine / generated comps as apply briefs
- Cheaper implementor applies under allowlist
- Escalate to xhigh only when apply fails a **written** fidelity gate -
  not for open "make it prettier" tweaks
- Research surveys: Lavish real screenshots with credit, not dream models

Orb timer and equipment HUD moved when structure was frozen upstream.
The Imagine UI survey burned attention and got deleted in disgrace. Taste
stays upstream. Apply stays downstream.

---

## How the primary uses these

When writing a brief (`AGENTS.md`):

1. Lean allowlist always (`docs/context-budget.md`)
2. Contested UI after a scout → Anti-Goal Block
3. Known seams / expensive model → Edit-Map + Thin TDD Contract
4. Visual xhigh → Taste Freeze Gate (refuse to spawn until wireframe/ref
   pointer exists)
5. Human merge → `bin/finish`, never a goodbye `bin/answer`
