#!/usr/bin/env bash
# Fails if a case-specific term appears anywhere in git history (ADR 0003):
# in any file of any commit, or in any commit message.
#
# Terms come from $LEAK_TERMS (one per line; a GitHub secret in CI) or, locally,
# from private/leak-terms.txt. Only commit hashes and paths are printed, never
# the matching text, so the CI log of a public repo leaks nothing.
set -euo pipefail

terms="${LEAK_TERMS:-}"
if [ -z "$terms" ] && [ -f private/leak-terms.txt ]; then
  terms="$(cat private/leak-terms.txt)"
fi
if [ -z "$terms" ]; then
  echo "::warning::No leak terms configured (LEAK_TERMS or private/leak-terms.txt); check skipped."
  exit 0
fi

patterns="$(mktemp)"
trap 'rm -f "$patterns"' EXIT
printf '%s\n' "$terms" | tr -d '\r' | sed '/^[[:space:]]*$/d' > "$patterns"

failed=0

hits="$(git grep -l -i -F -f "$patterns" $(git rev-list --all) -- || true)"
if [ -n "$hits" ]; then
  echo "Case-specific terms in committed files (commit:path):"
  echo "$hits"
  failed=1
fi

for commit in $(git rev-list --all); do
  if git log -1 --format=%B "$commit" | grep -q -i -F -f "$patterns"; then
    echo "Case-specific terms in the message of commit $commit"
    failed=1
  fi
done

if [ "$failed" -eq 0 ]; then
  echo "Leak check passed: $(wc -l < "$patterns") terms, $(git rev-list --all | wc -l) commits."
fi
exit "$failed"
