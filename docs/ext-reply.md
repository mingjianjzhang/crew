# External reply entry point (`state/ext-reply`)

Crew-owned filesystem queue so a trusted local caller (Crew View) can submit
answers without copy-pasting `bin/answer`, while apply stays herdr-gated.

## Layout

```
$CREW_ROOT/state/ext-reply/          # mode 0700
  inbox/                             # callers drop one JSON request per file
  processing/                        # drain claims files here while applying
  applied/                           # success receipts (idempotent archive)
  applied/by-key/                    # optional index by idempotencyKey
  failed/                            # validation / apply failures
  pending-delivery/                  # answer saved; herdr prompt not confirmed
```

`bin/ext-reply` creates these directories on first use.

## Schema `crew-ext-reply/v1`

One JSON object per file. Shared fields: `schema`, `id`, `type`, `createdAt`
(optional; enqueue fills epoch seconds when missing), optional `idempotencyKey`,
optional `source` (`crew-view`, `cli`, …).

### `type: "answer"` (v1)

```json
{
  "schema": "crew-ext-reply/v1",
  "id": "01JEXAMPLE",
  "type": "answer",
  "taskId": "community-debug-session1",
  "decisionKey": "hosted-session-ready",
  "text": "Bugs filed; continue.",
  "force": false,
  "idempotencyKey": "crew-view-call-123"
}
```

Drain calls existing `bin/answer` so farewell detection and pending delivery stay
single-sourced.

### Refused in v1

- `type: "spawn"` and `type: "finish"` (come later; clear error on enqueue/drain).
- Raw `herdr agent prompt`, keystrokes, or pane focus.
- Inventing `HERDR_ENV=1` from outside a herdr-managed pane.
- Cross-home brokers (write only into the target Crew home’s own `state/ext-reply`).

## Commands

| Subcommand | `HERDR_ENV` | Role |
| --- | --- | --- |
| `enqueue @FILE\|JSON` | No | Validate and drop into `inbox/` (atomic temp + rename). |
| `status` | No | Counts and short listing. |
| `drain` / `apply` | Yes | Claim inbox → processing → `bin/answer` → receipts. |
| `deliver` | Yes | Retry `pending-delivery` with `bin/answer … --deliver`. |

Callers may write `inbox/<id>.json` directly with the same schema; `enqueue` is
the checked helper for tests and humans.

## Event-driven apply model

1. External caller enqueues (no herdr required).
2. Caller triggers apply into a live Crew/herdr session, for example
   `herdr pane run <primary-pane> 'cd "$CREW_ROOT" && bin/ext-reply drain'`.
3. There is **no** silent Crew daemon that polls the queue or wakes the primary.
4. If herdr/Crew is not up, requests stay in `inbox/`; receipts and `bin/ext-reply status`
   surface that honestly.
5. `bin/status` may print a read-only `ext-reply: N queued` hint; it never drains.

## Idempotency and failure modes

- Same `id` or `idempotencyKey` already in `applied/` → enqueue/drain no-op success.
- `applied` — answer prompt confirmed (or idempotent replay).
- `pending_delivery` — answer on disk; agent was not idle/done; use `bin/ext-reply deliver`.
- `failed` — validation or `bin/answer` refusal (unknown key, farewell shape, …).
- Files left in `processing/` after a crash need explicit inspect / re-queue; drain
  does not silently replay them.

## Trust

Same OS user as the Crew home; directory mode `0700`.
No Crew HTTP listener for this surface.
Do not expose `state/ext-reply` off-machine without extra auth.
