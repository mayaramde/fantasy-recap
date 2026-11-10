#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash). Reads the tool call as JSON on stdin and
exits 2 (BLOCK_EXIT) with a message on stderr to block it. Exit 0 to allow.

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

Pushes made while `main` is checked out are blocked outright: with main out,
`git push`, `git push origin HEAD` and friends all push main. The branch is
looked up where the command runs: the payload's `cwd`, a `cd` earlier in the
same command, or `git -C <path>`.
"""
import json
import os
import re
import shlex
import subprocess
import sys

# Claude Code blocks a tool call only when a PreToolUse hook exits with 2;
# any other non-zero code is reported as a hook error and the command runs.
BLOCK_EXIT = 2

SHELL_OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}

# A `.env` file, or `.env.<anything>` — except the example Maya fills in by
# hand. Deliberately NOT a bare "startswith" check: ".environment.md" must
# not match just because it starts with the same four letters.
ENV_RE = re.compile(r"^\.env(\.[\w.-]+)?$")


def read_payload():
    """The command to check and the directory Claude Code runs it in."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None, None
    return (payload.get("tool_input") or {}).get("command"), payload.get("cwd")


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

# Push modes that send every local branch, main included (--mirror also
# force-overwrites and deletes remote branches), whatever else is on the line.
ALL_BRANCH_PUSH_FLAGS = {"--mirror", "--all", "--branches"}


def current_branch(directory=None):
    """The branch checked out in `directory` (default: the hook's own cwd), or
    None when git can't say (not a repo, git missing). A detached HEAD reports
    "HEAD"."""
    cmd = ["git"] + (["-C", directory] if directory else []) + ["rev-parse", "--abbrev-ref", "HEAD"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def implicit_main_push_reason(rest, branch):
    """Block any push made while main is checked out.

    `rest` is the tokens after `git`, e.g. ["push", "-u", "origin", "HEAD"];
    `branch` is the checked-out branch (see current_branch()). With main
    checked out, a push that names no branch, or HEAD/@, or a flag-with-value
    that shifts the words around, all push main, and telling them apart from a
    safe push is fragile. Every shipped change goes out from its own branch, so
    the rule is simply: switch off main before pushing. When git can't say
    which branch is out, allow; settings.json still asks before the bare forms.
    """
    if branch == "main":
        return "git push while main is checked out (switch to a branch first)"
    return None


# git's own global options that take a value: `git -C <path> push` must not
# read <path> as the subcommand.
GIT_GLOBAL_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def parse_git(segment):
    """(subcommand, args after it, the -C directory or None) for a segment
    that runs git, else (None, [], None)."""
    # Only a segment that *runs* git (after any VAR=value prefixes), so
    # `grep git push.md` or `echo git push` isn't read as a push.
    words = list(segment)
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words = words[1:]
    if not words or words[0] != "git":
        return None, [], None
    toks = words[1:]
    directory, i = None, 0
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] in GIT_GLOBAL_VALUE_OPTS:
            if toks[i] == "-C" and i + 1 < len(toks):
                directory = toks[i + 1]
            i += 2
        else:
            i += 1
    if i >= len(toks):
        return None, [], directory
    return toks[i], toks[i + 1:], directory


def dangerous_git_reason(segment, branch=None, cwd=None):
    """Why this segment's git command must not run, or None. `cwd` is where
    the command runs (the payload's cwd, or a `cd` earlier in the command);
    `branch` overrides the lookup, for tests."""
    subcommand, args, git_dir = parse_git(segment)

    if subcommand == "push":
        for tok in args:
            if tok.startswith("--force"):
                return f"git push uses {tok}"
            if FORCE_FLAG_RE.match(tok):
                return f"git push uses a force flag ({tok})"
            if tok.startswith("+") and len(tok) > 1:
                return f"git push uses a force refspec ({tok})"
            if tok == "main" or tok.endswith(":main") or tok.endswith("/main"):
                return f"git push targets main directly ({tok})"
            if tok in ALL_BRANCH_PUSH_FLAGS:
                return f"git push uses {tok}, which pushes main along with every other branch"
            if tok == ":" or "*" in tok:
                return f"git push uses a matching refspec ({tok}), which can push main"
        if branch is None:
            directory = git_dir
            if directory and cwd and not os.path.isabs(directory):
                directory = os.path.join(cwd, directory)
            branch = current_branch(directory or cwd)
        return implicit_main_push_reason(["push"] + args, branch)

    if subcommand == "add":
        if any(tok.startswith("--force") or FORCE_FLAG_RE.match(tok) for tok in args):
            return "git add uses -f/--force, the only way to force a gitignored file into a commit"
        return None

    return None


def rm_rf_root(segment):
    return "rm" in segment and any(t in ("-rf", "-fr") for t in segment) and "/" in segment


def is_fork_bomb(command):
    squeezed = re.sub(r"\s+", "", command)
    return ":(){:|:&};:" in squeezed


def main():
    command, cwd = read_payload()
    if not command:
        return 0

    if is_fork_bomb(command):
        print("Blocked by guard_bash.py: fork bomb pattern.", file=sys.stderr)
        return BLOCK_EXIT

    tokens = tokenize(command)
    for segment in split_commands(tokens):
        if rm_rf_root(segment):
            print("Blocked by guard_bash.py: rm -rf on /.", file=sys.stderr)
            return BLOCK_EXIT

        hit = secret_path_hit(segment)
        if hit:
            print(f"Blocked by guard_bash.py: command references a denied secret path ({hit!r}).",
                  file=sys.stderr)
            return BLOCK_EXIT

        if segment[0] == "cd" and len(segment) > 1:
            target = os.path.expanduser(segment[1])
            cwd = target if os.path.isabs(target) or not cwd else os.path.join(cwd, target)
            continue

        reason = dangerous_git_reason(segment, cwd=cwd)
        if reason:
            print(f"Blocked by guard_bash.py: {reason}.", file=sys.stderr)
            return BLOCK_EXIT

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a hook bug must not silently block every command
        print(f"guard_bash.py: internal error, allowing by default: {exc}", file=sys.stderr)
        sys.exit(0)
