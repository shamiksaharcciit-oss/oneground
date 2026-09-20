# Report: 039b-both-scales-rule

## Repo state expected vs found

Expected, and found:

- `docs/MODELS.md` with a ceiling-rule section (line 303) stating the
  routing/index decomposition. Found, and it is the right home: the ceiling
  rule and the both-scales rule are the same defect one level apart — a
  number that cannot say what it licenses until something else is stated
  beside it.
- `oneground/report/claims.py`, the 019 claim invariant, checking that a
  quoted number is cited. Found, and it does check that (`check()` step 6).
- The 039 rulings from the previous task already on `main` at `c40e5ea`.
  Found.

One thing I expected to be a documentation question and found to be a code
question: **the rule has a live instance in shipped code**, not only in prose.
`oneground/proposals/verdict.py:97` computes a proposal card's `delta` as a
difference and judges it against a difference threshold (`by_at_least`), and
the card renders "X rises by `delta`". That is a gap quoted on one scale,
with no record that a scale was chosen — the same shape as task 039's own
prediction. It is not a wrong number today; it is an unguarded one.

## What was done

1. The both-scales rule written into the ceiling-rule section of
   `docs/MODELS.md` as a stated rule, with task 039 as its evidence, the
   sentence each scale supports named, and its enforcement status stated
   rather than implied.
2. The enforcement question investigated by measurement rather than by
   reading: four mutants of a proposal-card metric claim run through
   `claims.check`.

No gate, threshold, tolerance or seed was changed. No code was changed —
see "Observed, not done" for why building was the wrong call and not a
shortfall.

## Measurements

### Can `claims.check` see a gap? No, and it is not close.

`tasks/scratch/039b-can-the-invariant-see-a-gap.py` builds the exact claim
shape `proposals/card.py:_metric_claim` produces, with the two cited values
held fixed at `before=0.8500` and `after=0.8623`, and varies only the derived
`delta` the prose prints:

| # | what the prose says | truthful? | `claims.check()` |
|---|---|---|---|
| A | `rises by 0.0123, from 0.8500 to 0.8623` | yes | **no problems** |
| B | `rises by 0.1230, from 0.8500 to 0.8623` | inflated 10× | **no problems** |
| C | `rises by -0.0123, from 0.8500 to 0.8623` | sign reversed | **no problems** |
| D | `rises by 1.0145, from 0.8500 to 0.8623` | a **ratio**, printed where a difference is claimed | **no problems** |

Mutant D is the rule's exact defect, executed: the scale silently changed, the
prose still says "rises by", and the oracle is silent. All four pass.

### Why they pass

Two independent structural reasons, both read from the module and confirmed by
the run above.

**1. A `Cite` cannot hold a derived quantity.** Its fields are
`member, value, source, outcome, constraint, reason`, and `source` is a path
into a run's own artifacts — `simulate.json:rows[cfg].recall_at_10` — which
`check()` step 5 goes and reads. **A difference has no such path**: no field
in any artifact holds `a − b`. So a gap cannot be cited, and step 6 ("a value
quoted in the prose must be one the claim cites") has nothing to match it
against. `delta` lives in `Claim.extra`, which nothing checks.

**2. The invariant is single-run.** `RowIndex` is
`{subject: {member: {constraint: fact}}}`, built by `rows_from_options()` from
one report's options. There is **no run dimension**, so the two sides of a
between-corpora gap cannot both be present to be compared. A 039-shaped gap
spans `runs/039-nprobe-arxiv-150k` and `runs/039-nprobe-stackexchange-150k` —
two artifact trees the index has no way to hold at once.

### And the 039 violations are where the invariant does not look

`raise_on_violation` is called in exactly two places in the tree:

- `oneground/report/__init__.py:1222` — the report
- `oneground/proposals/propose.py:607` — the proposal card

Both run over one run's rows. The gap task 039 actually mis-stated was in
`docs/MODELS.md` and in a task report — hand-written prose, rendered from no
`Claim`, which the invariant never sees and was never built to see.

## Verification

| check | result |
|---|---|
| The rule is stated in `docs/MODELS.md`'s ceiling-rule section with 039 as evidence | **PASS** — `### Both scales, or neither (task 039)` |
| Each scale is named with the sentence it supports | **PASS** — both in the rule's table |
| Every number in the new section recomputed from the runs | **PASS** — 0.0982, 0.0435, 1.686, 5.833 via `tasks/scratch/039-doc-numbers.py` |
| Can the claim invariant enforce the rule as it stands | **NO** — measured above, four mutants pass |
| Suite | **PASS** — 1265 passed, 2 skipped |

**Couldn't check:** whether any *shipped* card has ever printed a wrong delta.
`verdict.py:97` computes it as `round((b - a), DECIMALS)` with the direction
applied, which is correct, and no card in the tree is wrong. What is
unverifiable is the counterfactual — nothing would have caught it if it were,
which is the finding rather than a gap in this check.

## The answer to the question asked: what structure enforcement needs

Three pieces. The first carries the others and has independent value; the
third should not be built for this rule alone.

**(a) A derived cite — the one that matters.** A cite whose value is *computed
from other cites by a named operation*, with the operation recorded and
re-executed by `check()`:

```
Derived(op="difference", of=(cite_after, cite_before), value=0.0123)
Derived(op="ratio",      of=(cite_after, cite_before), value=1.0145)
```

`check()` gains one rule — recompute `op` over `of` and compare to `value` —
and mutants B, C and D above all fail. This is the same move the module
already made once: step 5b stopped believing `holds_for` and recomputed it
from the rows, because "a claim that supplies its own truth condition is not
being checked". A derived cite is that, for arithmetic.

**(b) The scale rule, which (a) makes almost free.** Once a gap is a derived
cite, **`op` is the scale**. The rule becomes checkable in the shape `check()`
already has: a claim carrying a derived cite over a pair must carry at least
two, with different `op`, over the *same* pair — and the existing step 6
already forces each printed number to be one the claim cites, so naming both
in the prose follows without new machinery.

**(c) A run dimension on `RowIndex`, and not for this rule.** Cross-run gaps
need the two runs' rows present at once, and a row would need to carry which
corpus, which ground truth and which query subset it came from. That is
**already named as missing twice** — `docs/BRIDGE.md` §4 ("a row's provenance
is not one of the invariant's inputs", which is why its table rule had to be a
structural refusal) and `docs/LIBRARY.md` §2.2's three-valued comparability
verdict, which is written and implemented nowhere. This rule is the **third**
position resting on that same absent structure. Whichever is built first
should build it, and the other two cite it — which is the rule `BRIDGE.md`
§4 already states.

### Why I did not build a presence-check instead

A both-scales check could be written today against `Claim.extra`: require a
`proposal_metric` claim to carry a `ratio` key beside its `delta`, and fail if
it does not. **That would assert presence, not correspondence** — it would
confirm a second number is there while checking neither number is right, and
mutant D would still pass with a ratio beside it.

That is precisely the defect `claims.py` was built to refuse. Its own opening
says the tests before it "asserted **presence** — the names appear, the page
renders — rather than **correspondence**", and calls that structural rather
than careless. Shipping a presence-check under this rule's name would put the
rule's badge on the failure mode the module exists to prevent, and would make
the rule look enforced while leaving it unenforced. Worse than not building
it, because the next person would stop looking.

So the rule is written, its status is stated in the document, and the
structure is named. It is not silently unenforced, which was the concern that
scoped this task.

## Observed, not done

- **The proposal card quotes an unchecked derived number today.**
  `verdict.py:97`'s `delta` is correct, and nothing verifies that it is. This
  is the smallest, highest-value place to build (a), and it is worth doing on
  its own merits before any of the scale machinery — the card is the one
  artifact in the project that states a difference and judges against a
  difference threshold.
- **The proposal card's threshold is scale-blind in the same way 039's
  prediction was.** `by_at_least` is a difference, `_band` compares a
  difference, and nothing in a policy file records that a scale was chosen or
  offers another. A policy author is in exactly the position I was in writing
  the 039 brief. Not fixed — it is a change to a shipped interface and no
  brief asks for it.
- **The rule cannot reach hand-written documents at all.** `docs/MODELS.md`'s
  gap is prose no `Claim` renders. Enforcing there means either generating
  those paragraphs from claims or building a prose checker that would have to
  guess what is a gap. Neither is proposed here; the rule stays written for
  documents and becomes executable for claims, and the document now says so.
- `docs/LIBRARY.md` §2.2 and `docs/BRIDGE.md` §4 should eventually name this
  rule as the third dependent on the provenance structure. Not done — editing
  either needs a brief that names it.

## Repo now contains

New:

- `tasks/039b-both-scales-rule.report.md` — this file.
- `tasks/scratch/039b-can-the-invariant-see-a-gap.py` — the four mutants
  (gitignored, local).

Changed:

- `docs/MODELS.md` — the ceiling-rule section gains
  `### Both scales, or neither (task 039)`: the rule, its measured evidence,
  the sentence each scale supports, why it is a rule rather than a habit, and
  its enforcement status.

No source file was changed.

## Blocked on developer

Nothing.

One decision is now ready to be made rather than raised: **whether to build
the derived cite (a)**. It is bounded, it has a live beneficiary that is not
this rule (the proposal card's unchecked `delta`), and it is the piece that
makes the both-scales rule executable rather than written. It needs a brief;
it is not in this one.
