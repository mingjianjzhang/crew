# Rules-completion lane

One lane. Three commands. The human still merges.

```sh
bin/lane assign rules-r3 \
  --project /absolute/path/to/repo \
  --base feature/isometric-demo \
  --share community-demo-design \
  --freeze state/share/community-demo-design/narrative/<freeze>.md \
  --budget-usd 40 \
  --max-cycles 2 \
  --ship-model grok-4.7 --ship-effort high \
  --review-model grok-4.7 --review-effort high \
  --brief state/briefs/rules-r3.md

bin/lane cancel rules-r3
```

`assign` checks the brief, writes `state/lanes/<id>.json`, spawns `<id>-s`, and starts `bin/lane watch` if it is not already running. `cancel` marks the lane cancelled and leaves the live worker alone. Watch is the only long-lived process. It speaks herdr's newline-delimited JSON socket (`events.subscribe` on `HERDR_SOCK` or `~/.config/herdr/herdr.sock`) and reconciles `.crew/status` before any spawn.

Chain: ship done with a PR url and a numeric `costUsd` → review scout. Pass → notify, state `passed`. Fail with a valid fix brief, and only while `reviewCount < maxCycles` → one fix ship → one re-review. A second fail, a `block`, `failed`, `needs-decision`, a null cost, a missing PR url, or a sum of `costUsd` above `budgetUsd` stops the lane. Null is not zero.

Watch does not `bin/answer`, `bin/finish`, `gh pr merge`, or focus a pane. A 60s tick may call `herdr agent get` for a lane pane whose last event is older than that. The default stall notice is 60 minutes (`--stall-minutes`). It does not kill the pane.

`--lane` on `bin/spawn` records the id and writes `CREW_LANE` / `CREW_ROOT` into the worktree env. v0 does not hook `lib/crew-status`. A busy lane lock is skipped and retried on the next event; it is not stolen.

Entry checks fail closed: Edit-Map plus a `path:line` cite, Thin TDD or `must-stay-green` plus a fenced run command, a freeze file that contains `FROZEN`, no `--yolo` / `--effort xhigh` / `--permission-mode plan`, no hosted-debug or packet-path brief, share set, and `YOLO.md` absent or `Status: OFF`. A second non-terminal lane on the same share is refused. Passed is not a freeze stamp. `bin/status` does not print lanes in v0.

Review scouts write `.crew/lane-result.json` (`pass`, `fail` + `fixBrief`, or `block`) and, on fail, `state/lanes/<id>/fix-1.md`. Usage and that verdict come before `done`. The lane does not grep the report.
