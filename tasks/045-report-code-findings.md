# Task 045 — What the interface found in the report code

## Setup
Branch `task-045` from `main`. Commit `task 045:` and push after every
commit. No pod. The work is in `oneground/report/` — `claims.py`,
`verdict.py` and `__init__.py` — and their tests. Nothing here measures a
corpus.

## Why

Task 041 built the read half of the interface: a page that shows, for every
figure in a report, the file and field it was read from and the value at that
field. Building it produced eight findings, and **five of them are not about
the interface.** Four are collected here.

They share one property, and it is the reason they are one task:

> **Each is a defect in what a claim says, not in how a claim is drawn.**

The interface refused all four. It renders a claim verbatim, so a renderer
that corrected a claim's sentence, rewrote its citation or collapsed fifteen
claims into one would make the screen and the receipt disagree — and a reader
comparing the two would be right to trust neither. An ugly token on a page is
a smaller fault than a page that quietly improves its source.

So the page displays them, and this is where they get fixed.

**The order matters and the first one is why.** Finding 1 is a check whose
name promised more than it delivered, and it is the reason the other three
survived review: a project with a claim invariant reasonably assumes its
claims have been checked. Fix that first, and the others become things the
suite can hold rather than things a reader has to notice.

---

## Do

### 1. The claim invariant checks that a cited field holds the cited value

**This leads, and the rest depend on it.**

Task 019's invariant makes every sentence in a report a `Claim` carrying the
rows it cites, so a reader can reconstruct the sentence from its evidence.
`claims.check()` verifies that the sentence follows from what it cites.

**It never verifies that the citation is true.** A `Cite` carries a `source`
path and a `value`, and nothing in the project compared the two until a UI was
asked to render them side by side. Two defects had survived the invariant, two
other real-report tests, a published fixture and the teaser:

| where | cited | the field named actually held |
|---|---|---|
| `verdict.py:606` (throttled qps) | `119.1` | `load.completed` = **35731** |
| `verdict.py:670` (budget) | a monthly figure | `costs["config"]` — never a key |

Both were fixed in 041 as one-line repairs with property tests. **The gap that
let them through was not.**

Required behaviour:

- `check()` gains a step that, for every cite carrying a `value`, resolves its
  `source` against the run's receipts and compares. A disagreement is a
  violation naming both numbers and the path.
- **Non-field sources are classified, not failed.** Four shapes in a real
  report are legitimately not a scalar field, and a check that fails them
  would be wrong three times to catch one:
  - `(rule)` — the conclusion follows from a rule, not a row;
  - `requirements:constraints` — an input the user wrote, not a receipt;
  - `options[*]` — a wildcard over every option;
  - a source naming a **container** whose cited value is one of its members
    (`p95_across_runs` cited by its `.min`; `qps_max` by its `.qps_max`).
  041's `oneground/lab/views/evidence.py` names eight kinds and
  `oneground/lab/citations.py` resolves them; that vocabulary is the one to
  reuse rather than invent a second.
- **A source naming a field that is not there is a violation**, distinct from
  the four above, and says which file and which field.

**One design decision this task must make and record.** The resolver exists in
`oneground/lab/citations.py`, and it is there because 041 was forbidden to
import `oneground.report` — the lab's guard lists it as measuring. The
dependency cannot simply be reversed: a shared resolver may not live in
`oneground/report`, or the lab can never use it. Two options, and the report
must say which was chosen and why:

  (a) move the path grammar and walker to a module both import, leaving
      `citations.py` as the lab's transport over it;
  (b) implement the check in `claims.py` and have the lab cite that, which
      requires the shared part to sit outside `oneground.report`.

Whichever is chosen, **there must be one path grammar.** 041 chose the
grammar `report.json` already cites with so that a view's declared `reads` and
a claim's `source` never need translating; a second grammar would reintroduce
exactly the place two things can disagree.

**Acceptance is a mutant.** Reintroduce `verdict.py:606`'s pairing — a source
naming `load.completed` while carrying `load.achieved_qps`'s value — and the
invariant must fail, naming both numbers. A check that passes on a healthy
tree and was never watched fail is not evidence (`docs/FAMILIES.md` §4.1).

---

### 2. A citation that cannot be reconstructed from what it names

Two `to_resolve` claims in the arXiv report cite
`verify_info.json:engine_facts.index_params`. `engine_facts` lives under
`engines[]`, one level below where the source points, and the claims carry no
`member`.

**The missing member is the symptom.** The claims' own text spans **both**
engines — *"pgvector has not been asked what index families it builds … qdrant
has not been asked …"* — so there is no single engine whose value the sentence
rests on.

This is why the obvious repair is wrong. Rewriting the source as
`verify_info.json:engines[].engine_facts.index_params` would make the entry
resolve while still not saying which engine's value the sentence rests on —
**a link that looks right and answers nothing**, which is worse than one that
says it cannot answer.

Required behaviour, and it is a choice between two shapes:

- **two claims, one per engine, each with `member` set** — the sentence
  becomes two sentences, each reconstructible; or
- **one claim citing both values** — the sentence stays one and carries two
  cites, each with its `member`.

Either satisfies step 1's new check. Neither is a rendering change. Say in the
report which was chosen and what it does to the claim count on the arXiv
report.

Until then the interface renders the entry as `unresolved` with its reason,
which is the correct rendering and should not change.

---

### 3. The report writes a machine token into its own prose

**Sixteen of the arXiv report's 37 claim sentences contain the literal string
`couldnt_check`** inside the sentence a reader is meant to read:

> `hash_sharded[…]: latency_p95 was not compared across engines because fewer
> than two engines produced a value -- qdrant (couldnt_check), pgvector
> (couldnt_check).`

and `oneground/report/__init__.py:715` writes *"so it is couldnt_check rather
than …"* directly into a claim.

This is task 035's caption rule one layer in: **a value that exists so a
machine can compare it has been printed where a sentence belongs.** The token
is a check, not English.

Required behaviour:

- A claim's `text` says what happened in words — *"could not be checked"*,
  *"was not compared"* — and never prints the outcome constant.
- The outcome constant stays in the machine field (`asserts_outcome`, a
  verdict's `outcome`, a constraint's `outcome`) where comparison needs it.
- Named sites to start from: `__init__.py:715`, and wherever the per-engine
  tuples `(couldnt_check)` are composed. Grep is the right tool; the count
  above is from one report and is not a ceiling.

**Not a rendering fix, and the interface deliberately did not make it one.**
`oneground/lab/static/ui.js` strips the token wherever *the page* composes a
line — a gap heading, a drawer note, a remedy — because the heading already
says it. It does not strip it from a claim, for the reason at the top of this
brief.

---

### 4. One fact, stated fifteen times, outweighs every verdict

Measured on the arXiv report:

| | claims | characters |
|---|---|---|
| all claims stating a verdict | 16 | **3,659** |
| one `no_engine_comparison` sentence, repeated | **15** | **3,959** |

Fifteen of the 21 claims that state no verdict are the same sentence —
*"&lt;config&gt;: &lt;constraint&gt; was not compared across engines because
fewer than two engines produced a value"* — differing only in the
configuration label and the constraint name. Each is true. Together they are
**one fact**: two engines were measured and only one produced a value.

The consequence is not cosmetic. On any surface that lists claims — the
report page, `report.html`, a printed report — one fact occupies more room
than every verdict in the report combined, so the thing a reader came for is
outnumbered by a restatement.

**The claim invariant already supports the shape that fixes it.** A `Claim`
carries `quantifier`, `holds_for` and `holds_rule`, and 019's step 5b derives
`holds_for` from the rows rather than believing it. A claim true once per
configuration and identical in substance is one claim **universally quantified
over those configurations**: one sentence, fifteen members in `holds_for`.

Required behaviour:

- Claims identical in substance and differing only in their subject are
  emitted as one quantified claim.
- The quantified claim's `holds_for` lists every member, and step 5b still
  derives it from the rows — the collapse must not become a claim that
  supplies its own truth condition.
- Every member keeps its own citation, so step 1's check still resolves each
  one.
- **The count that must not change is the set of facts**, not the number of
  claims. Say in the report what the arXiv report's claim count becomes and
  confirm no fact was dropped.

---

## What this may not do

- **Fix any of these in a renderer.** Every one of the four is a defect in
  what a claim says. A page that corrected a sentence, rewrote a citation or
  collapsed fifteen claims into one would make the screen and the receipt
  disagree, and both would then be unreliable.
- **Build a check that cannot fail.** Every new rule gets a mutant that runs
  the rule's own code — not a restatement of it — and the unmutated tree must
  pass the same check on the same input. `docs/FAMILIES.md` §4.1, warnings 3
  and 5.
- **Downgrade a held measurement to couldn't-check** because a stronger claim
  is unproven. `docs/FAMILIES.md` §4.1, warning 4.
- **Invent a second path grammar.** One, shared, in the language
  `report.json` already cites with.
- **Change a published value.** `fixtures/arxiv-150k/report/report.json` was
  rebuilt in 041 and its digests are recorded there. If a fix here moves it,
  that is a fixture rebuild with its own digests and its own ruling — stop and
  report before changing one.

## Acceptance

- The invariant fails on a cite whose source names a field holding a different
  value, naming both numbers and the path, proved by a mutant.
- The four non-field source shapes are classified rather than failed, each
  named, with a test per shape.
- One path grammar, shared, with the report saying where it lives and why.
- The spanning citation is two claims with `member` set, or one claim citing
  both values, and resolves under the new check.
- No claim's `text` contains an outcome constant, asserted over a real report.
- Repeated-in-substance claims are emitted as one quantified claim whose
  `holds_for` is derived from the rows, with the arXiv claim count before and
  after and a statement that no fact was dropped.
- Full suite green. `site/teaser/` byte-unchanged.

## Do not

- Reach into `site/teaser/` — it is core's, and 041's Finding 2 (the teaser's
  unverified provenance) is **not** part of this task.
- Rename or repurpose `calibrate/history.py:comparable()`.
- Treat the counts in this brief as ceilings. They are from one report on one
  machine; the checks are what generalise.

---

## One thing worth knowing when this is scheduled

**041's side-by-side view already works, and is waiting on receipts rather
than on code.**

`docs/LIBRARY.md` §2.2's comparability verdict is implemented at
`oneground/comparability.py`, the interface draws it, and the no-alignment
rule is enforced structurally — two runs are joined into shared rows only when
the verdict permits it. All of that is built and tested.

It answers `couldnt_check` for every pair of runs on this machine, including
two byte-identical copies of one run, because no artifact records a usable
code identity or any machine identity. **That is what task 043 fixes.**

So the sequencing is worth knowing: **when 043 lands, a permanent
couldn't-check becomes a working feature with no change to the interface at
all.** Nothing in 041 needs revisiting, nothing in this task touches it, and
the first run produced after 043 with a clean tree and a recorded machine
digest will make the side-by-side answer `comparable` on its own.
