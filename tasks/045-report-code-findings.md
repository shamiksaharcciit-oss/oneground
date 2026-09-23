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
the interface.** Five are collected here — four from 041, and one the
proposals stream found while building 044.

They share one property, and it is the reason they are one task:

> **Each is a defect in what a claim says, not in how a claim is drawn.**

The interface refused all five. It renders a claim verbatim, so a renderer
that corrected a claim's sentence, rewrote its citation, supplied a missing
remedy or collapsed fifteen claims into one would make the screen and the
receipt disagree — and a reader comparing the two would be right to trust
neither. An ugly token on a page is a smaller fault than a page that quietly
improves its source.

So the page displays them, and this is where they get fixed. Four were found
by building the page; the fifth was found by a test the page's own rules
required, which is the same thing one step further on.

**The order matters and the first one is why.** Finding 1 is a check whose
name promised more than it delivered, and it is the reason the others survived
review: a project with a claim invariant reasonably assumes its claims have
been checked. Fix that first, and the rest become things the suite can hold
rather than things a reader has to notice.

**Two of the five are the same two lines.** Findings 2 and 5 both land on
`verdict.py:364` and `:524` — the same pair of couldn't-check verdicts carry
an unreconstructable citation *and* no remedy. Do them together.

**And one of them is being scheduled by its own recurrence.** The failing
remedy test has now been recorded in two separate merge reports — task 044's
and task 036's — each by a stream that did not cause it, did not own it, and
merged onto it knowingly rather than hold a clean change hostage. That is a
defect arriving on the schedule by repetition rather than because anyone
decided it was next, and each recurrence costs a paragraph of someone else's
report explaining why it is not theirs.

It is also the argument for **finding 5's full scope rather than its visible
one.** Two streams have now met the same two claims, because those two are
the ones a local workdir happens to exercise. Fixing those two would stop the
paragraphs and leave twenty-seven couldn't-check verdicts unrouted, waiting
for whichever workdir exercises them next to start the cycle again.

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

### 5. A couldn't-check whose remedy restates the obstacle

**The sharpest of the five**, because the remedy is the only part of a
couldn't-check a reader can act on. A verdict that says *I could not check
this* and stops has told them the one thing they already suspected.

Found by the proposals stream in task 044, which did not cause it and does not
own it: `test_every_couldnt_check_claim_carries_a_remedy` fails on the arXiv
workdir, claims `[33, 34]`, both reading:

> *"To decide latency_p95: this configuration was not the one verified — the
> verify run built hnsw in a single namespace, which is not a hash_sharded
> deployment."*

**Read that sentence twice.** It begins with the grammar of a remedy — *To
decide X:* — and never becomes one. What follows the colon is the obstacle.
A reader skimming, or a reviewer checking that remedies exist, sees a sentence
shaped like an instruction; only someone who reads to the end finds there is
nothing to do in it. The action it is missing is: *verify this configuration,
built as `hash_sharded`, on a real engine.*

#### The routing exists. Check it before writing any prose.

**Do this first, and do not write a sentence until it is answered.** This is
the addition's lead and it is the part of this finding most worth keeping:
`report/claims.py:how_to_resolve` **already routes a remedy**, for two kinds:

```python
remedy = getattr(verdict, "remedy", "")
kind = getattr(verdict, "couldnt_check_kind", None)
if remedy and kind in ("not_verifiable_here", "coverage_unresolved"):
    return f"To decide {name}: {remedy}."
```

So a hand-written sentence for these two claims **would paper over a routing
fault with better prose**: the claim would read well, the test would pass, and
every other verdict taking the same path would keep arriving unrouted. Fix the
routing and the sentence follows. Write the sentence and the routing stays
broken and invisible.

#### What the routing actually does, measured

`verdict.py` post-processes couldn't-check verdicts in one loop, and only for
`ENGINE_CONSTRAINTS = ("latency_p95", "qps")`:

| branch | `couldnt_check_kind` | `remedy` | routed by `how_to_resolve`? |
|---|---|---|---|
| a decision exists | `not_verifiable_here` | composed from it | **yes** |
| coverage unknown | `coverage_unresolved` | composed from it | **yes** |
| otherwise | `not_verified` | **`""`**, explicitly | **no** |

Three facts follow, and the third is the defect:

1. **The `else` branch sets `remedy = ""` deliberately.** `not_verified` is a
   kind with no remedy attached, though task 034's own docstring says what its
   remedy is: *"a run that could have happened and did not — remedy: run it."*
2. **`how_to_resolve` does not route `not_verified`**, so even a populated
   remedy would not reach the claim through that branch.
3. **`how_to_resolve` falls through to
   `return "To decide %s: %s." % (name, reason)`** — the reason, wearing a
   remedy's opening words. That is the sentence above, and it is produced for
   every couldn't-check the earlier branches do not match.

The two claims are the visible case. **Every couldn't-check on a constraint
other than `latency_p95` or `qps` never enters the routing loop at all** —
`recall_at_k`, `storage_amplification`, `memory_budget` and the rest reach a
reader with `couldnt_check_kind: None`, `remedy: ""`, and a fall-through
sentence that restates their obstacle.

#### Required behaviour

- **Fix the routing, then the prose.** In order, and the report says which
  change did what.
- `not_verified` carries a remedy. Task 034 already wrote it: *run it.* For
  the two claims that means *verify this configuration, built as the family
  the row names, on a real engine.*
- `how_to_resolve` routes every kind that carries a remedy, not two of three.
- **The fall-through stops dressing a reason as a remedy.** If no remedy is
  known, the claim says so in words a reader can act on — *"nothing here can
  settle this; what would is …"* — or the absence is visible rather than
  disguised by an opening clause. A sentence that begins *To decide X* and
  does not say how to decide X is worse than a blank, because a blank is
  obviously missing.

  **This is finding 5's other half, one layer along: right shape, no
  content.** The first half is an action sitting in `reason` where nothing
  looking for a remedy will find it — right words, wrong field, and worse than
  absent because it reads as done. The second is a sentence carrying a
  remedy's opening words and an obstacle's content — right shape, wrong
  content, and worse than absent for the same reason. Both defeat a reader and
  a reviewer in the same way: the thing has the appearance of the thing. A
  check that asks *"is there a remedy?"* answers yes to both.

- **Routing covers every constraint, not two of them.** *The two claims anyone
  looked at were inside the routed set and still unrouted, so everything
  outside it was never in scope at all* — which is the size of the problem in
  one sentence.

  The loop runs only over `ENGINE_CONSTRAINTS = ("latency_p95", "qps")`, so a
  couldn't-check on `recall_at_k`, `storage_amplification`, `memory_budget` or
  `monthly_budget` **never enters routing at all**: it arrives with
  `couldnt_check_kind: None`, `remedy: ""`, and the fall-through sentence.
  This is the larger half of the finding.

  Either every constraint's couldn't-check is routed, or the ones that are not
  carry a recorded reason why routing does not apply to them. "It was only
  ever written for engine constraints" is a fact about the code, not a reason
  a reader can act on.

#### Findings 2 and 5 are the same two lines

`verdict.py:364` and `:524` produce both the unactionable reason *and* the
citation Finding 2 describes — they carry
`source="verify_info.json:engine_facts.index_params"`, a per-engine field
named by a verdict spanning every engine. One edit closes both, and doing them
apart touches the same two verdicts twice.

#### Why it went unnoticed, which is a finding about the check

`test_every_couldnt_check_claim_carries_a_remedy` reads a local, untracked
workdir. In CI there is none, so it **skips**, and the suite is green. It is
red only on a machine that happens to hold that workdir.

> **A check that passes everywhere it runs, and only runs where nobody looks,
> reported nothing for as long as it existed.**

The general form is now `docs/FAMILIES.md` §4.1 warning 6, alongside the two
other ways to produce a green result without evidence.

**So this task also owes a tracked workdir that exercises the
not-verifiable-here path**, so the case fails for everyone or for no one.
`oneground/lab/testdata/041-pre-fix-report.json` is the precedent: tracked,
digest pinned in the test, and the helper that reads it fails rather than
skips when it is absent.

#### Established, not assumed

- **Task 044 did not cause it.** The failure reproduces identically with 044's
  changes stashed, and 044 writes into no artifact a claim is built from. 044
  merged onto it knowingly rather than holding a clean change hostage, which
  its own merge report records.
- **The test post-dates the workdir**, not the other way round:
  `test_evidence.py` arrived with 041, so task 036's full-suite runs were green
  on the same machine with the same run directory. For dating the defect, not
  for blame.
- **A correction to this brief's own first draft.** It said `verdict.py` sets
  `couldnt_check_kind` zero times. That was a grep for `couldnt_check_kind=`
  which missed the spaced assignment form, and the truth is more useful: it is
  set at three sites in one loop, two of which also set a remedy. The routing
  is not absent. It is incomplete, and it has a fall-through that hides its
  own gap.

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
- Every couldn't-check verdict carries a kind and a remedy that names an
  action, or a recorded reason why it cannot — asserted over all 29 in
  `verdict.py`, not over the two that were noticed, and including the
  constraints outside `ENGINE_CONSTRAINTS` that never enter the routing loop.
- `how_to_resolve` routes every kind that carries a remedy, and its
  fall-through no longer returns a reason prefixed with *To decide X*.
- Routing reaches **every constraint**, not only `latency_p95` and `qps`, or
  each constraint it does not reach carries a recorded reason why — asserted
  over a report whose couldn't-checks span more than the engine constraints.
- A tracked input exercises the not-verifiable-here path, so the case fails
  for everyone or for no one.
- The remedy check fails rather than skips where its input is tracked, and the
  report says which inputs are tracked and which may honestly be absent.
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
