# Fonts — empty on purpose

`docs/design/tokens.md` names Space Grotesk for the interface and IBM Plex
Mono for receipts, and says both are **loaded from the system only — no CDN,
no webfont fetch, no network call of any kind**. This directory exists because
task T1 asked for `@font-face` from local files here if the licences allow it,
and to say so if they do not.

## The licences do allow it

| family | licence | bundling |
|---|---|---|
| Space Grotesk | SIL Open Font License 1.1 | permitted, including in a web page, with the licence text alongside |
| IBM Plex Mono | SIL Open Font License 1.1 | same |

Neither licence is the blocker.

## Why nothing is bundled anyway

The font files are not in this repository, and fetching them would mean a
network call at build time from an agent that is not authorised to make one.
So the page ships with no `@font-face` at all and falls through the stacks
`docs/design/tokens.css` already defines:

    --font-ui:   "Space Grotesk", "Segoe UI", system-ui, -apple-system, sans-serif
    --font-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace

A reader with either family installed gets it. Everyone else gets Segoe UI and
Cascadia Mono on Windows, the system UI font and `ui-monospace` elsewhere. The
layout was built and measured against the fallback, not against the intended
face, so nothing reflows or overflows when the fallback is what renders.

There is deliberately **no** `@font-face` rule pointing at files that are not
here: it would fail silently over http and log a failed request from
`file://`, and the page's claim is that it makes no requests it did not intend.

## To bundle them later

1. Put `SpaceGrotesk-Regular.woff2`, `SpaceGrotesk-SemiBold.woff2`,
   `IBMPlexMono-Regular.woff2` and the two `OFL.txt` licence files in this
   directory.
2. Add the `@font-face` blocks at the top of `../style.css`, each with
   `font-display: swap` and `src: url("fonts/<file>") format("woff2")`.
3. Re-check the page size: `python ../verify_teaser_data.py` prints the load
   size and fails if it passes 5 MB. Three woff2 faces are roughly 120 kB, and
   the `file://` bundle is already at 4.75 MB of the 5 MB budget, so the
   subsetted faces are the only version that fits.
