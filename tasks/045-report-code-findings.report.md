# Report: 045-report-code-findings

## Repo state expected vs found

| the brief assumed | found |
|---|---|
| branch `task-045` from `main` | yes — `origin/main` at `da41810`, with 046 merged |
| the work is in `oneground/report/` — `claims.py`, `verdict.py`, `__init__.py` | yes, plus `oneground/lab/citations.py` (it holds the second copy of the path grammar) and `oneground/lab/test_evidence.py` (it owns the remedy check) |
| `claims.py:how_to_resolve` routes two kinds of three | yes, verbatim |
| `verdict.py`'s `else` branch sets `remedy = ""` | yes, at what is now line 1005 |
| `ENGINE_CONSTRAINTS = ("latency_p95", "qps")` gates the routing loop | yes |
| **20** `COULDNT_CHECK` constructions in `verdict.py`, 14 inside `ENGINE_CONSTRAINTS` (latency_p95 9, qps 5) and 6 outside (recall_at_k, storage_amplification, memory_budget 1 each, monthly_budget 3) | **exactly** — parsed from the AST, not grepped (`tasks/scratch/045_sites.py`) |
| 15 `no_engine_comparison` claims, 3,959 characters, in a 37-claim report | **exactly** |
| the remedy test fails on the local arXiv workdir, claims `[33, 34]` | yes |

Three things the brief did not say, found before building, each of which
changed the work:

1. **The fifteen are not one fact.** Fourteen cite two engines that produced
   no value; the fifteenth cites pgvector at 316.87 with `fails`. Collapsing
   all fifteen states an outcome of a row that did not have it. This became
   finding 4's acceptance.
2. **The local workdir's `report.json` has no `oneground` provenance block at
   all.** It was written on 13 September, before the report recorded its own
   producing commit, so it also predates `remedy`. The brief's diagnosis
   (stale artifact, different branch) is right; the marker for it is in the
   artifact and is checkable.
3. **Nothing in the production path passes a workdir to the invariant**, so
   finding 1's step 8 did not run when a report was written. Ruled into this
   task rather than filed; it is finding 6 below.

## What was done

Five findings in the brief's order, and a sixth by ruling: **step 8 was a test
and not a guard.**

### Finding 1 — the invariant never opened a file a cite named

`check()` gains **step 8**: for every cite with a `source` and a value, the
field is read out of the run's receipts and compared with the cited value.
The 606 defect — `verify.json:load.completed` carrying `119.1` where the
field holds `35731` — is now a violation naming both numbers and the path.
Four shapes that are legitimately not a scalar field are **classified, not
failed**: a rule, a requirements input, a wildcard over every option, and a
container whose cited value is one of its members. A source naming a field
that is not there is its own violation, with its own message.

**One path grammar, and where it lives.** `oneground/cites.py`. Both readers
— `report/claims.py` and `lab/citations.py` — import it; the lab module is
now a re-export. It went first to `oneground/receipts/cites.py`, where every
argument for the home was sound, and the lab guard refused it: importing that
package runs `receipts/__init__.py`, which contains `import torch` inside
`library_versions()`. The module moved to the package root, which imports
nothing at all. `docs/PRACTICE.md` §5 records the rule as its fourth entry —
**a module's neutrality is a property of everything its package pulls in, not
of the module** — and it is the first of the four where the wrong home passed
every reasonable test.

**Step 8 is silent when no workdir is given, and a test asserts the silence
is an absence rather than a pass.** That shape is the cheap half of the
coverage rule, and this project has needed it in every conditional check it
has written.

### Finding 2 — a remedy that named the wrong engine

`classify_couldnt_checks` built each per-engine verdict's remedy by joining
**every** engine's coverage decision onto it, so qdrant's verdict carried
pgvector's obstacle. It now filters to the verdict's own engine, and keeps the
whole set where the verdict has no engine — a constraint that is not
per-engine has no one engine's coverage to cite, and an empty remedy there
would turn a real obstacle into silence.

The structure needed no change: the claims were always two, one per engine.
What was ambiguous was the sentence, and with it the source.

### Finding 3 — a machine token in an English sentence

`_r_no_engine_comparison` and `_r_indistinguishable` printed the raw outcome.
`outcome_label` already existed three hundred lines below both. Two more
sites: a `test_verdict.py` assertion that pinned the defect
(`assert "couldnt_check" in text`), and a sentence in `report/__init__.py`
that read "so it is couldnt_check rather than assumed to be default".

### Finding 4 — one fact, stated fifteen times

Rows citing the same engine facts are emitted as **one claim with each row as
a part**. The parent is `UNIVERSAL` over the rows; each part carries that
row's own subject, its own citations, its own `asserts_outcome`, so 5b derives
that row's membership from that option's rows.

A new **step 9** holds the thing a collapse can break: a sentence standing in
for several rows prints their shared facts once, and is admissible only if
every part cites the same facts, member for member.

**And it states what makes the group a group** — ruled after the first
version of the collapse printed the rows' shared reason nowhere. Twelve rows
stating a reason zero times is the same defect as fifteen stating it fifteen
times, from the other side: the grouping is itself a claim, and a sentence
that hides its basis is harder to check than the repetition it replaced.

Step 9 holds this with **two checks, not one**, because either alone is
satisfiable for free and the other side of the defect walks straight through
it. A check that only demands a basis is satisfied by stating anything —
`detail = "because it was convenient to group them"` passes it as readily as
the true reason. A check that only compares a stated basis to the members is
satisfied by stating nothing — the twelve rows go back to citing their reason
zero times and there is nothing there to compare. Only both together enforce
the ruling: `detail` must be present when the rows share a reason, and when
present it must be one of the reasons they actually carry. The two mutation
tests in `test_one_fact_one_sentence.py` each defeat one check and are caught
by the other. `docs/PRACTICE.md` §4.1 records the rule.

### Finding 5 — a couldn't-check whose remedy restates the obstacle

The routing first, the prose after, in that order.

1. **Every couldn't-check `verdict.py` builds records a kind and a remedy** —
   20 construction sites, all 20. Where the action was already written into
   the `reason` (the no-verify-run rule, the no-load-phase rule) it moved to
   the field and the reason kept the obstacle.
2. **`classify_couldnt_checks` stops writing `v.remedy = ""`.** `not_verified`
   is the one kind whose remedy is always an action — task 034's own docstring
   says so — and the empty string is what sent every verdict on that branch to
   the fall-through.
3. **`how_to_resolve` routes on the presence of a remedy**, not on a list of
   two kinds, so a kind introduced later arrives routed. Its fall-through no
   longer prefixes an obstacle with *To decide X*; when nothing is recorded,
   the absence is the sentence.

The coverage classification still wins where it applies, and the order is now
asserted: an engine that cannot build the family is a deeper obstacle than the
run that was not made.

### Finding 6 — the check ran in tests and nowhere else

Ruled in rather than filed, and the ruling is the finding's own subject: a
repair exercised only by its own test is a test, not a guard, and leaving it
would have been 045 reproducing what it is about.

Three things, in order, because each is the next one's precondition.

1. **The under-specified citation step 8 found is tightened.** `latency_p95`'s
   `meets` branch cites the *worst* run and its `fails` branch the *best*, and
   both named the whole `p95_across_runs` object. They now name `.max` and
   `.min`. The couldn't-check branch keeps the container deliberately: it
   cites no value and what it is about *is* the spread.
2. **A fifth non-field shape: `PENDING`.** Wiring the gate surfaced something
   the tests could not: a report's claims cite `report.json:options[...]` and
   a proposal card's cite `card.json:measured...` — **the document the check
   is a precondition for writing.** It cannot be read at the moment it is
   checked because the check is why it does not exist yet, which is a
   different fact from a path naming nothing. The caller declares it; an
   undeclared absence stays a violation, which is what stops this being a way
   to switch step 8 off.
3. **The workdir is passed at both call sites.** `report/__init__.py:1327`
   with `pending=("report.json",)`, `propose.py:612` with `plan.workdir` and
   `pending=("card.json",)`. `raise_on_violation`, `check_all` and `check` all
   take `workdir` and `pending` now.

And one more instance the wiring found, which no test would have: `qps_max`'s
cite named `verify.json:qps_max`, a block holding the rate, the concurrency,
the p99 and the stop reason, while carrying only the rate. The cite now names
`verify.json:qps_max.qps_max`; the claim's own `source` still names the block,
because the block is what the sentence is about.

## Measurements

Every number below was produced by a script in `tasks/scratch/` that imports
project code unmodified. The scripts are named after the finding.

### Finding 4: fifteen claims into three

`tasks/scratch/045_finding4_shape.py` reads the stored report;
`045_finding4_after.py` rebuilds the report's options from it and puts them
back through `compare_engine_claims`.

| | claims | characters |
|---|---|---|
| `no_engine_comparison`, stored | 15 | 3,959 |
| `no_engine_comparison`, rebuilt | **3** | 1,739 |
| …with each group stating its basis (ruled) | **3** | **2,309** |

The basis costs 570 characters and the collapse still removes 42%. They are
the best-spent characters in the sentence: they are what makes it checkable.

The three: 2 hash_sharded rows, 12 semantic_sharded rows, and the
single_node_hnsw row that cites something else and stays its own sentence.

**No fact was dropped**, measured two ways: the set of `(configuration,
constraint)` rows stated is the same 15 before and after — `dropped: none,
added: none` — and the cited engine facts for every one of those rows are
unchanged — `rows whose cited engine facts changed: none`.

**The report's claim count: 37 → 25.** Confirmed independently by rebuilding
the whole claim set (`decision_claims` 23 + `qps_max_claims` 2 = 25), which is
asserted in `test_prose_has_no_outcome_tokens.py`.

Why three and not two: the grouping key is the whole cited substance,
including each verdict's `reason`. hash_sharded's reason names a hash_sharded
deployment and semantic_sharded's names a semantic_sharded one. Step 9
enforces the weaker, sentence-level condition — do not print a fact that is
false of a row — and the emitter groups more finely so that two different
explanations are not merged into a sentence carrying neither.

### Finding 4: the mutant, and the proof it is step 9 that refuses it

`tasks/scratch/045_finding4_mutant_proof.py`:

```
with step 9:    1 problem(s)
   collapsed claim states one set of engine facts for 15 rows, but
   ['single_node_hnsw[...]: latency_p95'] do not share it: ...
without step 9: 0 problem(s)
step 9 is the rule that refuses it: True
```

The sentence it refuses, in full, begins *"15 rows were not compared across
engines because fewer than two engines produced a value -- qdrant
(couldn't-check), pgvector (couldn't-check) in each"* — of a row where
pgvector produced 316.87.

### Finding 5: the routing, before and after

`tasks/scratch/045_finding5_ab.py`, run once against the working tree and once
with `verdict.py` and `claims.py` stashed. Each case is produced by the rule
that produces it in a real run.

| case | before: remedy / kind | after: remedy / kind |
|---|---|---|
| recall_at_k, k not swept | — / none | yes / `not_verified` |
| storage_amplification absent | — / none | yes / `not_verified` |
| memory_budget absent | — / none | yes / `not_verified` |
| monthly_budget, no cost model | — / none | yes / `not_verifiable_here` |
| monthly_budget, no priced row | — / none | yes / `not_verified` |
| latency_p95, no verify run | — / none | yes / `not_verified` |
| **latency_p95, wrong family built** | — / none | yes / `not_verified` |
| qps, no load phase | — / none | yes / `not_verified` |

The headline case, verbatim:

> **before** — To decide latency_p95: this configuration was not the one
> verified -- the verify run built hnsw in a single namespace, which is not a
> hash_sharded deployment.
>
> **after** — To decide latency_p95: verify this configuration, built as
> hash_sharded, on a real engine: `oneground verify` against a deployment that
> is a hash_sharded one. The run this report reads built something else, so no
> measurement in it settles this row.

Three of the eight "before" sentences were actionable, and each for the wrong
structural reason: two had the action written into the `reason` field, and one
(`monthly_budget`) had it hard-coded in `how_to_resolve` — which is why the
same sentence was printed for *no cost model in this build* and *this row was
not priced*, two different obstacles with two different answers.

And the fall-through, where nothing is recorded:

> Nothing recorded in this run settles recall_at_k, and no remedy for it is
> recorded either. The obstacle was: the sweep row is empty.

### Finding 5: the 20 construction sites

`tasks/scratch/045_sites.py` walks `verdict.py`'s AST.

```
20 COULDNT_CHECK construction sites; 20 record a remedy; 20 a kind
```

Split, matching the brief exactly: latency_p95 9, qps 5 (inside
`ENGINE_CONSTRAINTS`); recall_at_k 1, storage_amplification 1, memory_budget
1, monthly_budget 3 (outside it, and never entering the routing loop before
this task). The same walk is now a test, so the rule reaches sites that do not
exist yet.

### Finding 5: on the tracked arXiv bundle

Judged from `fixtures/arxiv-150k/report/` receipts rather than from the
`report.json` they sit beside (`045_finding5_after.py`):

- couldn't-check verdicts: 29, all carrying a kind and a remedy.
- **couldn't-check verdicts with no remedy: 0.**
- With `coverages=None` — the configuration that isolates the branch finding 5
  is about — 29 rows reach the mismatch branch, carry `not_verified`, and
  produce a sentence naming the family to build.

### Finding 2: the narrowed citation resolves

`tasks/scratch/045_finding2_resolves.py`, on
`verify_info.json:engine_facts.index_params`:

| member | kind | what came back |
|---|---|---|
| unset | **unresolved** | `no field 'engine_facts' here` |
| `qdrant` | field | `{ef_construct: 200, m: 32, ...}` |
| `pgvector` | field | `{ef_construction: 200, m: 32, opclass: ...}` |

Which is the finding in one table: the path is meaningless without an engine
and resolves with one, and 041's interface rendering it `unresolved` was
correct rather than a display fault.

### Finding 3: over a real report

`tasks/scratch/045_finding3_realreport.py`, and now
`test_prose_has_no_outcome_tokens.py`:

| | stored report | rebuilt |
|---|---|---|
| claims | 37 | 25 |
| containing `couldnt_check` | **16** | **0** |

`meets` and `fails` appear in 4 and 14 claims respectively, before and after,
and are not tested for: they are the English words the sentences are made of.
`couldnt_check` is the one outcome whose constant is not a word anybody would
write.

### Finding 6: the gate, before and after

`tasks/scratch/045_gate_on_fixture.py`. The arXiv bundle's 25 claims, judged
from its receipts by today's rules, then checked the way
`report/__init__.py` checks before it writes.

| checked | claims with a citation problem |
|---|---|
| as the gate runs it (`pending=("report.json",)`) | **0** |
| with `report.json` readable as well | **0** |
| the **stored** `report.json`, same workdir | **4** |

The four are the artifact, not the code: two claims citing
`…p95_across_runs` and two citing `verify.json:qps_max`, both tightened in
this task, both still in the file that was written before it. The same
distinction as finding 3's, arrived at from the other direction.

Before the wiring, all three rows of that table read **0**, because
`raise_on_violation` took no workdir and step 8 never ran.

### Tests

| file | tests | subject |
|---|---|---|
| `report/test_citation_is_true.py` | 15 | findings 1 and 6 |
| `report/test_remedy_names_one_engine.py` | 2 | finding 2 |
| `report/test_prose_has_no_outcome_tokens.py` | 3 | finding 3, over a real report |
| `report/test_one_fact_one_sentence.py` | 9 | finding 4 |
| `report/test_remedy_is_not_the_obstacle.py` | 9 | finding 5 |

Two existing tests in `verify/test_matched.py` changed, and both were the
defect rather than collateral: each asserted that an action was in `v.reason`.
Passing is what kept it there.

## Verification

### Passed

- **Full suite green: `1776 passed, 41 skipped` in 11m58s**, exit 0, with the
  gate wired. For comparison, the tree at the start of this task was
  `1750 passed, 40 skipped, 1 failed` — the failure being
  `test_every_couldnt_check_claim_carries_a_remedy`, which finding 5 is about.
  The extra skip is that test's local-workdir arm, which now skips on a
  recorded reason instead of failing against a stale artifact; its rule is
  held by the tracked companion, which raises.
- **Every new rule has a mutant that runs the rule's own code.**
  - Finding 1: `test_the_mutant_verdict_606` — a cite carrying `119.1` against
    a field holding `35731`, which must fail naming both.
  - Finding 4: the fifteen collapsed on the sentence rather than on what they
    cite.
  - Finding 5: two mutants, one per half — the action in the `reason` field,
    and the reason wearing a remedy's opening words.
  - Finding 6: the same gate, with and without a workdir, on the same claim —
    `raise_on_violation` raises with one and returns with the other, which is
    what every production call site did until this task.

- **A mutant should name the rule, not only the absence of the defect.**
  Finding 4's does, and it is worth stating as a form rather than as a detail
  of one test. Running the mutant with step 9's marker removed leaves the
  same claim passing **every other rule in the invariant**: 1 problem becomes
  0. So the result is not "the collapse is now refused" — which any of nine
  rules might have been doing — but "**step 9 is what refuses it**". A mutant
  that only shows the defect gone leaves open that a neighbouring rule caught
  it by luck, and a rule caught something by luck once is a rule nobody can
  rely on next time. Removing the candidate rule and watching the mutant pass
  is one extra run and turns *the defect is caught* into *this is the thing
  catching it*.

- **The honest number for finding 5 is eight and one.** All nine of its tests
  are red against the unfixed tree, but the ninth
  (`test_the_coverage_routing_still_wins_where_it_applies`) is red on
  `how_to_resolve`'s signature, not on the defect. **Eight tests prove the
  repair and one proves the interface moved**, and counting nine would have
  been claiming a demonstration that was an API artefact.
- **The mutants are proved to be defects before they are proved to be caught.**
  Finding 4's asserts the rendered sentence actually says
  `pgvector (couldn't-check) in each` and that the odd row actually cites
  `316.8743 / fails`, so the check is not firing on a sentence nobody would
  print. Finding 3's earlier draft made exactly that mistake — it tested
  `composed_text()` on unrendered claims and proved a token absent from an
  empty string.
- **`site/teaser/` byte-unchanged** — `git diff main --name-only -- site/teaser/`
  is empty.
- **No published value changed.** `fixtures/arxiv-150k/report/report.json` is
  untouched; the rebuilds above are in memory.

### What is tracked and what may honestly be absent

The brief asks the report to say which is which.

| input | status | behaviour when absent |
|---|---|---|
| `fixtures/arxiv-150k/report/` (report, simulate, verify, verify_info) | **tracked** | **raises.** Used by all 9 finding-4 tests, 3 of finding 5's, and all 3 of finding 3's |
| `oneground/lab/testdata/041-pre-fix-report.json` | **tracked**, digest pinned | raises (pre-existing) |
| `runs/arxiv-150k-via-characterize` | local run | skips, naming the command |
| `runs/041-ui/support-tickets-2026q3` | local run | skips, naming the command |

`test_every_couldnt_check_claim_carries_a_remedy` now has a tracked companion
that raises, and its local-workdir arm skips **only on a report whose own
`oneground` provenance block is absent** — that is, one written before the
build recorded a producing commit, and therefore before `remedy` existed. A
reason rather than an absence. `docs/PRACTICE.md` §2 warning 6 already records
the general form; the repair is noted beside it.

### Failed

None outstanding. One test changed because it pinned a defect:
`test_a_family_the_engine_builds_is_merely_not_verified_synthetic` asserted
`v.remedy == ""` one line below a docstring calling the remedy *"run it"*.
That is how the empty string survived from task 034 to task 045, and the
docstring was right the whole time.

### Couldn't check

- **Whether the local `runs/arxiv-150k-via-characterize` report would pass the
  remedy check after regeneration.** Not measured, because the brief forbids
  regenerating it and the reason it gives is correct: `TIER1` is several other
  tests' subject, and a regenerated report reaches the coverage branch, which
  routed before this task. A pass there would prove a different branch was
  taken.
- **Whether the live gate refuses a real `oneground report` run end to end.**
  Measured to one step short: the arXiv bundle's 25 claims pass
  `check_all(..., workdir, pending)` with the arguments `run()` uses, and the
  gate itself is shown raising and not raising on the same claim. What is not
  measured is a full `run()` over a corpus, which needs a workdir with the
  vectors and is not something this machine holds.

## Observed, not done

**1. The two stored artifacts are now measurably behind the code**, and
neither was regenerated. `fixtures/arxiv-150k/report/report.json` carries 16
sentences with the `couldnt_check` token and four claims whose citations name
a container; `runs/arxiv-150k-via-characterize/report.json` predates
`couldnt_check_kind` entirely. Both are recorded here with the exact counts
rather than quietly fixed: regenerating the fixture is a rebuild with its own
digests and its own ruling, and the brief forbids regenerating the run.

**2. `report.json` and `card.json` are the only two `pending` documents named,
and the list is per call site.** A third gate added later gets this right only
by someone remembering. Deriving it — the document being written is the one
the caller is about to write — would need the writer and the checker to be the
same function, which they are not. Small, and the shape this task keeps
finding.

**3. ~~The collapsed sentence does not print the shared reason.~~ Ruled in
and done** — see finding 4 above and `docs/PRACTICE.md` §4.1. Left here with
its original text struck rather than deleted, because what it said was that
nothing had regressed, and that was true and was also why it would never have
been noticed. Each part
keeps its own, so nothing is lost from the record, but the twelve
semantic_sharded rows share one explanation that no sentence now states —
where before it was stated zero times across fifteen. Printing it once is a
prose change beyond the brief's list.

**4. The decision log's order changed for collapsed claims.** A group is
emitted where its *first* member appeared, so the second and later members of
a group move earlier in the log. Nothing reads the log positionally.

**5. `test_no_lent_outcomes.LOG_BUILDERS` is a hand-maintained list.** Moving
the no-comparison emission into its own function removed
`no_engine_comparison` from the derived set within one run, and the test's
staleness assertion — the half with nothing to catch on most days — caught it.
Worth recording that the half nobody writes is the half that fired.

**6. The brief's commit-message convention.** It says `task 045:`; the repo's
history uses `NNN:` (`046: the ruling on the seven…`). I followed the repo.

## Repo now contains

New:

- `oneground/cites.py` — the shared path grammar
- `oneground/report/test_citation_is_true.py`
- `oneground/report/test_remedy_names_one_engine.py`
- `oneground/report/test_one_fact_one_sentence.py`
- `oneground/report/test_remedy_is_not_the_obstacle.py`
- `oneground/report/test_prose_has_no_outcome_tokens.py`

Changed:

- `oneground/cites.py` — `PENDING`, the fifth non-field shape;
  `resolve(pending=)`; the stale "why receipts is the home" paragraph replaced
  with why the package root is
- `oneground/report/claims.py` — step 8, step 9, `_cites_of`, `_same`,
  `check`/`check_all`/`raise_on_violation` take `workdir` and `pending`,
  `part(subject=, asserts_outcome=, holds_rule=)`, `how_to_resolve` rewritten,
  `_r_no_engine_comparison` handles both shapes
- `oneground/report/verdict.py` — 20 couldn't-check sites record a kind and a
  remedy; `mismatch_remedy`; `_decisions_for`; `NOT_VERIFIABLE_HERE` and
  `OFF_ENGINE_CONSTRAINTS`; the `else` branch keeps the remedy; latency
  `meets`/`fails` cite `.max`/`.min` rather than the container
- `oneground/report/__init__.py` — `no_comparison_claim`,
  `_no_comparison_substance`, `_NoComparison`, `_shared_reason`; the gate
  passes `workdir` and `pending`; `qps_max`'s cite names the field; one prose
  fix
- `oneground/proposals/propose.py` — the card's gate passes `plan.workdir` and
  `pending=("card.json",)`
- `oneground/lab/citations.py` — re-exports the shared grammar
- `oneground/lab/test_evidence.py` — a tracked remedy check that raises; the
  local arm skips on a recorded reason
- `oneground/verify/test_matched.py` — two tests that asserted an action was
  in `reason` now assert it is in `remedy`
- `oneground/report/test_verdict.py`, `oneground/report/test_no_lent_outcomes.py`
- `docs/PRACTICE.md` — §4.1, *a collapse states what makes the group a group,
  once* (ruled); §5's fourth entry (ruled); §2 warning 6 notes the repair

Scratch (gitignored, listed so the measurements can be re-run):
`tasks/scratch/045_token_fresh.py`, `045_finding2_resolves.py`,
`045_finding3_realreport.py`, `045_finding4_shape.py`,
`045_finding4_substance.py`, `045_finding4_after.py`,
`045_finding4_source.py`, `045_finding4_mutant_proof.py`,
`045_finding5_before.py`, `045_finding5_drawer.py`, `045_finding5_after.py`,
`045_finding5_ab.py`, `045_sites.py`, `045_propose_workdir.py`,
`045_gate_on_fixture.py`.

Commits on `task-045`:

| | |
|---|---|
| `76d7dba` | findings 1, 2, 3 |
| `712bd99` | finding 4 |
| `0eeb4cd` | finding 5 |
| `bc7f0bf` | finding 3's assertion over a real report |
| `b2d33e8` | finding 6 — the check becomes a guard at both gates |
| `1a4b74b` | this report |
| *(next)* | the collapse states its basis (ruled) |

## Blocked on developer

**Publishing is yours.** `git push -u origin task-045` was refused by this
session's permission layer ("out-of-place publication"), not by git or by the
remote, and I did not route around it. Commits landed after you said you were
pushing — `b2d33e8` (finding 6), `1a4b74b` (this report) and the basis ruling
— so re-push before merging, or merge from local.

No rulings outstanding. One thing worth knowing rather than deciding: **the
gate is now live on
`oneground report` and `oneground propose`.** A report whose citation names a
field holding another value, or names a field that is not there, will refuse
to be written. That is the intent, and it is a behaviour change — the first
run that trips it will look like a regression in whatever produced the
citation, which is exactly what it is.
