# fp_news / waiver card calibration

Shipped in the 2026-10-20 run (PR #171) after three voice-check rounds. Read these
before writing `fp_news`, `fp_back`, or `waiver` cards — they're what "advice first,
one line of personality" actually looks like when it lands, and what it looks like
when it almost lands but doesn't.

Every card below kept its FantasyPros attribution (`"FantasyPros has..."`, `"per
FantasyPros' ownership numbers"`, etc.) even in its funniest form. That attribution
is not decoration — it's the hard rule in Step 5 ("every card whose text uses a
FantasyPros number or claim must say so explicitly"), and it's the single easiest
thing to lose when you're reaching for a sharper line. Check for it last, every time.

## Lands: one real joke, built from a checkable fact

> **Kyle Monangai is now listed questionable**
> FantasyPros has Kyle Monangai questionable with a thumb injury, the most
> bench-running-back injury a bench running back has ever had. He's on your bench,
> so nothing changes, but somewhere a trainer wrote 'thumb' on a clipboard with a
> completely straight face.

Why it works: the joke ("the most bench-running-back injury...") is a real,
checkable irony — a minor injury to an already-irrelevant player — not an invented
feeling. The clipboard image is the one coda, not stacked on top of anything else.

> **A.J. Brown is listed questionable**
> FantasyPros has A.J. Brown questionable with an ankle injury after a limited
> practice, the fantasy equivalent of a 'fine, I'm fine' text. Drake London and
> Garrett Wilson are healthy insurance if he sits. Check back before lineups lock
> and try not to doomscroll the injury report.

Why it works: the "fine, I'm fine" text is an accurate pop-culture-grade analogy for
a limited-practice questionable tag, and the doomscroll aside is a single
fourth-wall wink at the reader, not a second joke stacked on the first.

## Flat: zero personality (the most common miss)

The first voice-check round wrote every fp_news card dead straight — fact, advice,
stop. That's not "safe," it's under-dialed for this surface. A Coach card without
*any* personality line fails the same way a recap blurb with no joke does:

> ~~FantasyPros has Alec Pierce on injured reserve. He's on your bench, so your
> lineup doesn't change.~~

Fixed version kept every fact and added exactly one turn:

> FantasyPros has Alec Pierce on injured reserve, which barely registers in a
> receiver room this deep. You have more wideouts than attention span. Lineup's fine.

## Flat: the repeated-template trap

Round 2 fixed the "zero personality" problem by reaching for the same shape on
three different out/questionable cards in the same batch — list the healthy
backups, then a reassurance clause:

> ~~...Chris Olave, Parker Washington, Brian Thomas Jr. and Deebo Samuel Sr. are
> all healthy options on your roster, **so an empty receiver spot is not your
> excuse this week**.~~
>
> ~~...DeVonta Smith, Tetairoa McMillan and Mike Evans are all healthy, **so a
> three-deep receiver room should make this an easy fix**.~~
>
> ~~...Drake London and Garrett Wilson are both healthy, **so one questionable
> receiver shouldn't cost you anything**.~~

Each one individually reads fine. Across a batch of a dozen cards, three identical
sentence shapes read as a fill-in-the-blank template — exactly what Step 5b's
"so managers never read a fill-in-the-blank template" line is warning against, and
it applies just as much to Step 5's fp_news cards. If you notice you've written
"[healthy names], so [reassurance clause]" more than once in the same run, change
the shape of at least one of them — personify something, use a distinct comparison,
lean on a different joke technique from CLAUDE.md's list.

## Over-dialed: two jokes stacked on one card

Round 3, reaching for "more funny," overcorrected on two cards:

> ~~Nobody in the league owns the Minnesota Vikings, FantasyPros' top-ranked
> defense the rest of the way, so you can have the best unit in the building for
> the price of a waiver claim. Grab them before somebody else notices **the fire
> sale**.~~ *(plus an earlier "empty as a Monday-morning fridge" simile, cut in the
> round before this one — three images total across one short card)*

Fixed to one joke:

> Your DST spot is empty. Nobody in the league owns the Minnesota Vikings,
> FantasyPros' number one defense the rest of the way, so you can have the best
> unit in the building for the price of a waiver claim. Grab them before somebody
> else notices the fire sale.

Pick the best image and cut the rest — the same "pick the best one and cut the
rest" rule CLAUDE.md states for recap blurbs applies here at the same strictness.

## The serious exception is narrow, not a blanket "no jokes on injuries" rule

Only a genuinely lineup-altering injury — a starter, not bench depth — gets the
strict one-sentence, zero-joke treatment:

> **Jalen Hurts is now on IR** *(serious)*
> FantasyPros has Jalen Hurts on injured reserve with a calf injury, so Brock
> Purdy steps in at QB from your bench while we hope for a quick recovery.

Every other injury card in this same run — including several IR designations —
got the normal one-line-of-personality treatment, because the player was bench
depth with no lineup consequence. Don't apply the serious, joke-free voice to
every injury by default; that's under-dialed for a card that doesn't actually
matter to the team's starting lineup, the same way a flat recap blurb is under-dialed
for a routine matchup. Decide serious-or-not the way CLAUDE.md's dial table does:
does this change what she starts this week, or is it a bench-depth footnote?
