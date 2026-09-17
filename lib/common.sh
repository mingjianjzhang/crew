# Shared Bash 3.2-compatible primitives. Metadata is JSON, never sourced or eval'd.
set -euo pipefail
umask 077
CREW_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
STATE=$CREW_ROOT/state
LOCKS=()

die() { printf 'crew: %s\n' "$*" >&2; exit 1; }
require_runtime() {
  [[ ${HERDR_ENV:-} == 1 ]] || die 'Run Crew inside a herdr-managed pane (HERDR_ENV=1).'
  local tool
  for tool in git jq herdr; do command -v "$tool" >/dev/null || die "Missing dependency: $tool"; done
  mkdir -p "$STATE" "$CREW_ROOT/data"
}
valid_id() { [[ $1 =~ ^[a-z][a-z0-9-]{0,26}$ ]] || die 'Invalid id: use 1-27 lowercase letters, digits or hyphens, starting with a letter.'; }
valid_key() { [[ $1 =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$ ]] || die 'Invalid decision key.'; }
cleanup() {
  local lock
  for lock in "${LOCKS[@]+${LOCKS[@]}}"; do rm -f "$lock/owner"; rmdir "$lock" 2>/dev/null || :; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
lock() {
  local path=$1
  mkdir "$path" 2>/dev/null || die "Busy: $path. Retry later. If abandoned, inspect its owner file before removing the lock."
  LOCKS+=("$path")
  printf '%s %s\n' "$$" "$(date +%s)" > "$path/owner"
}
unlock() {
  local path=$1 i
  rm -f "$path/owner"; rmdir "$path"
  for i in "${!LOCKS[@]}"; do [[ ${LOCKS[$i]} != "$path" ]] || unset 'LOCKS[i]'; done
}
load_task() {
  valid_id "$1"; ID=$1; META=$STATE/$ID.meta
  [[ -f $META && ! -L $META ]] || die "No task: $ID"
  jq -e --arg id "$ID" '.id == $id and (.project|startswith("/")) and
    (.worktree|startswith("/")) and .branch == ("crew/"+$id) and
    .agent == ("crew-"+$id) and (.kind == "ship" or .kind == "scout") and
    (.port_base|type == "number")' "$META" >/dev/null || die "Invalid metadata: $META"
  PROJECT=$(jq -r .project "$META"); WORKTREE=$(jq -r .worktree "$META")
  BRANCH=$(jq -r .branch "$META"); AGENT=$(jq -r .agent "$META")
  WORKSPACE=$(jq -r '.workspace // ""' "$META"); PANE=$(jq -r '.pane // ""' "$META")
  PHASE=$(jq -r .phase "$META"); KIND=$(jq -r .kind "$META")
}
meta_update() {
  jq "$@" "$META" > "$META.tmp"
  mv "$META.tmp" "$META"
}
phase() { meta_update --arg phase "$1" '.phase = $phase'; PHASE=$1; }
common_dir() { git -C "$1" rev-parse --path-format=absolute --git-common-dir; }
verify_worktree() {
  [[ -d $WORKTREE && ! -L $WORKTREE && $WORKTREE != "$PROJECT" ]] || die 'Worker worktree is missing or not isolated.'
  [[ $(git -C "$WORKTREE" rev-parse --show-toplevel) == "$WORKTREE" ]] || die 'Unexpected worktree root.'
  [[ $(common_dir "$WORKTREE") == "$(common_dir "$PROJECT")" ]] || die 'Worktree belongs to another repository.'
  [[ $(git -C "$WORKTREE" symbolic-ref --short HEAD) == "$BRANCH" ]] || die 'Worker branch changed; inspect before proceeding.'
}
verify_workspace() {
  local info
  info=$(herdr workspace get "$WORKSPACE") || die 'Cannot verify herdr workspace; no mutation performed.'
  jq -e --arg path "$WORKTREE" --arg ws "$WORKSPACE" \
    '.result.workspace | .workspace_id == $ws and .worktree.checkout_path == $path' <<< "$info" >/dev/null ||
    die 'herdr workspace identity changed; no mutation performed.'
}
agent_state() {
  local out
  if out=$(herdr agent get "$AGENT" 2>&1); then
    jq -r --arg pane "$PANE" --arg ws "$WORKSPACE" '
      .result.agent | if .pane_id == $pane and .workspace_id == $ws
      then .agent_status else "unknown" end' <<< "$out"
  elif jq -e '.error.code == "agent_not_found"' <<< "$out" >/dev/null 2>&1; then
    printf 'gone\n'
  else
    printf 'unknown\n'
  fi
}
append_event() { "$WORKTREE/.crew/crew-status" "$1" "$2"; }
log_summary() {
  jq -Rn --argjson seen "${2:-0}" '
    [inputs | capture("^(?<time>[0-9]+) (?<verb>working|needs-decision|resolved|done|failed): (?<note>.*)$")
      | .time |= tonumber] as $events |
    reduce range(0; $events|length) as $i
      ({row:"working",note:"no events",decisions:{},pending:{},terminal:null,unread:[],count:($events|length)};
       $events[$i] as $e | ($e.note|split(" ")[0]) as $key |
       if $e.verb == "needs-decision" then .decisions[$key] = $e.note | del(.pending[$key])
       elif $e.verb == "resolved" then del(.decisions[$key]) |
         if ($e.note|endswith(" pending")) then .pending[$key] = $e.note else del(.pending[$key]) end
       elif $e.verb == "done" or $e.verb == "failed" then .terminal = $e |
         if $i >= $seen then .unread += [$e] else . end
       else .note = $e.note end) |
    if .terminal != null then .row = .terminal.verb | .note = .terminal.note
    elif (.decisions|length)>0 then .row="needs-decision" | .note=(.decisions|to_entries|map(.value)|join("; "))
    else . end' "$1"
}
