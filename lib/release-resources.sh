# Best-effort release of a task's local runtime resources.
# Bash 3.2 compatible. Safe to call more than once. Never fails the caller.
#
# Stops the task-scoped chrome-devtools-axi session (if present) and kills
# processes listening on the reserved ten-port block. Does not touch other
# tasks' sessions or unrelated Chrome instances.

release_task_resources() {
  local id=$1 worktree=$2 port_base=$3
  local port end pid pids bridge_pid bridge_file killed=0 axi_stopped=0

  [[ -n $id && -n $port_base && $port_base =~ ^[0-9]+$ ]] || return 0

  # 1) Stop the AXI bridge/browser for this task session only.
  if command -v chrome-devtools-axi >/dev/null 2>&1; then
    if CHROME_DEVTOOLS_AXI_SESSION=$id chrome-devtools-axi stop >/dev/null 2>&1; then
      axi_stopped=1
    fi
  fi
  bridge_file=$HOME/.chrome-devtools-axi/sessions/$id/bridge.pid
  if [[ -f $bridge_file ]]; then
    bridge_pid=$(jq -r '.pid // empty' "$bridge_file" 2>/dev/null || true)
    if [[ -z $bridge_pid ]]; then
      bridge_pid=$(tr -dc '0-9' < "$bridge_file" | head -c 12 || true)
    fi
    if [[ -n $bridge_pid ]] && kill -0 "$bridge_pid" 2>/dev/null; then
      kill "$bridge_pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$bridge_pid" 2>/dev/null || true
      killed=1
    fi
    rm -f "$bridge_file" 2>/dev/null || true
  fi

  # 2) Free the reserved preview/scenario port block.
  end=$((port_base + 9))
  port=$port_base
  while [[ $port -le $end ]]; do
    pids=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
    for pid in $pids; do
      [[ $pid =~ ^[0-9]+$ ]] || continue
      kill "$pid" 2>/dev/null || true
      killed=1
    done
    port=$((port + 1))
  done
  if [[ $killed -eq 1 ]]; then
    sleep 0.2
    port=$port_base
    while [[ $port -le $end ]]; do
      pids=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
      for pid in $pids; do
        [[ $pid =~ ^[0-9]+$ ]] || continue
        kill -9 "$pid" 2>/dev/null || true
      done
      port=$((port + 1))
    done
  fi

  # worktree is accepted for callers/tests; port+session cleanup is enough here.
  : "${worktree:=}"

  printf 'resources: session=%s axi_stop=%s ports=%s-%s\n' \
    "$id" "$axi_stopped" "$port_base" "$end"
}

# Executed as a script (not sourced by teardown): parse flags and run once.
if [[ ${0##*/} == release-resources.sh ]]; then
  # Manual/test entry: bash lib/release-resources.sh --id ID --port-base N [--worktree PATH]
  id=; port_base=; worktree=
  while [[ $# -gt 0 ]]; do
    case $1 in
      --id) id=$2; shift 2;;
      --port-base) port_base=$2; shift 2;;
      --worktree) worktree=$2; shift 2;;
      *) echo "Unknown arg: $1" >&2; exit 2;;
    esac
  done
  [[ -n $id && -n $port_base ]] || { echo 'Usage: release-resources.sh --id ID --port-base N [--worktree PATH]' >&2; exit 2; }
  release_task_resources "$id" "$worktree" "$port_base"
fi
