#!/bin/bash
# Run from inside the repo root. Lists the 20 largest blobs anywhere in
# git history (all commits, not just HEAD).
set -e

git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '/^blob/ {print $2, $3, substr($0, index($0,$4))}' |
  sort -k2 -n -r |
  head -20 |
  awk '{ size=$2; unit="B";
         if (size>1073741824) {size=size/1073741824; unit="GB"}
         else if (size>1048576) {size=size/1048576; unit="MB"}
         else if (size>1024) {size=size/1024; unit="KB"}
         printf "%.2f %s  %s\n", size, unit, substr($0, index($0,$3)) }'
