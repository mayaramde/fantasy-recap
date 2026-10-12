# Working in Vercel

Vercel is where the league website lives. This is the page to reread when something
needs doing there and the last time was three weeks ago.

Nothing here requires knowing how Vercel works in general — only how *this* project
uses it, which is in a couple of ways deliberately unusual.

## 1. The four words Vercel uses

Almost everything in the dashboard is one of these:

- **Project** — the container. One project = one website. Ours is called
  `fantasy-recap`, inside a personal scope (a workspace) called `maya-fd13`.
- **Deployment** — one frozen copy of the site. Every deploy makes a *new* one;
  nothing is ever edited in place. Each gets its own permanent URL like
  `fantasy-recap-ptbjydozg-maya-fd13.vercel.app`. Old ones stay reachable forever.
- **Domain / alias** — the friendly name pointing at whichever deployment is
  currently "the site". Ours is **fantasyforthegirls.vercel.app**. Deploying to
  production means: make a new deployment, then move this pointer to it.
- **Environment variable** — a named secret or setting handed to code at runtime,
  so it isn't written in the repo. We don't need any: ESPN is read anonymously (§5b).

The useful consequence of "deployments are frozen": a bad deploy is never
destructive. The previous one still exists, and rolling back just moves the pointer.

## 2. Our project at a glance

| | |
|---|---|
| Scope (workspace) | `maya-fd13` |
| Project | `fantasy-recap` |
| Live site | https://fantasyforthegirls.vercel.app |
| Plan | Hobby (free) |
| Search engines | Blocked — `noindex` header, meta tag and robots.txt |

Log in at [vercel.com](https://vercel.com) and the project is on the dashboard. Or
from this repo, `vercel ls` prints the recent deployments without opening a browser.

## 3. How code gets live here (and why Vercel's own git integration is off for `main`)

Normally Vercel watches your GitHub repo and builds-and-deploys every push, on Vercel's
own servers. **We turned that off for `main`.** In `vercel.json`:

```json
{ "git": { "deploymentEnabled": { "main": false } } }
```

The reason: the Live page is built from ESPN data captured on Maya's Mac (or in CI) that
isn't committed for the in-progress week. A build on Vercel's own servers would build from
the repo alone and publish a site with that data missing. Turning off Vercel's *own* git
integration for `main` means a merge can never silently wipe the Live page that way.

**Every other branch still gets an automatic preview.** Push a branch (or open a PR) and
Vercel builds it on its own servers and posts the preview link on the PR. That build only
sees what's committed on the branch, so it shows the draft copy with the committed weeks.
The live week isn't committed, so the build borrows it: `scripts/vercel_build.sh` sets
`FANTASY_LIVE_FROM` to the league site, and `site/build.py` reads the live-week data out of that
page (best effort; if the fetch fails the preview just has no Live or Coach tab). Only the draft
copy does this, and only when the live week is newer than the branch's last recap. What it shows is
production's snapshot (its standings and odds, published recaps only): good for reviewing design, not a
computation over the branch's own data. It's for looking at design and code changes, never the
league's site: it can't touch production, and Deployment Protection (§7) keeps it behind
Maya's Vercel login. When a preview needs the live week too, `scripts/deploy.sh --preview`
is still the way (§8).

So the only thing that changes the league's site is **`scripts/deploy.sh`**. It runs `vercel build`
on the machine it's on (which calls `scripts/vercel_build.sh` → `site/build.py`), then
uploads the finished bundle with `vercel deploy --prebuilt`. Vercel's servers never build
the league's site; every production build happens on a machine we control, one that can
capture fresh ESPN data first.

Three things run that script:

1. **GitHub Actions, scheduled** — the `live-update` workflow's cron schedule, hourly
   during games plus a daily morning run. It captures the current week fresh from ESPN
   before deploying, so the in-progress week is never missing.
2. **GitHub Actions, on push** — the same workflow also has a `push` trigger, scoped to
   the paths that actually affect the site (`recaps/`, `data/`, `site/`, `scripts/`, `api/`,
   `league.json`, `vercel.json`). This is what gets a merged recap live within minutes
   instead of waiting for the next scheduled run — it's a GitHub Actions job calling our
   own build script, not Vercel's git integration, so the "isn't committed yet" problem
   above doesn't apply: a published recap's data is committed by the time this fires.
3. **This Mac** — any time `scripts/deploy.sh` is run by hand. With the push trigger in
   place this is a backstop, not the routine path — useful if CI is down or for a quick
   manual check, but `recap-ship` no longer runs it as a normal step.

Worth saying plainly, because it surprises everyone:

> Committed is not the same as live, and live is not the same as committed.

Work can sit merged on `main` and not be on the site (nobody has deployed since).
Work can be on the site and not committed anywhere (deployed from this Mac off an
unmerged branch). Neither is broken — it's just two separate tracks.

## 4. The five screens worth knowing

Open the project and you'll see a row of tabs. These are the ones that matter:

- **Deployments** — every deploy, newest first, with who made it and whether it
  worked. Click one to see its build log, or to roll back to it. This is the first
  place to look when something seems stale or broken. Most rows are now automatic
  branch previews (§3); roll back only to a row marked **Production**, never promote a
  branch preview (the build refuses, see §7).
- **Logs** (and **Observability**) — what the `/api/live` function actually did on
  real requests: status codes, errors, how long it took. The only way to see why
  the Live page isn't refreshing.
- **Settings → Environment Variables** — empty on purpose. See §5b.
- **Analytics** — page views, via the CDN script described in §5a.
- **Settings → General** — the project name, and the delete button. Rarely needed.

Everything else in that navigation (Storage, Firewall, Flags, AI, Integrations,
Speed Insights) is for things this project doesn't use. You can ignore all of it.

## 5. Two things worth knowing

### a. Web Analytics — enabled and configured

Enabled for the project on 2026-09-28, and configured to use Vercel's CDN-based
analytics script on 2026-09-28.

This project uses the CDN approach (`https://cdn.vercel-insights.com/v1/script.js`)
rather than the npm package approach, because the CDN script reports directly to
Vercel's servers without needing any build-time integration. The script tag is added
in `site/build.py` in the `standalone()` function, so it's included in every generated
HTML page.

The `@vercel/analytics` npm package needs a JavaScript framework build to inject it; this
site is static HTML written by `site/build.py`, so a plain script tag is the simpler fit.

Analytics data appears in the Vercel dashboard after the site receives traffic. The
script loads with `defer`, so it doesn't block page rendering.

### b. No ESPN secrets

The league is **public** on ESPN (the commissioner set it on 2026-10-09), so everything the
site reads from ESPN is read anonymously: the `live-update` capture in GitHub Actions, the
`/api/live` function on Vercel, and the headless fallback on the Mac. There are no ESPN
cookies anywhere any more, and no environment variables to set.

If `ESPN_S2` and `ESPN_SWID` are still listed under Settings → Environment Variables (they
were added 2026-09-28, back when the league was private), delete them. Nothing reads them.

## 6. If ESPN stops answering

Every ESPN read depends on the league staying public. If it's ever switched back to private,
ESPN starts answering **401**, and you'll see it in two places at once:

- A GitHub issue titled **"live-update failing: ESPN league not public"** (the workflow opens it).
- The Live page stuck on old numbers, with `/api/live` returning **503** and
  `"ESPN 401: is the league still public on ESPN?"`.

The fix is one setting, not a secret: the commissioner sets the league back to public in
ESPN's league settings. Nothing in the repo or on Vercel needs changing.

Other failure emails:

- **"Could not retrieve Project Settings"** → the Vercel token. It has to be scoped to the
  whole account, not to the `fantasy-recap` project: `vercel build` looks the account up first, and a
  project-scoped token gets "User not found" for that, which the CLI reports as the message above.

GitHub Actions also needs `VERCEL_TOKEN` so it can deploy. It's listed in the
header comment of `.github/workflows/live-update.yml`.

## 7. Things that will bite you

- **Changing an environment variable doesn't change the live site.** It applies to
  the *next* deployment. Always redeploy after.
- **Share the alias, never a deployment URL.** Deployment Protection is on (Vercel
  Authentication, Standard Protection): every long `fantasy-recap-xxxxx-maya-fd13.vercel.app`
  URL, including every `--preview` deploy, redirects to a Vercel login and only opens for
  Maya's account. Only the production aliases are public, so send the league
  `fantasyforthegirls.vercel.app`. Handy the other way round too: a stray deployment or
  draft-preview link can't leak anything. Settings → Deployment Protection is where to change it.
- **Rolling back is safe, to a Production deployment.** Deployments → filter to
  Production → pick a good one → Instant Rollback. The pointer moves; nothing is rebuilt
  or lost. Don't promote a branch preview: it was built from committed data only, so
  Vercel would rebuild it for production without the live week. `scripts/vercel_build.sh`
  refuses that build rather than publish the draft copy to the league.

## 8. Cheat sheet

```bash
vercel whoami                    # which account the CLI is using
vercel ls                        # recent deployments, newest first
scripts/deploy.sh                # build locally + publish to the live site
scripts/deploy.sh --preview      # throwaway URL for reviewing a draft, with this Mac's live week
git push -u origin my-branch     # automatic preview URL from committed data (any branch but main)
vercel env ls                    # variable names on the project (never values)
vercel env add NAME production   # add one, prompts for the value
vercel logs <deployment-url>     # runtime output from a deployment
```

One-time setup on a new Mac: `vercel login`, then `vercel link` to connect this
folder to the project. GitHub Actions can't run `vercel link`, so `scripts/deploy.sh`
runs `vercel pull` there instead, which rebuilds that link from `VERCEL_ORG_ID`,
`VERCEL_PROJECT_ID` and the token.
