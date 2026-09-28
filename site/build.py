"""Build the recap page from data/ facts + recaps/ writeups.

Writes two self-contained pages:
  site/dist/index.html    league page: only weeks whose recap has "status": "published"
  site/dist/preview.html  Maya's review copy: published + draft weeks (drafts are marked)

Usage: python3 site/build.py [--season 2026]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
LEAGUE = json.loads((ROOT / "league.json").read_text())

CALLOUT_KEYS = ("game_balls", "flags", "tough_breaks", "glossary")
PLAYER_KEYS = ("name", "pos", "slot", "points", "projected")


def side(t):
    return {
        "team_id": t["team_id"], "manager": t["manager"], "team_name": t["team_name"],
        "points": t["points"], "projected": t["projected"], "optimal": t["optimal_points"],
        "result": t["result"],
        "starters": [{k: p[k] for k in PLAYER_KEYS} for p in t["starters"]],
        "bench": [{k: p[k] for k in PLAYER_KEYS} for p in t["bench"]],
    }


def week_payload(facts, recap):
    teams = {t["team_id"]: t for t in facts["teams"]}
    games, seen = [], set()
    for t in facts["teams"]:
        key = tuple(sorted((t["team_id"], t["opponent_id"])))
        if key in seen:
            continue
        seen.add(key)
        a, b = teams[key[0]], teams[key[1]]
        winner, loser = (a, b) if a["points"] >= b["points"] else (b, a)
        games.append({"key": f"{key[0]}-{key[1]}", "winner": side(winner), "loser": side(loser),
                      "blurb": recap.get("matchups", {}).get(f"{key[0]}-{key[1]}", "")})
    games.sort(key=lambda g: g["winner"]["points"] + g["loser"]["points"], reverse=True)

    lg = facts["league"]
    return {
        "week": facts["week"],
        "status": recap.get("status", "draft"),
        "complete": facts["complete"],
        "headline": recap.get("headline", ""),
        "dek": recap.get("dek", ""),
        "games": games,
        **{k: recap.get(k, []) for k in CALLOUT_KEYS},
        "standings": facts["standings"],
        "top_performers": lg["top_performers"],
        "high_score": lg["high_score"],
        "low_score": lg["low_score"],
        "median": lg["median_score"],
    }


def render(weeks, preview):
    template = (SITE / "template.html").read_text()
    data = {
        "league": {"name": LEAGUE["name"], "season": LEAGUE["season"], "scoring": LEAGUE["scoring"]},
        "preview": preview,
        "weeks": weeks,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = "Flag on the Play Preview" if preview else "Flag on the Play"
    return template.replace("__PAGE_TITLE__", title).replace("__RECAP_DATA__", blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    args = ap.parse_args()

    weeks = []
    for recap_path in sorted((ROOT / "recaps" / str(args.season)).glob("week-*.json")):
        recap = json.loads(recap_path.read_text())
        facts_path = ROOT / "data" / str(args.season) / f"week-{recap['week']:02d}" / "facts.json"
        if not facts_path.exists():
            raise SystemExit(f"{recap_path.name}: missing {facts_path.relative_to(ROOT)}; run scripts/analyze.py")
        weeks.append(week_payload(json.loads(facts_path.read_text()), recap))
    weeks.sort(key=lambda w: w["week"])

    dist = SITE / "dist"
    dist.mkdir(exist_ok=True)
    published = [w for w in weeks if w["status"] == "published"]
    (dist / "index.html").write_text(render(published, preview=False))
    (dist / "preview.html").write_text(render(weeks, preview=True))
    print(f"index.html: weeks {[w['week'] for w in published] or 'none yet'}")
    print(f"preview.html: weeks {[(w['week'], w['status']) for w in weeks]}")


if __name__ == "__main__":
    main()
