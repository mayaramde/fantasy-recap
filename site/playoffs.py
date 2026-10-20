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
    """league.json's "playoffs" block. Byes aren't read from it: the bracket gives them to the top seeds
    whenever the field isn't a power of two, so the count follows from the field size and the page can't
    disagree with the bracket it draws."""
    p = league.get("playoffs") or {}
    teams = max(2, int(p.get("teams", 4)))
    size = 1
    while size < teams:
        size *= 2
    return {"teams": teams, "byes": size - teams,
            "regular_season_weeks": int(p.get("regular_season_weeks", 14)),
            "first_round_week": int(p.get("first_round_week", p.get("regular_season_weeks", 14) + 1)),
            "championship_weeks": max(1, int(p.get("championship_weeks", 1))),
            "tiebreaker": p.get("tiebreaker", "points_for"), "reseed": bool(p.get("reseed", False)),
            "consolation_ladder": bool(p.get("consolation_ladder", False))}


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


def _schedule(schedule, ids):
    """{week: [(a, b), ...]} with int weeks (JSON gives string keys) and sorted pairs. A week whose pairs
    don't name every team exactly once (a typo, a stale id, a missing game) is dropped, so that week
    falls back to random opponents instead of crashing the build or quietly benching someone."""
    out = {}
    for w, pairs in (schedule or {}).items():
        pairs = sorted(tuple(sorted(pair)) for pair in pairs)
        if sorted(t for pair in pairs for t in pair) == sorted(ids):
            out[int(w)] = pairs
    return out


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


def _play_bracket(n, reseed, game, championship_weeks=1):
    """Single elimination over seeds 1..n, byes to the top seeds when n isn't a power of two;
    game(seed, seed, weeks) returns the winner. Every round is one week except the final, which is
    the total over `championship_weeks`. Returns (champion seed, [[(a, b, weeks, winner), ...] per round]).

    Four teams, the league's format: 1v4 and 2v3, then the final. Six would be 3v6 and 4v5, then
    1 v the 4/5 winner and 2 v the 3/6 winner, then the final."""
    size = 1
    while size < n:
        size *= 2
    slots = [s if s <= n else None for s in _bracket_order(size)]
    rounds = []
    while len(slots) > 1:
        weeks = championship_weeks if len(slots) == 2 else 1
        games, nxt = [], []
        for a, b in zip(slots[::2], slots[1::2]):
            if a is None or b is None:
                nxt.append(b if a is None else a)
                continue
            w = game(a, b, weeks)
            games.append((a, b, weeks, w))
            nxt.append(w)
        rounds.append(games)
        slots = nxt
        if reseed and len(slots) > 1:
            ranked = sorted(slots)
            slots = [ranked[s - 1] for s in _bracket_order(len(ranked))]
    return slots[0], rounds


def _random_pairs(ids, rng):
    ids = list(ids)
    rng.shuffle(ids)
    return list(zip(ids[::2], ids[1::2]))


def _simulate(teams, weeks_played, cfg, schedule, n_sims, seed, watch=None, shift=None):
    """`watch` names one remaining week. Every simulated season is then also filed under who won
    each of that week's games, so stakes() can read a team's odds given a win and given a loss off
    the same seasons, with every other game left to chance.

    `shift` ({team id: points per week}) moves a team's weekly mean, for trade_odds(). It never
    changes how many random numbers a season draws, so the same seed with and without it plays
    the same seasons and the difference is the shift alone."""
    ids = [t["id"] for t in teams]
    n = len(ids)
    mu, sigma = _ratings(teams)
    if shift:
        mu = {i: m + shift.get(i, 0.0) for i, m in mu.items()}
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
    # cond[team][won?] = [seasons, made the playoffs, won the title]
    cond = {i: {True: [0, 0, 0], False: [0, 0, 0]} for i in ids}

    for _ in range(n_sims):
        won = {}
        w = {i: base[i]["wins"] for i in ids}
        l = {i: base[i]["losses"] for i in ids}
        tie = {i: base[i]["ties"] for i in ids}
        pf = {i: base[i]["pf"] for i in ids}
        for wk in remaining:
            watching = wk == watch
            for a, b in schedule.get(wk) or _random_pairs(ids, rng):
                pa, pb = gauss(mu[a], sigma), gauss(mu[b], sigma)
                if watching and pa != pb:
                    won[a], won[b] = pa > pb, pb > pa
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

        def game(sa, sb, weeks):
            a, b = order[sa - 1], order[sb - 1]
            pa = sum(gauss(mu[a], sigma) for _ in range(weeks))
            pb = sum(gauss(mu[b], sigma) for _ in range(weeks))
            return sa if pa >= pb else sb

        champ, _ = _play_bracket(n_po, cfg["reseed"], game, cfg["championship_weeks"])
        title[order[champ - 1]] += 1
        for rank, i in enumerate(order if won else ()):
            if i in won:
                c = cond[i][won[i]]
                c[0] += 1
                c[1] += rank < n_po
                c[2] += rank == champ - 1

    return {"mu": mu, "sigma": sigma, "remaining": remaining, "cond": cond,
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


def win_prob(mu_a, mu_b, sigma):
    """P(a outscores b) when both weekly scores are normal with spread sigma (the difference has sd sigma*sqrt(2))."""
    return 0.5 * (1 + math.erf((mu_a - mu_b) / (sigma * 2)))


def _projected_bracket(ranked, cfg, mu, sigma):
    """The chalk bracket from projected seeds: each game names its favorite and her win probability,
    and the favorite advances. `rounds` runs first round to final, each with its first NFL week and
    how many weeks it spans (the final can be a multi-week total)."""
    probs = {}

    def game(sa, sb, weeks):
        a, b = ranked[sa - 1], ranked[sb - 1]
        p = win_prob(weeks * mu[a], weeks * mu[b], sigma * math.sqrt(weeks))
        fav, p = (sa, p) if p >= 0.5 else (sb, 1 - p)
        probs[(sa, sb)] = p
        return fav

    champ, played = _play_bracket(min(cfg["teams"], len(ranked)), cfg["reseed"], game, cfg["championship_weeks"])
    rounds, week = [], cfg["first_round_week"]
    for games in played:
        weeks = games[0][2]
        rounds.append({"week": week, "weeks": weeks, "games": [
            {"teams": [{"seed": s, "team_id": ranked[s - 1]} for s in (a, b)],
             "favorite": ranked[w - 1], "win_prob": round(probs[(a, b)], 3)} for a, b, _, w in games]})
        week += weeks
    out = {"rounds": rounds, "final": rounds[-1]["games"][0], "champion": ranked[champ - 1]}
    what_if = _what_if(ranked, cfg, mu, sigma)
    if what_if:
        out["what_if"] = what_if
    return out


def _what_if(ranked, cfg, mu, sigma):
    """Every path through a four-team bracket (two semifinals, then a final), for the page's what-if mode.

    The model that draws the chalk bracket answers every other pairing too: win_prob() is exact for any
    two teams, so each possible final carries its own probabilities and `est` is False. (`est` stays in
    the payload so a rougher source can flag itself and the page will print the "~".)

    A scenario is one winner per semifinal plus a champion: P = P(semi 1) * P(semi 2) * P(final),
    treating the three games as independent. The eight scenarios cover every outcome, so they sum to 1.
    Returns None for any other format (byes, six teams, a reseed), where the page keeps the plain bracket."""
    if min(cfg["teams"], len(ranked)) != 4 or cfg["reseed"]:
        return None

    def beats(a, b, weeks):
        return win_prob(weeks * mu[a], weeks * mu[b], sigma * math.sqrt(weeks))

    semis, p_semi, seed_of = [], {}, {}
    for sa, sb in ((1, 4), (2, 3)):
        a, b = ranked[sa - 1], ranked[sb - 1]
        pa = beats(a, b, 1)
        p_semi.update({a: pa, b: 1 - pa})
        seed_of.update({a: sa, b: sb})
        semis.append({"teams": [{"team_id": a, "seed": sa, "p": round(pa, 4)},
                                {"team_id": b, "seed": sb, "p": round(1 - pa, 4)}]})
    finals, scenarios = [], []
    for x in semis[0]["teams"]:
        for y in semis[1]["teams"]:
            a, b = sorted((x["team_id"], y["team_id"]), key=seed_of.get)
            pa = beats(a, b, cfg["championship_weeks"])
            finals.append({"teams": [a, b], "p": {str(a): round(pa, 4), str(b): round(1 - pa, 4)}, "est": False})
            reach = p_semi[a] * p_semi[b]
            for champ, pf in ((a, pa), (b, 1 - pa)):
                scenarios.append({"semis": [x["team_id"], y["team_id"]], "champion": champ,
                                  "reach": round(reach, 4), "p": round(reach * pf, 6), "est": False})
    return {"semis": semis, "finals": finals, "scenarios": scenarios}


def _projected_ladder(ranked, cfg, mu, sigma):
    """The consolation ladder for the Playoff picture's second view, or None when the league doesn't
    play one or the teams left out aren't exactly four (the only shape the page can draw).

    The four teams that miss the playoffs play on, seeded where the standings leave them (5 to 8 in this
    league). Round one pairs the outside seeds and the inside seeds (5v8, 6v7), the same shape as the
    playoff bracket. Then the ladder: the two winners meet for 5th and 6th, the two losers for 7th and 8th.
    Like the championship, that last round is the total over `championship_weeks`. The page offers the
    ladder's what-if beside the winners' one, so it carries the same two things: the chalk path, and
    `what_if` with every game priced by win_prob() (the same model) and every path's odds, which sum to 1.
    """
    n_po = min(cfg["teams"], len(ranked))
    low = ranked[n_po:]
    if not cfg["consolation_ladder"] or len(low) != 4:
        return None
    seed_of = {t: n_po + k + 1 for k, t in enumerate(low)}
    weeks = cfg["championship_weeks"]

    def beats(a, b, wk):
        return win_prob(wk * mu[a], wk * mu[b], sigma * math.sqrt(wk))

    def game(a, b, wk, places):
        a, b = sorted((a, b), key=seed_of.get)
        p = beats(a, b, wk)
        fav, p_fav = (a, p) if p >= 0.5 else (b, 1 - p)
        return {"teams": [{"seed": seed_of[t], "team_id": t} for t in (a, b)], "favorite": fav,
                "win_prob": round(p_fav, 3), "places": places}

    first = [(low[0], low[3]), (low[1], low[2])]
    r1 = [game(a, b, 1, None) for a, b in first]
    won = [g["favorite"] for g in r1]
    lost = [next(t for t in pair if t != w) for pair, w in zip(first, won)]
    top_places, bottom_places = [n_po + 1, n_po + 2], [n_po + 3, n_po + 4]
    top, bottom = game(won[0], won[1], weeks, top_places), game(lost[0], lost[1], weeks, bottom_places)
    standings = [top["favorite"], next(t["team_id"] for t in top["teams"] if t["team_id"] != top["favorite"]),
                 bottom["favorite"], next(t["team_id"] for t in bottom["teams"] if t["team_id"] != bottom["favorite"])]
    rounds = [{"week": cfg["first_round_week"], "weeks": 1, "games": r1},
              {"week": cfg["first_round_week"] + 1, "weeks": weeks, "games": [top, bottom]}]

    semis = [{"teams": [{"team_id": a, "seed": seed_of[a], "p": round(beats(a, b, 1), 4)},
                        {"team_id": b, "seed": seed_of[b], "p": round(1 - beats(a, b, 1), 4)}]}
             for a, b in first]
    p_r1 = {t["team_id"]: t["p"] for g in semis for t in g["teams"]}
    finals, scenarios = [], []
    for x in first[0]:
        for y in first[1]:
            a, b = sorted((x, y), key=seed_of.get)
            pa = beats(a, b, weeks)
            finals.append({"teams": [a, b], "p": {str(a): round(pa, 4), str(b): round(1 - pa, 4)}})
    for w0 in first[0]:
        for w1 in first[1]:
            l0, l1 = (next(t for t in pair if t != w) for pair, w in zip(first, (w0, w1)))
            reach = p_r1[w0] * p_r1[w1]
            top_a, top_b = sorted((w0, w1), key=seed_of.get)
            bot_a, bot_b = sorted((l0, l1), key=seed_of.get)
            p_top, p_bot = beats(top_a, top_b, weeks), beats(bot_a, bot_b, weeks)
            for tw, p_t in ((top_a, p_top), (top_b, 1 - p_top)):
                for bw, p_b in ((bot_a, p_bot), (bot_b, 1 - p_bot)):
                    scenarios.append({"r1": [w0, w1], "top": tw, "bottom": bw, "reach": round(reach, 4),
                                      "p": round(reach * p_t * p_b, 6)})
    return {"rounds": rounds, "places": [{"place": n_po + k + 1, "team_id": t} for k, t in enumerate(standings)],
            "what_if": {"semis": semis, "finals": finals, "scenarios": scenarios}}


def build(standings, weeks_played, league, schedule=None, n_sims=8000):
    """Playoff odds for every team, or None before any week has been played."""
    cfg = _config(league)
    weeks_played = sorted(w for w in weeks_played if w <= cfg["regular_season_weeks"])
    if not weeks_played or not standings:
        return None
    teams = _teams(standings, cfg["regular_season_weeks"])
    sched = _schedule(schedule, [t["id"] for t in teams])
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
    if min(cfg["teams"], len(ranked)) >= 2:
        bracket = _projected_bracket(ranked, cfg, now["mu"], now["sigma"])

    return {"config": cfg, "sims": n_sims, "sigma": round(now["sigma"], 2), "games_left": games_left,
            "real_schedule": all(w in sched for w in now["remaining"]),
            "weeks_played": weeks_played, "now_cut": now_cut, "bracket": bracket,
            "ladder": _projected_ladder(ranked, cfg, now["mu"], now["sigma"]), "teams": rows}


# ---------- trade_odds: what a trade does to both teams' odds ----------

def trade_odds(standings, weeks_played, league, shift, schedule=None, n_sims=8000):
    """Every team's playoff and title odds today and with `shift` applied ({team id: points per week},
    e.g. two teams' lineup gains from a trade), from the same simulated seasons, so a small change is
    the trade and not the dice. {"before": {id: {"playoff", "title"}}, "after": {...}}, or None before
    any week has been played or after the regular season. Never raises on a bad shift: unknown ids are
    ignored."""
    cfg = _config(league)
    weeks_played = sorted(w for w in weeks_played if w <= cfg["regular_season_weeks"])
    if not weeks_played or not standings or len(weeks_played) >= cfg["regular_season_weeks"]:
        return None
    teams = _teams(standings, cfg["regular_season_weeks"])
    sched = _schedule(schedule, [t["id"] for t in teams])
    seed = int.from_bytes(_digest(teams, weeks_played, cfg, sched, n_sims), "big")

    def odds(sim):
        return {i: {"playoff": round(s["playoff"], 4), "title": round(s["title"], 4)} for i, s in sim["teams"].items()}

    before = odds(_simulate(teams, weeks_played, cfg, sched, n_sims, seed))
    after = odds(_simulate(teams, weeks_played, cfg, sched, n_sims, seed, shift=shift))
    return {"before": before, "after": after}


# ---------- stakes: what this week's game does to a team's playoff odds ----------

MIN_BUCKET = 100         # fewer simulated seasons than this on one side of a game is too few to quote


def _game_weight(a, b):
    """How much one game matters, for ranking the week's slate (the top one is "Biggest swing").

    `a` and `b` are the two teams' stakes rows. Bigger means it leads the page."""
    # The sum, so a game that moves both teams leads one that only moves one of them.
    return a["swing"] + b["swing"]


def stakes(standings, weeks_played, league, week, games, n_sims=8000, schedule=None):
    """Each team's playoff and title odds if she wins `week`'s game and if she loses it.

    `games` is that week's real pairings, [(team_id, team_id), ...]. One simulation of the rest of the
    season, read twice: the seasons where she won that game, and the ones where she lost. Every other
    game, that week's included, is left to chance, so the two numbers sit either side of her odds today
    (near enough: this is its own run of the simulation, not the Standings page's). `schedule` is the same
    optional real schedule build() takes, for the weeks after this one.

    Returns {"week", "sims", "games": [{"key", "teams": [row, row]}, ...]} with the games ranked by
    _game_weight, or {} when there is nothing honest to say: no finished week, a playoff week, an
    earlier week still unplayed, or pairings that don't name every team once. Never raises.
    """
    try:
        cfg = _config(league)
        played = sorted(w for w in weeks_played if w <= cfg["regular_season_weeks"])
        remaining = [w for w in range(1, cfg["regular_season_weeks"] + 1) if w not in played]
        if not played or not standings or not remaining or week != remaining[0]:
            return {}
        teams = _teams(standings, cfg["regular_season_weeks"])
        sched = _schedule({**(schedule or {}), week: games}, [t["id"] for t in teams])
        if week not in sched:
            return {}
        key = hashlib.sha256(b"stakes" + _digest(teams, played, cfg, sched, n_sims)).digest()
        if key not in _CACHE:
            sim = _simulate(teams, played, cfg, sched, n_sims, int.from_bytes(key, "big"), watch=week)
            _CACHE[key] = {"week": week, "sims": n_sims, "games": _stakes_games(sim["cond"], sched[week])}
        return copy.deepcopy(_CACHE[key])
    except (KeyError, TypeError, ValueError, AttributeError):
        return {}


def _stakes_games(cond, pairs):
    def row(i):
        win, lose = cond[i][True], cond[i][False]
        decided = win[0] + lose[0]
        out = {"team_id": i, "p_win": round(win[0] / decided, 4) if decided else None}
        for name, c in (("win", win), ("lose", lose)):
            ok = c[0] >= MIN_BUCKET
            out[name] = round(c[1] / c[0], 4) if ok else None
            out[f"title_{name}"] = round(c[2] / c[0], 4) if ok else None
        known = out["win"] is not None and out["lose"] is not None
        out["swing"] = round(out["win"] - out["lose"], 4) if known else 0.0
        return out

    out = [{"key": f"{a}-{b}", "teams": [row(a), row(b)]} for a, b in pairs]
    out.sort(key=lambda g: _game_weight(*g["teams"]), reverse=True)
    return out
