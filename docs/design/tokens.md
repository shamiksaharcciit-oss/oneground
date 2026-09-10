# Design tokens

One palette, used by every rendered artifact oneground produces. Defined here
so the report, the ground view and anything later agree without copying hex
codes between files.

The ground view (`docs/img/ground_*.png`) was drawn on this slate before these
tokens were written down; the values below are taken from it so a report and
the hero image sit on the same background rather than nearly the same one.

## Surfaces and ink

| token | hex | use |
|---|---|---|
| `--slate` | `#1B2432` | page background; the ground view's own base |
| `--panel` | `#243040` | cards, table bodies, anything lifted off the page |
| `--ink` | `#E7EAEF` | primary text |
| `--muted` | `#8B96A5` | secondary text, labels, source paths |
| `--ochre` | `#C99A3B` | the project accent; used sparingly, never for an outcome |

## Outcome colours

Three outcomes, three colours, and **no fourth**. These carry meaning, so
nothing else in the interface may use them.

| token | hex | outcome |
|---|---|---|
| `--teal` | `#4FC1AD` | `meets` |
| `--coral` | `#E36C5E` | `fails` |
| `--amber` | `#D9A441` | `couldnt_check` |

Amber is deliberately not a muted grey. couldn't-check is a real result with
its own weight, not an absence, and greying it out would invite a reader to
skip it — which is the exact failure mode the three-outcome rule exists to
prevent.

`--ochre` and `--amber` are close on purpose but never adjacent: the accent
never appears inside a verdict cell.

## Type

| role | family | notes |
|---|---|---|
| interface | Space Grotesk | headings, tables, prose |
| receipts | IBM Plex Mono | digests, file paths, field references, config labels |

Both are loaded **from the system only** — no CDN, no webfont fetch, no
network call of any kind from a rendered report. A report has to open on a
laptop with no internet, so each family falls back through a generic stack and
the layout is designed to survive the fallback rather than depend on the face.

Monospace means "this is a receipt you can check", so it is used for exactly
those things and not for emphasis.

## Rules

- The recommendation is the only emphasised element on the page. Everything
  else is quiet and typographic.
- No charts in the report (task 010). A number with its source beats a
  picture of a number.
- Every verdict cell shows its source field, so the colour is never the only
  thing carrying the claim.
