# Read-only usage rollup. Source after lib/common.sh (needs CREW_ROOT).

# usage_report FILE SINCE UNTIL MODE
# SINCE/UNTIL are YYYY-MM-DD or empty. MODE is full or line.
usage_report() {
  local file=$1 since=$2 until=$3 mode=$4
  jq -rs -f "$CREW_ROOT/lib/usage-report.jq" \
    --arg since "$since" --arg until "$until" --arg mode "$mode" \
    "$file"
}

# UTC date N days before today. macOS date -v, else GNU date -d.
usage_trailing_start() {
  local days=$1
  if date -u -v-0d +%Y-%m-%d >/dev/null 2>&1; then
    date -u -v-"${days}"d +%Y-%m-%d
  else
    date -u -d "${days} days ago" +%Y-%m-%d
  fi
}
