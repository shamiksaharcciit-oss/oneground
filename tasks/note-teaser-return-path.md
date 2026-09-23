# For core, with the request for `app.js`

## The gap, in one paragraph

Our arrangement for `site/teaser/` is *our file, our digests, their re-copy*:
we produce the bytes, `data/MANIFEST.sha256` records them, and
`check_hosted.py` confirms the host is serving what this repository produced —
which works precisely because the flow runs one way. **A byte-for-byte copy
with a one-way flow is not a copy, it is a fork with a naming convention**,
and it stays indistinguishable from a copy for exactly as long as only one
side writes. Change 1(a) is the first time the other side wrote: core edited
`app.js`, deployed it, and the change now exists only there, so
`check_hosted.py` reads *contradicted* on a file whose difference we approved
— the tool cannot tell an accepted change from a stale CDN or a bad deploy,
because from its side they are the same bytes not matching. The cost is not
the confusion; it is that **our repository is now behind the page while every
mechanism that depends on it assumes the reverse**. Task 044e's export
rewrites `values.json`, rebuilds `data/MANIFEST.sha256` and restamps
`app.js`'s cache-bust digests, so running it against our tree today would
publish a manifest describing a page that is not the page, and it would do so
silently. The fix is not this one pull. It is a stated return path, because a
one-off pull leaves the same gap open for the next change either side makes.

## What we are asking for

**Immediately:** your current `app.js` (host `e65aee1190418bdf…`, 49,486
bytes) as a patch or a file, so our tree matches the page and 044e's re-export
can run. Nothing else is out of step — 8 of 9 files verify byte-for-byte.

**Standing, and this is the part worth agreeing:**

> **When you change a file we own, run `check_hosted.py` as the last step of
> the deploy, and treat a contradiction as the signal to send the file back.**

That needs no new process and no new tool. It is the tool both sides already
have, pointed the other way at the one moment it is cheapest to act on:

- **Today** we run it and find drift late, from the far side, with no file in
  hand and no way to tell an approved change from a bad deploy.
- **Under this** you run it at the moment you create the drift, with the
  changed file already in front of you, and the contradiction names exactly
  which file to send.

It also makes the check mean something it does not mean now. A green
`check_hosted.py` currently says *the host has not drifted from us*; after
this it says *neither side has drifted from the other*, which is what everyone
has been assuming it said.

**Two smaller things that would help, neither essential:**

1. If a change is coming that you know we will want (a caption, a panel, any
   text we drafted), sending it before the deploy rather than after costs you
   nothing and means our tree is never behind a live page.
2. If it is easier for you to edit and deploy first, that is fine — the
   standing ask is only that the deploy tells you to send it. We would rather
   have a fast path with a return leg than a slow path with a review gate.

## What we are not asking for

Not ownership of the page, not a review step before you ship, and not that you
stop editing files we produce — change 1(a) is better than what we sent and it
should have gone in. Only that the bytes come back, and that the thing which
notices when they have not is run by whoever is in a position to fix it.
