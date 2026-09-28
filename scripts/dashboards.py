"""Per-manager private dashboards: link tokens, and the payload each page gets.

Each manager gets one unguessable URL (/me/<token>/) and her own HTML file containing
only her data, so a teammate who somehow lands on another page still can't read anyone
else's advice out of the payload.

Tokens are derived, not stored: HMAC-SHA256(secret, "<season>:<team_id>"). The secret
lives in .dashboard-secret (gitignored, created on first use) or the DASHBOARD_SECRET
environment variable, which is how GitHub Actions gets it. Deriving them means the links
are stable across rebuilds and never committed, and rotating the secret rotates all 8.

`python3 scripts/links.py` prints the links to hand out. This module is imported by
site/build.py; it is not a command-line tool itself.
"""

import hashlib
import hmac
import json
import os
import secrets
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = ROOT / ".dashboard-secret"
TOKEN_CHARS = 20  # 80 bits of hex; not guessable, still short enough to text


def secret(create=False):
    """The link secret, from the environment or .dashboard-secret.

    Returns None when there is none and create is False, so a build can say clearly
    that it cannot produce dashboards instead of silently producing wrong links.
    """
    env = os.environ.get("DASHBOARD_SECRET", "").strip()
    if env:
        return env
    if SECRET_FILE.exists():
        value = SECRET_FILE.read_text().strip()
        if value:
            return value
    if not create:
        return None
    value = secrets.token_hex(32)
    SECRET_FILE.write_text(value + "\n")
    SECRET_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600: only Maya's account
    return value


def token(season, team_id, key):
    msg = f"{season}:{team_id}".encode()
    return hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()[:TOKEN_CHARS]


def short(manager):
    """'Samantha (Sam)' -> 'Samantha', matching the rest of the site."""
    return manager.split(" (")[0]


def slug(manager):
    return short(manager).lower().replace(" ", "-")


def advice_dir(season, week):
    return ROOT / "advice" / str(season) / f"week-{week:02d}"


def load_advice(season, week, manager):
    """The written advice for one manager, or None if it hasn't been generated."""
    path = advice_dir(season, week) / f"{slug(manager)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def latest_advice_week(season, teams):
    """Newest week that has advice for every team; 0 if none does.

    All-or-nothing on purpose: a half-generated week would leave some managers looking
    at last week's advice while others see this week's, with no way to tell.
    """
    root = ROOT / "advice" / str(season)
    if not root.exists():
        return 0
    weeks = []
    for d in sorted(root.glob("week-*")):
        week = int(d.name.split("-")[1])
        if all((d / f"{slug(t['manager'])}.json").exists() for t in teams):
            weeks.append(week)
    return max(weeks, default=0)


def roster_view(team_facts):
    """Her current roster as captured, starters first, with what each player scored."""
    keys = ("name", "pos", "slot", "points", "projected")
    return {
        "starters": [{k: p[k] for k in keys} for p in team_facts["starters"]],
        "bench": [{k: p[k] for k in keys} for p in team_facts["bench"]],
    }


def payload(team, season_stats, facts_by_week, advice, league):
    """Everything one dashboard page needs — and nothing about anyone else's plans.

    Opponent scores and league standings are already on the public site, so they stay;
    other managers' advice, waiver targets and start/sit calls are never included.
    """
    tid = team["team_id"]
    me = next(s for s in season_stats["standings"] if s["team_id"] == tid)
    rank = season_stats["standings"].index(me) + 1
    latest = max(facts_by_week) if facts_by_week else None
    team_facts = next((t for t in facts_by_week[latest]["teams"] if t["team_id"] == tid), None) if latest else None

    return {
        "league": {"name": league["name"].strip(), "season": league["season"], "scoring": league["scoring"]},
        "manager": short(team["manager"]),
        "team_name": team["team_name"],
        "team_id": tid,
        "rank": rank,
        "teams_in_league": len(season_stats["standings"]),
        "record": {k: me[k] for k in ("wins", "losses", "ties")},
        "points_for": me["points_for"],
        "points_against": me["points_against"],
        "avg": me["avg"],
        "streak": me["streak"],
        "all_play": {"w": me["all_play_w"], "l": me["all_play_l"]},
        "bench_left": me["bench_left"],
        "weekly": me["weekly"],
        "awards": me["awards"],
        "roster_week": latest,
        "roster_captured_at": facts_by_week[latest]["captured_at"] if latest else None,
        "roster_complete": facts_by_week[latest]["complete"] if latest else None,
        "roster": roster_view(team_facts) if team_facts else None,
        "last_week": {
            "points": team_facts["points"], "result": team_facts["result"],
            "optimal": team_facts["optimal_points"], "points_left": team_facts["points_left_on_bench"],
            "swaps": team_facts["lineup_swaps"],
        } if team_facts else None,
        "advice": advice,
    }
