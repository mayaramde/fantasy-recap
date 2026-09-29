#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash). Reads the tool call as JSON on stdin and
exits non-zero with a message on stderr to block it. Exit 0 to allow.

This is a hard guardrail, separate from settings.json's permission lists:
permissions gate whether the user is prompted, this gates whether the
command can run at all, even if the user would have approved it. Keep this
list short and about things that are never fine, not things that are merely
risky (those belong in permissions.ask / CLAUDE.md).

Three things are never fine here:
  - Reading a secret path. settings.json's broad `cat:*`/`grep:*`/`find:*`
    allow rules make those commands the easy way to read a denied file even
    though direct `Read` of it is blocked, so this hook re-checks every
    command's tokens (not just the ones named after cat/grep/find) against
    the same secret paths. `.env.espn.local.example` is deliberately not a
    secret, since Maya fills it in with her own values by hand.
  - Force-pushing, or pushing straight to `main`. Every shipped change goes
    through a branch + PR (CLAUDE.md).
  - `git add -f`/`-A -f`, the only way to force a gitignored secret into a
    commit.

The command is parsed with `shlex` (not a substring grep) so a pipe or a
`;`-chained command can't smuggle a denied path past a naive check, and each
`git` invocation's subcommand and flags are inspected structurally rather
than by pattern-matching the whole line.

Known limitation: `git -C <path> push ...` (a global git flag that takes a
value) will confuse the "first non-flag token is the subcommand" heuristic
below. Nothing in this repo's workflow uses `-C`, so this is left as a
documented gap rather than a general git command-line parser.
"""
import json
import re
import shlex
import sys

SHELL_OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}

# A `.env` file, or `.env.<anything>` — except the example Maya fills in by
# hand. Deliberately NOT a bare "startswith" check: ".environment.md" must
# not match just because it starts with the same four letters.
ENV_RE = re.compile(r"^\.env(\.[\w.-]+)?$")


def read_command():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return (payload.get("tool_input") or {}).get("command")


def tokenize(command):
    """Split into words and shell operators. Falls back to a plain whitespace
    split if the command has unbalanced quotes (e.g. inside a heredoc) that
    shlex can't tokenize — better to still scan something than to raise."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return command.split()


def split_commands(tokens):
    """Break the flat token stream into sub-command segments at shell
    operators, so `cat .env.local | grep x` is inspected as two segments and
    `git push -f && deploy` doesn't let the `&&` hide inside a git segment."""
    segments, current = [], []
    for tok in tokens:
        if tok in SHELL_OPERATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def is_secret_path(value):
    value = value.strip("'\"")
    if not value or value[0] in "-+":
        return False
    parts = [p for p in value.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        return False
    basename = parts[-1]
    if any(p == ".vercel" for p in parts):
        return True
    if basename == ".env.espn.local.example":
        return False
    return bool(ENV_RE.match(basename))


def secret_path_hit(tokens):
    for tok in tokens:
        if is_secret_path(tok):
            return tok
        # catches `--file=.env.local`-style flag=value forms too.
        if "=" in tok:
            _, _, value = tok.partition("=")
            if is_secret_path(value):
                return value
    return None


FORCE_FLAG_RE = re.compile(r"^-[a-zA-Z]*f[a-zA-Z]*$")


def dangerous_git_reason(segment):
    if "git" not in segment:
        return None
    rest = segment[segment.index("git") + 1:]
    subcommand = next((t for t in rest if not t.startswith("-")), None)

    if subcommand == "push":
        for tok in rest:
            if tok.startswith("--force"):
                return f"git push uses {tok}"
            if FORCE_FLAG_RE.match(tok):
                return f"git push uses a force flag ({tok})"
            if tok.startswith("+") and len(tok) > 1:
                return f"git push uses a force refspec ({tok})"
            if tok == "main" or tok.endswith(":main") or tok.endswith("/main"):
                return f"git push targets main directly ({tok})"
        return None

    if subcommand == "add":
        if any(tok.startswith("--force") or FORCE_FLAG_RE.match(tok) for tok in rest):
            return "git add uses -f/--force, the only way to force a gitignored file into a commit"
        return None

    return None


def rm_rf_root(segment):
    return "rm" in segment and any(t in ("-rf", "-fr") for t in segment) and "/" in segment


def is_fork_bomb(command):
    squeezed = re.sub(r"\s+", "", command)
    return ":(){:|:&};:" in squeezed


def main():
    command = read_command()
    if not command:
        return 0

    if is_fork_bomb(command):
        print("Blocked by guard_bash.py: fork bomb pattern.", file=sys.stderr)
        return 1

    tokens = tokenize(command)
    for segment in split_commands(tokens):
        if rm_rf_root(segment):
            print("Blocked by guard_bash.py: rm -rf on /.", file=sys.stderr)
            return 1

        hit = secret_path_hit(segment)
        if hit:
            print(f"Blocked by guard_bash.py: command references a denied secret path ({hit!r}).",
                  file=sys.stderr)
            return 1

        reason = dangerous_git_reason(segment)
        if reason:
            print(f"Blocked by guard_bash.py: {reason}.", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a hook bug must not silently block every command
        print(f"guard_bash.py: internal error, allowing by default: {exc}", file=sys.stderr)
        sys.exit(0)
