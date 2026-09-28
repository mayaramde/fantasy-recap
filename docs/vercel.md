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
  currently "the site". Ours is **fantasy-recap-eight.vercel.app**. Deploying to
  production means: make a new deployment, then move this pointer to it.
- **Environment variable** — a named secret or setting handed to code at runtime,
  so it isn't written in the repo. Ours will hold the ESPN login cookies.

The useful consequence of "deployments are frozen": a bad deploy is never
destructive. The previous one still exists, and rolling back just moves the pointer.

## 2. Our project at a glance

| | |
|---|---|
| Scope (workspace) | `maya-fd13` |
| Project | `fantasy-recap` |
| Live site | https://fantasy-recap-eight.vercel.app |
| Plan | Hobby (free) |
| Search engines | Blocked — `noindex` header, meta tag and robots.txt |

Log in at [vercel.com](https://vercel.com) and the project is on the dashboard. Or
from this repo, `vercel ls` prints the recent deployments without opening a browser.

## 3. How code gets live here (and why `git push` does nothing)

Normally Vercel watches your GitHub repo and deploys every push. **We turned that
off.** In `vercel.json`:

```json
{ "git": { "deploymentEnabled": false } }
```

The reason: the Live page is built from ESPN data captured on Maya's Mac that
isn't committed. A git-triggered deploy would build from the repo alone and
publish a site with that data missing. Turning it off means a merge can never
silently wipe the Live page.

So the only thing that changes the site is **`scripts/deploy.sh`**, which builds
locally and uploads the finished folder (`vercel deploy --prebuilt`). Vercel does
no building of its own for this project.

Two things run that script:

1. **This Mac** — the `fantasy-live-update` task each morning, plus any time you
   run `scripts/deploy.sh` by hand.
2. **GitHub Actions** — the `live-update` workflow, hourly during games. It checks
   out `main`, so it can only deploy what has been merged.

Worth saying plainly, because it surprises everyone:

> Committed is not the same as live, and live is not the same as committed.

Work can sit merged on `main` and not be on the site (nobody has deployed since).
Work can be on the site and not committed anywhere (deployed from this Mac off an
unmerged branch). Neither is broken — it's just two separate tracks.

## 4. The five screens worth knowing

Open the project and you'll see a row of tabs. These are the ones that matter:

- **Deployments** — every deploy, newest first, with who made it and whether it
  worked. Click one to see its build log, or to promote or roll back to it. This is
  the first place to look when something seems stale or broken.
- **Logs** (and **Observability**) — what the `/api/live` function actually did on
  real requests: status codes, errors, how long it took. The only way to see why
  the Live page isn't refreshing.
- **Settings → Environment Variables** — where the ESPN cookies go. See §5.
- **Analytics** — visitor and page-view counts, once enabled. See §5.
- **Settings → General** — the project name, and the delete button. Rarely needed.

Everything else in that navigation (Storage, Firewall, Flags, AI, Integrations,
Speed Insights) is for things this project doesn't use. You can ignore all of it.

## 5. The two things currently pending

### a. Turn on Web Analytics

The page already carries the analytics tag — `site/build.py` adds it to the league
page. But the endpoint it calls doesn't exist until analytics is switched on for
the project, so right now the tag does nothing.

Two halves, both needed:

1. Enable it on the project — either **Analytics → Enable** in the dashboard, or:
   ```bash
   vercel project web-analytics
   ```
2. Deploy, so the page carrying the tag is the page that's live:
   ```bash
   scripts/deploy.sh
   ```

Then check it took:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://fantasy-recap-eight.vercel.app/_vercel/insights/script.js
```

`200` means it's on. `404` means analytics is still off — that URL is served by
Vercel, not by our build, so a 404 there is a settings problem, never a code one.

Numbers appear a minute or so after the first real visit. Note that the tabs are
hash links (`#live`, `#recaps`), and Vercel counts the path, not the hash — so
every visit records as `/`. You get how many people looked, not which tab.

### b. Add the ESPN cookies as environment variables

The `/api/live` function reads `ESPN_S2` and `ESPN_SWID` (see
`scripts/espn_fetch.py`) to fetch the current week from ESPN. The project has no
environment variables at all right now, so the function answers 503 and the page
falls back to its baked-in data.

Add them as **Production** variables — dashboard via
**Settings → Environment Variables → Add**, or:

```bash
vercel env add ESPN_S2 production --sensitive
```

It prompts for the value; `--sensitive` keeps it hidden in the dashboard
afterwards. Repeat for `ESPN_SWID`. Then **deploy again** — a deployment gets the
variables as they were when it was created, so an existing deployment won't pick
up a new one:

```bash
scripts/deploy.sh
```

Check with `vercel env ls`, which lists the names (never the values).

These are your credentials. Don't paste them into a chat, a commit, or this file.

## 6. Why the ESPN cookies live in two places

This is the most confusing part of the setup, and it isn't a mistake:

| Where | Who reads it | What for |
|---|---|---|
| **GitHub Actions secrets** (repo → Settings → Secrets and variables → Actions) | `scripts/capture_node.mjs` in the `live-update` workflow | Capturing the week in CI, before deploying |
| **Vercel environment variables** (project → Settings) | `api/live.py` on the live site | Answering `/api/live` when someone opens the page |

Same two values, two completely separate systems. Neither can see the other's
copy. **When the ESPN cookies expire, both need updating** — otherwise you fix one
symptom and the other keeps failing.

Symptoms, so you can tell which is which:

- A GitHub Actions failure email saying **"ESPN 401"** → the *GitHub* copy expired.
- The Live page stuck on old numbers, `/api/live` returning **503** → the *Vercel*
  copy expired or was never set.

GitHub Actions also needs `VERCEL_TOKEN` (so it can deploy) and
`DASHBOARD_SECRET` (so the private dashboard links it builds match the ones you
handed out). Both are listed in the header comment of
`.github/workflows/live-update.yml`.

## 7. Things that will bite you

- **Changing an environment variable doesn't change the live site.** It applies to
  the *next* deployment. Always redeploy after.
- **A 404 on anything starting `/_vercel/`** is a Vercel feature that isn't enabled,
  not a bug in our code.
- **`scripts/deploy.sh --preview` leaves out the private dashboards** on purpose —
  those tokens should exist at one URL, not two. Don't use a preview URL to check
  whether dashboards work.
- **Deployment URLs are permanent.** That long `fantasy-recap-xxxxx-...` URL keeps
  working after you've moved on. Before sharing one, check what the project's
  Deployment Protection setting is, so you know whether it's open to anyone with
  the link.
- **Rolling back is safe.** Deployments → pick a good one → promote. The pointer
  moves; nothing is rebuilt or lost.

## 8. Cheat sheet

```bash
vercel whoami                    # which account the CLI is using
vercel ls                        # recent deployments, newest first
scripts/deploy.sh                # build locally + publish to the live site
scripts/deploy.sh --preview      # throwaway URL for reviewing a draft
vercel env ls                    # variable names on the project (never values)
vercel env add NAME production   # add one, prompts for the value
vercel project web-analytics     # turn on Web Analytics
vercel logs <deployment-url>     # runtime output from a deployment
```

One-time setup on a new Mac: `vercel login`, then `vercel link` to connect this
folder to the project.
