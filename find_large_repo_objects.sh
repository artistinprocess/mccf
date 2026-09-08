#!/bin/bash
# Run from inside the repo root: mccf_full
set -e

echo "=== 1. Overall .git size ==="
du -sh .git

echo
echo "=== 2. Git object count/size summary ==="
git count-objects -vH

echo
echo "=== 3. Files >20MB currently tracked in the working tree ==="
git ls-files -z | xargs -0 du -h 2>/dev/null | sort -rh | awk '$1 ~ /[0-9]G|[0-9][0-9][0-9]M|[2-9][0-9]M/' | head -30

echo
echo "=== 4. Largest blobs anywhere in git history (top 30) ==="
# This walks all commits, not just HEAD, so it catches things that were
# committed once and later deleted — those bytes are still in history
# and still get pushed.
git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '/^blob/ {print substr($0,6)}' |
  sort -k2 -n -r |
  head -30 |
  awk '{ size=$1; unit="B";
         if (size>1073741824) {size=size/1073741824; unit="GB"}
         else if (size>1048576) {size=size/1048576; unit="MB"}
         else if (size>1024) {size=size/1024; unit="KB"}
         printf "%.2f %s  %s\n", size, unit, substr($0, index($0,$2)) }'
