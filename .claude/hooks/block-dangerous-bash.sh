#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash). Reads the tool call as JSON on stdin and
# exits non-zero with a message on stderr to block it. Exit 0 to allow.
#
# This is a hard guardrail, separate from settings.json's permission lists:
# permissions gate whether the user is prompted, this gates whether the
# command can run at all, even if the user would have approved it.
# Keep this list short and about things that are never fine, not things
# that are merely risky (those belong in permissions.ask / CLAUDE.md).
#
# Two patterns here are specific to this repo's own CLAUDE.md rules, which
# state them as never-fine (not "ask"):
#   - "Don't push to main directly." Every shipped change goes through a
#     branch + PR.
#   - Raw ESPN captures and the dashboard secret are .gitignore'd because
#     they contain members' personal info or a credential; forcing past
#     that gitignore is the only way to accidentally commit them.

set -euo pipefail

input="$(cat)"
command="$(echo "$input" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"//; s/"$//')"

deny_patterns=(
  'rm -rf /'
  'git push --force '
  'git push -f '
  ':(){ :|:& };:'
  'git push origin main'
  'git push upstream main'
  'push origin HEAD:main'
  'git add -f'
  'git add --force'
)

for pattern in "${deny_patterns[@]}"; do
  if [[ "$command" == *"$pattern"* ]]; then
    echo "Blocked by block-dangerous-bash.sh: command matches denylisted pattern '$pattern'." >&2
    exit 1
  fi
done

exit 0
