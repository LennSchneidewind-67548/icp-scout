#!/usr/bin/env bash
# Fails if a case-specific term appears in the text GitHub holds for this repo:
# PR titles, bodies and branch names, reviews, review comments, issues,
# comments, commit comments, releases and the repository description (ADR 0003).
#
# Run it by hand before a visibility change, not in CI. PR text and comments go
# public with the repo, and scripts/leak-check.sh only reads git. Terms come
# from $LEAK_TERMS or private/leak-terms.txt, as in leak-check.sh. Only kinds
# and ids are printed, never the matching text or the term.
# Exit codes: 0 clean, 1 a hit, 2 a `gh` call failed (never read as a pass).
set -euo pipefail

terms="${LEAK_TERMS:-}"
if [ -z "$terms" ] && [ -f private/leak-terms.txt ]; then
  terms="$(cat private/leak-terms.txt)"
fi
if [ -z "$terms" ]; then
  echo "::warning::No leak terms configured (LEAK_TERMS or private/leak-terms.txt); check skipped."
  exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
patterns="$work/patterns"
printf '%s\n' "$terms" | tr -d '\r' | sed '/^[[:space:]]*$/d' > "$patterns"

failed=0
prs=0
issues=0
comments=0
out="$work/out"

# scan <kind> <id prefix> <endpoint> <jq filter> [--paginate]
# The filter prints one TSV line per item: an id, then the text fields.
# The raw lines stay in $out for the caller.
scan() {
  local kind="$1" prefix="$2" endpoint="$3" filter="$4" page="${5:-}"
  if ! gh api $page "$endpoint" --jq "$filter" > "$out"; then
    echo "Could not read $kind from GitHub."
    exit 2
  fi
  while IFS=$'\t' read -r id text || [ -n "$id" ]; do
    [ -z "$id" ] && continue
    case "$kind" in
      PR) prs=$((prs + 1)) ;;
      issue) issues=$((issues + 1)) ;;
      *comment*|review*) comments=$((comments + 1)) ;;
    esac
    if printf '%s\n' "$text" | grep -q -i -F -f "$patterns"; then
      echo "Case-specific terms in $kind $prefix$id."
      failed=1
    fi
  done < "$out"
}

R='repos/{owner}/{repo}'
scan PR '#' "$R/pulls?state=all&per_page=100" \
  '.[] | [.number, .title, (.body // ""), .head.ref] | @tsv' --paginate
numbers="$(cut -f1 "$out")"
for n in $numbers; do
  scan "review on PR" '#' "$R/pulls/$n/reviews?per_page=100" \
    ".[] | [\"$n\", (.body // \"\")] | @tsv" --paginate
done
scan "review comment on PR" '#' "$R/pulls/comments?per_page=100" \
  '.[] | [(.pull_request_url | split("/") | last), .body] | @tsv' --paginate
scan issue '#' "$R/issues?state=all&per_page=100" \
  '.[] | select(.pull_request | not) | [.number, .title, (.body // "")] | @tsv' --paginate
scan "comment on" '#' "$R/issues/comments?per_page=100" \
  '.[] | [(.issue_url | split("/") | last), .body] | @tsv' --paginate
scan "commit comment" '' "$R/comments?per_page=100" \
  '.[] | [.commit_id[0:12], .body] | @tsv' --paginate
scan release '' "$R/releases?per_page=100" \
  '.[] | [.tag_name, (.name // ""), (.body // "")] | @tsv' --paginate
scan repository '' "$R" \
  '[ "repo", (.description // ""), (.topics | join(" ")), (.homepage // "") ] | @tsv'

if [ "$failed" -eq 0 ]; then
  echo "GitHub text check passed: $(wc -l < "$patterns" | tr -d ' ') terms, $prs PRs, $issues issues, $comments comments."
fi
exit "$failed"
