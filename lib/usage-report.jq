# Roll up crew-usage/v1 JSONL. Null or omitted costUsd is blind, not $0.
# Args: $since, $until (YYYY-MM-DD, inclusive, empty = open), $mode (full|line).
def day:
  (.recordedAt // "")
  | if (type == "string" and length >= 10) then .[0:10] else "" end;
def priced: (.costUsd | type) == "number";
def money:
  ((. * 100) + 0.5 | floor) as $cents
  | (($cents / 100) | floor | tostring) as $whole
  | (($cents % 100) | tostring) as $frac
  | $whole + "." + (if ($frac | length) == 1 then "0" + $frac else $frac end);

(map(select(
  ($since == "" or (day >= $since)) and
  ($until == "" or (day != "" and day <= $until))
))) as $rows
| ($rows | map(select(priced) | .costUsd) | add // 0) as $known
| ($rows | map(select(priced)) | length) as $priced_n
| ($rows | length) as $n
| ($n - $priced_n) as $blind_n
| (if $since != "" then $since
   elif $n == 0 then ""
   else ($rows | map(day) | map(select(length > 0)) | min)
   end) as $from
| (if $until != "" then $until
   elif $n == 0 then ""
   else ($rows | map(day) | map(select(length > 0)) | max)
   end) as $to
| if $mode == "line" then
    if $n == 0 then
      "usage since \($since): no records in window"
    else
      "usage since \($since): known $\($known | money) (\($priced_n) priced), blind \($blind_n) (no costUsd, not $0)"
    end
  else
    (
      [
        "records: \($n)",
        (
          "window: " + (
            if $from == "" and $to == "" then "none"
            elif $from == "" then $to
            elif $to == "" then $from
            else "\($from) .. \($to)"
            end
          )
        ),
        "known_usd: \($known | money)",
        "priced: \($priced_n)",
        "blind: \($blind_n)"
      ] + (
        if $n == 0 then []
        else
          [""]
          + ["by_model:"]
          + (
              $rows
              | group_by([.harness, .model, .kind])
              | map({
                  harness: .[0].harness,
                  model: .[0].model,
                  kind: .[0].kind,
                  n: length,
                  blind: (map(select(priced | not)) | length),
                  known: (map(select(priced) | .costUsd) | add // 0)
                })
              | sort_by([-.known, .harness, .model, .kind])
              | map("\(.known | money) n=\(.n) blind=\(.blind) \(.harness)/\(.model) \(.kind)")
            )
          + ["", "top:"]
          + (
              [$rows[] | select(priced)]
              | sort_by([-.costUsd, .taskId])
              | .[0:8]
              | if length == 0 then ["(none priced)"]
                else map("\(.costUsd | money) \(.taskId) \(.harness)/\(.model) \(.kind)")
                end
            )
          + ["", "blind_rows:"]
          + (
              [$rows[] | select(priced | not)]
              | sort_by([.recordedAt // "", .taskId // ""])
              | if length == 0 then ["(none)"]
                else map("\(.taskId) \(.harness)/\(.model) \(.kind) \(.source // "?")")
                end
            )
        end
      )
    )[]
  end
