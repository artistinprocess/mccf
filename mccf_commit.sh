#!/usr/bin/env bash
# mccf_commit.sh -- commit (and optionally push) MCCF from Git Bash.
# Same steps as before (add, status, commit, push) plus the few guards that would have prevented last time's cleanup.
#
#   bash mccf_commit.sh "commit message"          commit only
#   bash mccf_commit.sh "commit message" push     commit, then  git push origin <branch>   (never --force)
#
# Run it from the mccf_full folder. Nothing is committed until you answer y.

MSG="${1:-}"; PUSH="${2:-}"
[ -z "$MSG" ] && { echo 'Usage: bash mccf_commit.sh "commit message" [push]'; exit 1; }

cd "$(dirname "$0")" || exit 1
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Not inside a git repository."; exit 1; }
cd "$ROOT" || exit 1
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Repository: $ROOT   branch: $BRANCH"

git diff --cached --quiet || { echo "Something is already staged. Commit it, or run 'git reset', then re-run."; exit 1; }
read -r -p "Has your backup finished? [y/N] " a; case "$a" in [Yy]*) ;; *) echo "Run again after the backup."; exit 0 ;; esac

# 1. The big / disposable things must be ignored. Checked with git itself, on the REAL paths, so your
#    existing .gitignore rules count and nothing gets added twice.
[ "$(head -c2 .gitignore 2>/dev/null | od -An -tx1 | tr -d ' \n')" = "fffe" ] && { echo ".gitignore is saved as UTF-16, so git cannot read it. Re-save it as UTF-8."; exit 1; }
need_ignored() {  # <a path that must be ignored>  <rule to add if it is not>
  if ! git check-ignore -q "$1"; then
    [ -s .gitignore ] && [ -n "$(tail -c1 .gitignore)" ] && echo >> .gitignore
    echo "$2" >> .gitignore; echo "  added to .gitignore: $2"
  fi
}
need_ignored static/x3d/X3DAssets/probe.bin        'static/x3d/X3DAssets/'
need_ignored static/avatars/backups/probe.x3d      'static/avatars/backups/'
need_ignored cultivars/backups/probe.xml           'cultivars/backups/'
need_ignored probe.bak                             '*.bak'
need_ignored backup_2026-09-19/probe.x3d           'backup_*/'
need_ignored static_copy_probe.html                'static_copy_*.html'
need_ignored LIVE_probe.html                       'LIVE_*.html'
need_ignored node_modules/probe.js                 'node_modules/'
need_ignored __pycache__/probe.pyc                 '__pycache__/'

# 2. Ignoring does NOT untrack. If anything already tracked is now ignored, stop (this was the X3DAssets trap).
TRACKED_IGNORED="$(git ls-files -ci --exclude-standard)"
if [ -n "$TRACKED_IGNORED" ]; then
  echo "STOPPED: $(echo "$TRACKED_IGNORED" | wc -l) already-tracked file(s) match the ignore rules, e.g.:"
  echo "$TRACKED_IGNORED" | head -8 | sed 's/^/    /'
  echo "  Untrack them (files stay on disk), then re-run:"
  echo "    git ls-files -ci --exclude-standard -z | xargs -0 git rm -r --cached -q"
  exit 1
fi

# 3. Stage, then look at what is about to go in.
git add -A 2>/dev/null
FILES="$(git diff --cached --name-only)"
[ -z "$FILES" ] && { echo "Nothing to commit."; exit 0; }
back_out() { git reset -q; echo "Nothing committed. ($*)"; exit "${CODE:-1}"; }

# 3a. Size: anything >= 95 MB stops us (GitHub's limit is 100); >= 20 MB asks first (Anna.x3d is ~24 MB).
BIG=""; HUGE=""
while IFS= read -r f; do
  [ -f "$f" ] || continue
  s=$(stat -c %s "$f" 2>/dev/null || wc -c < "$f")
  [ "$s" -ge 99614720 ] && HUGE="$HUGE$f ($((s/1048576)) MB)\n"
  [ "$s" -ge 20971520 ] && [ "$s" -lt 99614720 ] && BIG="$BIG$f ($((s/1048576)) MB)\n"
done <<< "$FILES"
[ -n "$HUGE" ] && { printf "STOPPED: too big for GitHub:\n$HUGE"; CODE=2 back_out "add them to .gitignore"; }
if [ -n "$BIG" ]; then
  printf "Large files (every committed version stays in history):\n$BIG"
  read -r -p "Commit them anyway? [y/N] " a; case "$a" in [Yy]*) ;; *) back_out "large files declined" ;; esac
fi

# 3b. New files that look like COPIES rather than source: browser downloads such as  mccf_x3d_loader(229).html
#     (we deleted those last time) and backup-style names such as  ...Bak.html, ...bak.html, "- Backup.xml", Old*.xml.
DUPS="$(git diff --cached --name-only --diff-filter=A | grep -E -e '\([0-9]+\)\.[A-Za-z0-9]+$' -e '([Bb]ak|[Bb]ackup)[^/]*$' -e '(^|/)Old[^/]*$')"
if [ -n "$DUPS" ]; then
  echo "New files that look like backup or download copies:"; echo "$DUPS" | sed 's/^/    /'
  read -r -p "Commit them anyway? [y/N] " a; case "$a" in [Yy]*) ;; *) back_out "move or delete them (or add them to .gitignore), then re-run" ;; esac
fi

# 3c. Anything that looks like a key or password (file names only; the repo is public).
SECRETS="$(git diff --cached --name-only -z --diff-filter=AM | xargs -0 grep -lIiE -e 'sk-[A-Za-z0-9_-]{20,}' -e 'AKIA[0-9A-Z]{16}' -e 'gh[pousr]_[A-Za-z0-9]{30,}' -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' -e '(api[_-]?key|secret|passwd|password|token)[[:space:]]*[=:][[:space:]]*["'"'"'][A-Za-z0-9_.-]{16,}["'"'"']' 2>/dev/null)"
if [ -n "$SECRETS" ]; then
  echo "STOPPED: these files contain something that looks like a key or password (public repo!):"; echo "$SECRETS" | sed 's/^/    /'
  echo "  Remove the value (use an environment variable) and re-run. If they are all false alarms: ALLOW_SECRETS=1 bash mccf_commit.sh ..."
  [ "${ALLOW_SECRETS:-}" = 1 ] || { CODE=3 back_out "secret check"; }
fi

# 4. Commit.
echo; git status --short | head -40; echo "($(echo "$FILES" | wc -l) file(s))"
read -r -p "Commit these with message \"$MSG\"? [y/N] " a; case "$a" in [Yy]*) ;; *) back_out "declined" ;; esac
if git commit -q -m "$MSG"; then echo "Committed $(git rev-parse --short HEAD)."; else
  git reset -q
  echo "The commit was BLOCKED (most likely your pre-commit hook; its message is above). Nothing was committed and nothing is left staged."
  echo "Fix what it reports, then run this script again."; exit 1
fi

# 5. Push (only if asked). A plain push: if GitHub has commits you don't, git refuses and we stop. No --force, ever.
if [ "$PUSH" = "push" ]; then
  if git push origin "$BRANCH"; then echo "Pushed."; else
    echo "Push was refused. The commit is safe locally. Do NOT force-push; show this output to Claude first."; exit 1
  fi
else
  echo "Not pushed. When ready:  git push origin $BRANCH"
fi
