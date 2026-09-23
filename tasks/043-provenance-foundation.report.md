# Report: 043-provenance-foundation

## The fifth instance, and I wrote it

**Leading, because it is the most useful thing in this task and it is against
my own work.**

`comparability.facts_of` reads each provenance fact from whichever receipt
carries it. Four times it had been special-cased to one source, reporting an
absence — or a wrong value — that was the reader's own. **While fixing the
fourth, I introduced the fifth.**

I added `run_environment` to `characterize`'s `build_info.json`, believing the
block was missing there. It was not: `build_info` already carried
`environment`, holding exactly the same stamp, three lines from where I was
typing. And `run_environment` does not mean what I assumed —

> **A key whose meaning differs by file is the mechanism.** In `report.json`,
> `environment` is the machine that **measured** and `run_environment` is the
> machine that **wrote the report**. Writing `run_environment` into
> `build_info.json` created a second block that reads as a different fact.

So I added a duplicate under a name that means something else elsewhere, in
the function whose defect is that names mean different things in different
files, in the task that exists to eliminate that defect, having diagnosed it
three times already.

**The only reason it did not ship is that a ruling forced me to look at blocks
rather than fields.** The interface stream's audit arrived mid-build; acting
on it meant reading `report.json`'s two environment blocks, which is when I
saw that `build_info` already had mine. The commit is reverted and stands as
evidence rather than as an embarrassment: the same reader now reads
`environment` from `build_info` where it always was, and **the demonstration
flips with my writer change removed.**

### The premise was wrong three times running

| draft | premise | corrected by |
|---|---|---|
| first | two fields missing from the receipts | the stop-and-show: all three provenance fields read `None` |
| second | three gaps, the third being that `characterize` writes no block | the demonstration failing again after the writer was fixed |
| third | four gaps, the fourth being the reader | the interface stream's audit, and my own reverted commit |
| **true** | **all four were the reader. Gap 3 was never a writer gap.** | |

Each correction came from **measurement**. None came from review, mine or
anyone's. The stop-and-show was the only mechanism that caught any of them,
and it caught them by failing.

### A recommendation for how tasks of this shape are briefed

Not a fact about this task. **A task whose later steps all rest on one
diagnosis should carry a stop-and-show in front of them, not a demonstration
at the end.**

The test is whether the brief has a load-bearing premise — here, *two missing
fields are what silence the verdict* — that steps 2 onward would be built on
and that no step would re-examine. Where it does, the first step is whatever
demonstrates the premise on real artifacts, and the task **stops there** and
reports before the rest is built.

What it costs is one round trip. What it saved here is six steps built on a
premise that was wrong three times over, each wrongness invisible to reading:
the writer looked missing when it was present, the block looked absent when it
was misnamed, and the field looked right when it came from the wrong one of
two blocks that carry the same key. A demonstration at the end would have
found the same thing and found it after the work.

The shape generalises past provenance. It applies wherever a brief says *X is
missing* or *X is broken* and the remedy is several steps of building on that
claim.

### Two things a reader should meet before they matter

Both are honest states rather than defects, and both are easy to trip over
downstream:

- **`ground_truth` in the measured list is currently the sample digest.** No
  receipt distinguishes them, so the key holds the same value as `sample` and
  says so, rather than being quietly absent. A row-level ground truth is what
  BRIDGE §4 will eventually need.
- **`rows_may_share_a_table` cannot return `comparable` today — only
  `couldnt_check`.** `query_subset` is declared and always `None`, because
  BRIDGE §3.3 records that no receipt expresses it. The rule is implemented
  and its answer is bounded by a missing receipt. Anyone building the
  VectorDBBench exporter expecting a green verdict should learn that here,
  and it is now also in the position paper.

## The demonstration, as ruled

```
run-a    environment_id=local:windows-amd64   pod=None   installation=cbfe36458396fe28
run-b    environment_id=local:windows-amd64   pod=None   installation=cbfe36458396fe28

machine ingredient:  unknown -> same
verdict:             not_comparable -> not_comparable      FLIPPED
```

Two real `characterize` runs on this machine. Both recorded the same digest;
the salt never left the machine; the receipts carry no hostname.

**The verdict staying `not_comparable` is the correct outcome.** `settings
differs` genuinely — two workdirs, two requirements files — and `code` is
unknown on a dirty tree. **043 does not make runs comparable. It stops a
missing field from hiding whether they are.** The machine ingredient has
stopped abstaining and started answering, which is the whole claim and the
only claim.

## The wrong value, which no absence test can catch

The interface stream's audit, reproduced:

```
before   environment_id  local:windows-amd64   pod  None    platform  Linux-6.8.0…
after    environment_id  1ombs4scr257a5        pod  1ombs4scr257a5   platform  Linux-6.8.0…
```

On the published arXiv fixture, `facts_of` returned one dict describing **a
Linux pod and a Windows laptop as one run**, silently discarding a pod id that
`verify_info.json` carries. It lands on the only ingredient that matters:
`pod` is the sole path by which `machine` can be known for a remote run, so
**043 would have fixed the local case and left the remote one silently
broken.**

Two latent ones closed with it: `libraries` and `python_version` are carried
by `report.json:run_environment` and were read from the info files only.

## What was built

**The carrier declaration (the design ruling).** `FACT_CARRIERS` maps each
fact to an ordered list of `(file, dotted path)`. `facts_of` iterates it;
nothing reads a receipt any other way. **The order is the precedence rule
written down** instead of implied by the order someone happened to write `if`
statements — which is what this function had never had, and is why five
instances accumulated in it.

The measuring machine precedes the reporting one, and that ordering is
asserted **as an ordering**:

> A test on the behaviour passes when the order changes for the wrong reason.
> `test_the_measuring_machine_wins_over_the_reporting_one` asserts the
> declaration's index order directly, so a reordering is caught at the
> declaration rather than at whichever consequence someone happened to test.

**The reader test is parametrised from the declaration**, not from a
restatement of it — so a carrier added is tested without anyone remembering,
and a carrier the reader claims but does not honour names itself in the
failure. With a mirror asserting a genuinely empty workdir reports genuine
absence, or the whole file passes against a reader returning constants.

**Step 1 — the installation digest.** A truncated `sha256(salt + machine
identifier)`; salt generated once, stored under `~/.oneground`, never
published; identifier never recorded. The platform class was refused for
asserting a sameness it cannot see, pod-only for making a published feature a
demonstration for anyone not renting a machine. It supports *"the same
installation"* and **not** *"the same machine"* — the salt is per
installation — and that limit is written where the field is defined.

**Step 2 — the derived cite.** A cite carrying an operation and its operands,
recomputed by `check()` rather than believed. Its operands are ordinary cites
checked against their sources, so a derived number is checked **down to the
artifacts**. 039b's four mutants: the honest one passes, the inflated,
sign-reversed and ratio-for-difference ones fail, each naming what was
recomputed. The ratio mutant fails **for the right reason** — the operation
was wrong, not the number — and the same value declared as a ratio is a
correct cite, which is the distinction the both-scales rule turns on.

**Step 3 — two provenance lists, and a cross-run index.** `RowIndex.add_run`
holds rows from several runs keyed `(run, subject)`, so two runs measuring the
same configuration label are not silently one row. `Provenance` carries
*what was measured* and *what did the measuring* separately, because two rows
can agree on one and differ on the other **in both directions**.
`query_subset` is declared and always `None` — BRIDGE §3.3 records that no
receipt expresses it — so a comparison over it is couldn't-check and visibly
so, rather than the list quietly having two members where the design says
three.

**Step 4 — cite and extend, not rebuild.** `rows_may_share_a_table` answers
BRIDGE §4's rule at row level, over the two lists, and distinguishes *same
data, different means* from *different data* because those license different
sentences. 041's `verdict` is untouched and is what it delegates to;
`calibrate/history.py:comparable()` keeps its name and its different subject.

**Step 5 — the path, sanitised where it is written.** `receipts.public_path`
and `public_paths_in`, called by `report` at the write site. Sanitising at
publish time is what produced three boundaries in one task and would have
produced a fourth; **a receipt that never contains the absolute path has
nothing to sanitise anywhere.** The note names the transform, not a caller.

**Step 6 — the three positions.** LIBRARY §2.2 now says the verdict is
implemented and what 043 gave it. BRIDGE §4 says the verdict exists **and the
structural refusal is still needed** — the verdict answers whether two rows
may share a table and cannot prevent a table being built from rows that may
not — and records that `query_subset` means two rows can never yet reach
`comparable`, only `couldnt_check`. MODELS' both-scales rule is now
*executable for claims, written for documents*.

**Step 7 — the card.** `verdict.py`'s `delta` is a derived cite. The operands
are ordered to match the direction `verdict.py` already applies, so the order
is the claim rather than a re-signing.

## Verification

| check | result |
|---|---|
| The verdict flips on a characterize-only pair | **PASS** — `machine: unknown → same` |
| It flips with the reverted writer change absent | **PASS** — the declaration reads `environment` where it always was |
| The published fixture reads as one machine | **PASS** — `pod` survives; asserted by a test |
| The measuring machine precedes the reporting one | **PASS** — asserted as an ordering, not as a behaviour |
| Every declared carrier is honoured | **PASS** — parametrised from the declaration |
| A genuinely empty workdir reports absence | **PASS** — the mirror |
| 039b's four mutants | **PASS** — one passes, three fail |
| A derived cite is checked through its operands | **PASS** — breaking an operand fails the derived value |
| No published value moved | **PASS** — `git status fixtures/ site/` empty |

## The sequencing answer (046 step 3)

**Sequence them, one pass, and the invocation field goes last — but the order
that matters is that the carrier is declared before the field is written.**

Four receipt changes land in the same writers this cycle: the salt, the
clean-tree commit, the environment block, and 046's invocation. Independent in
content, not in cost — each is a pass over the same three writers, and **each
pass is a chance to add a key whose meaning differs by file.** This task
demonstrated that risk is real rather than theoretical, at the cost of one
reverted commit.

The declaration is what makes the fourth change cheap instead of the fourth
chance to repeat this. Had it existed, adding `run_environment` would have
meant writing a second carrier for a fact that already had one, in a table
where the existing entry sat three lines above — the collision visible at the
point of choosing the name.

So: **add `invocation`'s carrier to `FACT_CARRIERS` first, with its
precedence, and let the writer follow.** Not a writer change with a reader
change after it.

## Observed, not done

- **`ground_truth` is currently the sample digest.** A row-level ground truth
  is what BRIDGE §4 will eventually need; today no receipt distinguishes them,
  so the key is honest about being the same value rather than absent.
- **The query-subset receipt is still missing**, as §3.3 says. Until it
  exists, `rows_may_share_a_table` cannot return `comparable`.
- **Nothing renders `docs/` from a `Claim`**, so the both-scales rule binds a
  human there. That is the gap task 039's own violations fell into.

## Blocked on developer

Nothing.
