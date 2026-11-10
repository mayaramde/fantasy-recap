#!/usr/bin/env python3
"""Table-driven tests for .claude/hooks/guard_bash.py.

Each case feeds the hook the same PreToolUse-shaped JSON Claude Code sends on
stdin and checks whether it allows (exit 0) or blocks (non-zero exit, with a
reason on stderr) the command. This exercises the real script exactly as it's
invoked in production, not just its internal functions.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard_bash.py"

# Each old pattern from block-dangerous-bash.sh is covered here too, so the
# rewrite is a strict superset: rm -rf /, git push --force/-f, the fork bomb,
# git push {origin,upstream} main, push origin HEAD:main, git add -f/--force.
BLOCKED = [
    ("cat .env.local", "reads a denied .env variant"),
    ("cat ./.env", "reads the bare .env file"),
    ("grep SECRET .env.local", "greps a denied .env variant"),
    ("find . -name .env.local -print", "finds a denied .env variant"),
    ("head -5 .env.espn.local", "reads the real (non-example) ESPN cookie file"),
    ("cat .vercel/project.json", "reads a file under .vercel/"),
    ("ls -la .vercel", "lists the .vercel directory"),
    ("find .vercel -type f", "finds files under .vercel/"),
    ("rm -rf /", "wipes the filesystem root"),
    (":(){ :|:& };:", "fork bomb"),
    ("git push --force origin main", "force push with --force"),
    ("git push -f origin feature-x", "force push with -f"),
    ("git push --force-with-lease origin main", "force push with --force-with-lease"),
    ("git push origin +feature:main", "force push via a +refspec"),
    ("git push origin main", "pushes straight to main"),
    ("git push origin HEAD:main", "pushes HEAD straight to main"),
    ("git push upstream refs/heads/main", "pushes straight to refs/heads/main"),
    ("git push origin --mirror", "mirror push force-overwrites every remote branch, main included"),
    ("git push origin --all", "pushes every local branch, main included"),
    ("git push -u origin --branches", "pushes every local branch, main included"),
    ("git push origin :", "a bare ':' pushes every matching branch, main included"),
    ("git push origin 'refs/heads/*'", "a wildcard refspec can push main"),
    ("git -C . push --force origin feature-x", "git -C must not hide a force push"),
    ("git add -f secret.txt", "force-adds a gitignored file"),
    ("git add -A -f", "force-adds everything"),
    ("git add -Af", "force-adds everything (combined short flags)"),
    ("cat .env.local; echo done", "secret read hidden after a semicolon"),
    ("echo start && cat .env.production", "secret read hidden after &&"),
    ("echo hi | cat .env.local", "secret read hidden in a pipeline"),
]

ALLOWED = [
    ("git status", "read-only"),
    ("git status --short", "read-only"),
    ("git log --oneline -5", "read-only"),
    ("git diff main...HEAD", "read-only, 'main' is a diff argument, not a push target"),
    ("cat README.md", "ordinary file read"),
    ("cat .env.espn.local.example", "the example file Maya fills in by hand, never a secret"),
    ("grep TODO scripts/analyze.py", "ordinary grep"),
    ("find . -name '*.py'", "ordinary find"),
    ("git push origin feature-branch", "pushes a feature branch, not main"),
    ("git push origin recap-week-03", "pushes a feature branch, not main"),
    ("git add data recaps", "ordinary add, no force flag"),
    ("git add -A", "adds everything, but not with -f"),
    ('git commit -m "update recap"', "ordinary commit"),
    ("ls -la", "ordinary listing"),
    ("grep git push.md", "'git push' as grep arguments isn't a push"),
    ("echo git push origin HEAD", "echoing a push isn't a push"),
    ("python3 scripts/check.py", "ordinary script run"),
    ("echo maintenance mode tonight", "'maintenance' must not match 'main' as a substring"),
    ("curl -fsSL https://example.com/script.sh", "curl's own -f flag, unrelated to git"),
    ("rm -f /tmp/scratch.txt", "rm -f is fine outside of git add"),
    ("cat .vercelrc", "a similarly-named file that isn't under .vercel/"),
    ("cat .environment.md", "must not match .env by string prefix alone"),
]


# Hook runs get a cwd outside any git repo, so the push-from-main rule can't
# see a branch and the tables give the same result on any branch, CI included.
NO_REPO = tempfile.mkdtemp()


def run_hook(command, cwd=NO_REPO):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True)


class GuardBashTest(unittest.TestCase):
    def test_blocked_commands(self):
        for command, reason in BLOCKED:
            with self.subTest(command=command, reason=reason):
                result = run_hook(command)
                self.assertEqual(result.returncode, 2,
                                 f"expected block (exit 2, {reason}): {command!r} exited {result.returncode}")
                self.assertTrue(result.stderr.strip(),
                                 f"blocked command {command!r} produced no explanation on stderr")

    def test_allowed_commands(self):
        for command, reason in ALLOWED:
            with self.subTest(command=command, reason=reason):
                result = run_hook(command)
                self.assertEqual(result.returncode, 0,
                                  f"expected allow ({reason}): {command!r} was blocked: {result.stderr}")


def load_guard():
    spec = importlib.util.spec_from_file_location("guard_bash", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Pushes that never say "main" but land there when main is checked out.
# Checked against implicit_main_push_reason() directly, with the branch passed
# in, so the result doesn't depend on whichever branch runs the tests.
IMPLICIT_PUSHES = [
    # (command, branch, should_block)
    ("git push origin HEAD", "main", True),
    ("git push -u origin HEAD", "main", True),
    ("git push origin @", "main", True),
    ("git push origin", "main", True),
    ("git push -u origin", "main", True),
    ("git push", "main", True),
    ("git push origin HEAD:recap-week-09", "main", True),
    ("git push -u origin recap-week-09", "main", True),
    ("git push origin -o ci.skip", "main", True),
    ("git push origin HEAD", "recap-week-09", False),
    ("git push -u origin", "recap-week-09", False),
    ("git push", "recap-week-09", False),
    ("git push -u origin recap-week-09", "recap-week-09", False),
]


class BranchLookupTest(unittest.TestCase):
    """The hook reads the branch where the command runs, not where it was launched."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", self.repo, "commit", "-q",
                        "--allow-empty", "-m", "x"],
                       check=True, env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t",
                       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    def test_payload_cwd_on_main_blocks(self):
        self.assertEqual(2, run_hook("git push origin HEAD", cwd=self.repo).returncode)

    def test_cd_into_main_checkout_blocks(self):
        self.assertEqual(2, run_hook(f"cd {self.repo} && git push -u origin", cwd=NO_REPO).returncode)

    def test_git_dash_c_main_checkout_blocks(self):
        self.assertEqual(2, run_hook(f"git -C {self.repo} push origin HEAD", cwd=NO_REPO).returncode)

    def test_feature_branch_allows(self):
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", "recap-week-09"], check=True)
        self.assertEqual(run_hook("git push -u origin recap-week-09", cwd=self.repo).returncode, 0)


class ImplicitMainPushTest(unittest.TestCase):
    def test_implicit_pushes(self):
        guard = load_guard()
        for command, branch, should_block in IMPLICIT_PUSHES:
            with self.subTest(command=command, branch=branch):
                rest = command.split()[1:]
                reason = guard.implicit_main_push_reason(rest, branch)
                if should_block:
                    self.assertTrue(reason, f"{command!r} on {branch} should be blocked")
                else:
                    self.assertIsNone(reason, f"{command!r} on {branch} was blocked: {reason}")


if __name__ == "__main__":
    unittest.main()
