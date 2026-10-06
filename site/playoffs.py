"""Playoff odds for the Standings page: a Monte Carlo of the rest of the regular season and the bracket.

Pure functions over season_payload()'s standings rows and league.json's "playoffs" block. Stdlib only
(the Vercel build has no numpy). The RNG is seeded from a sha256 of the inputs, so a rebuild of the same
weeks gives the same numbers, and results are memoized because render() runs twice per build.

Nothing here is a mathematical clinch: a team that made the playoffs in every simulated season is a
"Near lock", never "Clinched".
"""
import copy
import hashlib
import json
import math
import random

PRIOR_GAMES = 3          # shrink each team's mean toward the league average by this many phantom games
SIGMA_DEFAULT = 25.0     # weekly score spread when there's too little data to measure one
SIGMA_MIN, SIGMA_MAX = 18.0, 35.0
SIGMA_MIN_DF = 4

_CACHE = {}


def _config(league):
    p = league.get("playoffs") or {}
    return {"teams": int(p.get("teams", 6)), "byes": int(p.get("byes", 2)),
            "regular_season_weeks": int(p.get("regular_season_weeks", 14)),
            "first_round_week": int(p.get("first_round_week", p.get("regular_season_weeks", 14) + 1)),
            "tiebreaker": p.get("tiebreaker", "points_for"), "reseed": bool(p.get("reseed", False))}


def _teams(standings, last_week):
    """The few fields the simulation reads, in a JSON-able shape (also what the input hash covers).

    Records are rebuilt from regular-season games only: once a playoff week has a recap, the
    standings rows count it too, and a playoff win must not move anyone's seed."""
    out = []
    for s in standings:
        games = [{"week": g["week"], "points": g["points"], "opp": g["opponent_id"], "result": g["result"]}
                 for g in s["weekly"] if g["week"] <= last_week]
        out.append({"id": s["team_id"], "games": games,
                    "wins": sum(g["result"] == "W" for g in games), "losses": sum(g["result"] == "L" for g in games),
                    "ties": sum(g["result"] == "T" for g in games), "pf": round(sum(g["points"] for g in games), 2)})
    return out


def _schedule(schedule):
    """{week: [(a, b), ...]} with int weeks (JSON gives string keys) and sorted pairs."""
    return {int(w): sorted(tuple(sorted(pair)) for pair in pairs) for w, pairs in (schedule or {}).items()}


def _rank_key(t):
    return (t["wins"] + 0.5 * t["ties"], t["pf"])


def _rewind(teams, week):
    """(teams, pairings): the standings as they stood before `week`, and who actually played whom that week."""
    out, pairs = [], set()
    for t in teams:
        t = copy.deepcopy(t)
        for g in [g for g in t["games"] if g["week"] == week]:
            t["games"].remove(g)
            t["pf"] = round(t["pf"] - g["points"], 2)
            t[{"W": "wins", "L": "losses", "T": "ties"}[g["result"]]] -= 1
            pairs.add(tuple(sorted((t["id"], g["opp"]))))
        out.append(t)
    return out, sorted(pairs)


def _ratings(teams):
    """(mu by team, sigma): shrunk weekly means and the pooled within-team standard deviation."""
    scores = [g["points"] for t in teams for g in t["games"]]
    avg = sum(scores) / len(scores) if scores else 0.0
    mu, ss, df = {}, 0.0, 0
    for t in teams:
        pts = [g["points"] for g in t["games"]]
        mu[t["id"]] = (sum(pts) + PRIOR_GAMES * avg) / (len(pts) + PRIOR_GAMES)
        if len(pts) > 1:
            m = sum(pts) / len(pts)
            ss += sum((x - m) ** 2 for x in pts)
            df += len(pts) - 1
    sigma = SIGMA_DEFAULT if df < SIGMA_MIN_DF else min(SIGMA_MAX, max(SIGMA_MIN, math.sqrt(ss / df)))
    return mu, sigma


def _bracket_order(size):
    """Standard bracket slots for a power-of-two field: 1, 8, 4, 5, 2, 7, 3, 6 for eight."""
    order = [1]
    while len(order) < size:
        top = 2 * len(order) + 1
        order = [x for s in order for x in (s, top - s)]
    return order


def _play_bracket(n, reseed, game):
    """Single elimination over seeds 1..n, byes to the top seeds; game(seed, seed) returns the winner.

    For six teams that is exactly the league's bracket: 3v6 and 4v5, then 1 v the 4/5 winner and
    2 v the 3/6 winner, then the final."""
    size = 1
    while size < n:
        size *= 2
    slots = [s if s <= n else None for s in _bracket_order(size)]
    while len(slots) > 1:
        slots = [a if b is None else b if a is None else game(a, b) for a, b in zip(slots[::2], slots[1::2])]
        if reseed and len(slots) > 1:
            ranked = sorted(slots)
            slots = [ranked[s - 1] for s in _bracket_order(len(ranked))]
    return slots[0]


def _random_pairs(ids, rng):
    ids = list(ids)
    rng.shuffle(ids)
    return list(zip(ids[::2], ids[1::2]))


def _simulate(teams, weeks_played, cfg, schedule, n_sims, seed):
    ids = [t["id"] for t in teams]
    n = len(ids)
    mu, sigma = _ratings(teams)
    played = set(weeks_played)
    remaining = [w for w in range(1, cfg["regular_season_weeks"] + 1) if w not in played]
    n_po = min(cfg["teams"], n)
    rng = random.Random(seed)
    gauss = rng.gauss
    base = {t["id"]: t for t in teams}

    playoff = dict.fromkeys(ids, 0)
    bye = dict.fromkeys(ids, 0)
    title = dict.fromkeys(ids, 0)
    seeds = {i: [0] * n for i in ids}
    sim_w = dict.fromkeys(ids, 0)
    sim_l = dict.fromkeys(ids, 0)

    for _ in range(n_sims):
        w = {i: base[i]["wins"] for i in ids}
        l = {i: base[i]["losses"] for i in ids}
        tie = {i: base[i]["ties"] for i in ids}
        pf = {i: base[i]["pf"] for i in ids}
        for wk in remaining:
            for a, b in schedule.get(wk) or _random_pairs(ids, rng):
                pa, pb = gauss(mu[a], sigma), gauss(mu[b], sigma)
                pf[a] += pa
                pf[b] += pb
                if pa > pb:
                    w[a] += 1
                    l[b] += 1
                elif pb > pa:
                    w[b] += 1
                    l[a] += 1
                else:
                    tie[a] += 1
                    tie[b] += 1
        order = sorted(ids, key=lambda i: (w[i] + 0.5 * tie[i], pf[i]), reverse=True)
        for rank, i in enumerate(order):
            seeds[i][rank] += 1
            sim_w[i] += w[i] - base[i]["wins"]
            sim_l[i] += l[i] - base[i]["losses"]
            if rank < n_po:
                playoff[i] += 1
            if rank < cfg["byes"]:
                bye[i] += 1

        def game(sa, sb):
            a, b = order[sa - 1], order[sb - 1]
            return sa if gauss(mu[a], sigma) >= gauss(mu[b], sigma) else sb

        title[order[_play_bracket(n_po, cfg["reseed"], game) - 1]] += 1

    return {"mu": mu, "sigma": sigma, "remaining": remaining,
            "teams": {i: {"playoff": playoff[i] / n_sims, "bye": bye[i] / n_sims, "title": title[i] / n_sims,
                          "seed_dist": [c / n_sims for c in seeds[i]],
                          "avg_seed": sum((r + 1) * c for r, c in enumerate(seeds[i])) / n_sims,
                          "sim_w": sim_w[i] / n_sims, "sim_l": sim_l[i] / n_sims} for i in ids}}


def _digest(teams, weeks_played, cfg, schedule, n_sims):
    blob = json.dumps({"teams": teams, "weeks": weeks_played, "cfg": cfg, "n": n_sims,
                       "schedule": sorted((w, p) for w, p in schedule.items())}, sort_keys=True)
    return hashlib.sha256(blob.encode()).digest()


def _label(t, games_left, in_now):
    if not games_left:
        return "In" if in_now else "Out"
    if t["playoff"] >= 0.995:
        return "Near lock"
    if t["bye"] >= 0.5:
        return "Bye race"
    if t["playoff"] >= 0.8:
        return "Comfortable"
    if t["playoff"] >= 0.4:
        return "Bubble"
    if t["playoff"] <= 0.005:
        return "Near out"
    return "Long shot"


def _projected_bracket(ranked, mu, sigma):
    """The chalk bracket from projected seeds: each game names its favorite and her win probability,
    and the favorite advances."""
    def game(sa, sb):
        a, b = ranked[sa - 1], ranked[sb - 1]
        p = 0.5 * (1 + math.erf((mu[a] - mu[b]) / (sigma * 2)))   # P(a > b), score difference sd = sigma*sqrt(2)
        fav, p = (sa, p) if p >= 0.5 else (sb, 1 - p)
        return {"teams": [{"seed": s, "team_id": ranked[s - 1]} for s in (sa, sb)],
                "favorite": ranked[fav - 1], "win_prob": round(p, 3), "_seed": fav}

    round1 = [game(3, 6), game(4, 5)]
    semis = [game(1, round1[1]["_seed"]), game(2, round1[0]["_seed"])]
    final = game(semis[0]["_seed"], semis[1]["_seed"])
    for g in round1 + semis + [final]:
        del g["_seed"]
    return {"round1": round1, "semis": semis, "final": final, "champion": final["favorite"]}


def build(standings, weeks_played, league, schedule=None, n_sims=8000):
    """Playoff odds for every team, or None before any week has been played."""
    cfg = _config(league)
    weeks_played = sorted(w for w in weeks_played if w <= cfg["regular_season_weeks"])
    if not weeks_played or not standings:
        return None
    teams = _teams(standings, cfg["regular_season_weeks"])
    sched = _schedule(schedule)
    key = _digest(teams, weeks_played, cfg, sched, n_sims)
    if key not in _CACHE:
        _CACHE[key] = _build(teams, weeks_played, cfg, sched, n_sims, key)
    return copy.deepcopy(_CACHE[key])


def _build(teams, weeks_played, cfg, sched, n_sims, key):
    now = _simulate(teams, weeks_played, cfg, sched, n_sims, int.from_bytes(key, "big"))
    before = None
    if len(weeks_played) > 1:
        earlier, pairs = _rewind(teams, weeks_played[-1])
        prev_sched = {**sched, weeks_played[-1]: pairs}
        prev_key = _digest(earlier, weeks_played[:-1], cfg, prev_sched, n_sims)
        before = _simulate(earlier, weeks_played[:-1], cfg, prev_sched, n_sims, int.from_bytes(prev_key, "big"))

    n_po = min(cfg["teams"], len(teams))
    now_cut = [t["id"] for t in sorted(teams, key=_rank_key, reverse=True)[:n_po]]
    games_left = len(now["remaining"])
    base = {t["id"]: t for t in teams}
    ranked = sorted(now["teams"], key=lambda i: (now["teams"][i]["avg_seed"], -now["teams"][i]["playoff"], i))

    rows = []
    for proj_seed, i in enumerate(ranked, 1):
        s = now["teams"][i]
        row = {"team_id": i, "playoff": round(s["playoff"], 4), "bye": round(s["bye"], 4),
               "title": round(s["title"], 4), "seed_dist": [round(x, 4) for x in s["seed_dist"]],
               "avg_seed": round(s["avg_seed"], 2), "proj_seed": proj_seed,
               "proj_wins": round(base[i]["wins"] + s["sim_w"], 1),
               "proj_losses": round(base[i]["losses"] + s["sim_l"], 1),
               "trend": round(s["playoff"] - before["teams"][i]["playoff"], 4) if before else None}
        row["label"] = _label(s, games_left, i in now_cut)
        rows.append(row)

    bracket = None
    if cfg["teams"] == 6 and cfg["byes"] == 2 and len(ranked) >= 6:
        bracket = _projected_bracket(ranked, now["mu"], now["sigma"])

    return {"config": cfg, "sims": n_sims, "sigma": round(now["sigma"], 2), "games_left": games_left,
            "real_schedule": all(w in sched for w in now["remaining"]),
            "weeks_played": weeks_played, "now_cut": now_cut, "bracket": bracket, "teams": rows}
