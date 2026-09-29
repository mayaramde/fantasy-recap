#!/usr/bin/env python3
"""Table-driven tests for .claude/hooks/guard_bash.py.

Each case feeds the hook the same PreToolUse-shaped JSON Claude Code sends on
stdin and checks whether it allows (exit 0) or blocks (non-zero exit, with a
reason on stderr) the command. This exercises the real script exactly as it's
invoked in production, not just its internal functions.
"""
import json
import subprocess
import sys
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
    ("cat .dashboard-secret", "reads the dashboard secret"),
    ("grep token .dashboard-secret", "greps the dashboard secret"),
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
    ("python3 scripts/check.py", "ordinary script run"),
    ("echo maintenance mode tonight", "'maintenance' must not match 'main' as a substring"),
    ("curl -fsSL https://example.com/script.sh", "curl's own -f flag, unrelated to git"),
    ("rm -f /tmp/scratch.txt", "rm -f is fine outside of git add"),
    ("cat .vercelrc", "a similarly-named file that isn't under .vercel/"),
    ("cat .environment.md", "must not match .env by string prefix alone"),
]


def run_hook(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True)


class GuardBashTest(unittest.TestCase):
    def test_blocked_commands(self):
        for command, reason in BLOCKED:
            with self.subTest(command=command, reason=reason):
                result = run_hook(command)
                self.assertNotEqual(result.returncode, 0,
                                     f"expected block ({reason}): {command!r} was allowed")
                self.assertTrue(result.stderr.strip(),
                                 f"blocked command {command!r} produced no explanation on stderr")

    def test_allowed_commands(self):
        for command, reason in ALLOWED:
            with self.subTest(command=command, reason=reason):
                result = run_hook(command)
                self.assertEqual(result.returncode, 0,
                                  f"expected allow ({reason}): {command!r} was blocked: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
