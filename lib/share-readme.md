# Crew shared board

Workers on the same stack share this directory via `.crew/share`.
It lives in the Crew home (`state/share/<id>/`), not inside any one Git worktree.

## Rules

- Write useful notes other workers (and the primary) may need.
- Do **not** wait, poll, or block on siblings. The primary still coordinates.
- Do **not** edit other tasks' project worktrees from here.
- Keep task progress in local `.crew/status`; use this board for cross-task facts.

## Layout

| Path | Use |
| --- | --- |
| `updates/` | Short dated notes: landed PRs, contract changes, gotchas |
| `reviews/` | Adversarial / scout reports (copy or summarize) |
| `INDEX.md` | Optional running index maintained by anyone |

Prefer plain Markdown. Name files with task id or topic, e.g.
`updates/ipf-pr1-landed.md`, `reviews/pr46-adversarial.md`.

## Suggested update shape

```md
# <short title>
- Task: <id>
- PR: <url or number>
- Base: <branch>
- Summary: <what changed that siblings should know>
- Follow-ups: <optional>
```
