# Report: 041-interface-read

*The findings below were produced while building and are recorded as they were
found, rather than held to the end. Eight findings; five are about the
artifacts and the report code rather than about the interface, which is what
happens when a page is asked to show where every number came from.*

## Repo state expected vs found

The brief assumes `docs/INTERFACE.md` on main as its specification. Found:
`task-039` unmerged, carrying both the paper **and** the brief, so 041 could
not start; `tasks/README.md` on main says so rather than the task blocking
silently. 039 merged at `43c4a3b` six minutes into the hour, and both files
were byte-identical to the versions read on the branch.

Three mismatches between the brief and the tree, all ruled on before building:

1. **The 021 contract is bound to simulator state, not receipts.**
   `draw(view, header, columns)` takes numpy columns and derives `source` and
   `epsilon` from state-header keys. Steps 3–5 read receipt JSON, which has
   none of those. Generalising it is the slice's central design work, not
   plumbing.
2. **Two report tiers exist and the brief names one.** Tier 1 carries
   `claims` and a `summary`; Tier 2 (`run_declared`, current code) carries
   neither — no options, no claims, and every constraint `couldnt_check` by
   construction. Ruled a *required* case rather than a crash guard: it is the
   slice's best demonstration of step 6's equal-weight rule.
3. **Step 5's acceptance was not satisfiable as written.** "Every entry
   resolves to a real field in a real file" would require making the
   `recommendation` claim's `(rule)` source look like a citation. Ruled:
   every claim gets an entry, and every entry either resolves to a file and
   field or names which of the three non-field kinds it is.

The paper's §8 assigns the pod session card to slice 1 while its own §4.2
mechanism forbids it — `oneground.pod` is in the guard's `MEASURING` list and
`cmd_plan` writes no receipt to render instead. Ruled: deferred to slice 2,
the mechanism deciding the slicing rather than the sequencing. Neither route
was built.

---

## Finding 1 — the claim invariant's name promised more than it checked

**This is the finding of the task so far, and it outranks the fix it
produced.**

Task 019 established the claim invariant: every sentence in a report is a
`Claim` carrying the rows it cites, so a reader can reconstruct the sentence
from its evidence. `test_the_invariant_holds_on_both_fixtures_real_reports`
runs it against real reports.

It checks that a claim **is reconstructible from what it cites**. It never
checks that **the cited field holds the cited value**.

That gap is not theoretical. Building the evidence drawer — which by ruling
may not import `oneground/report/claims.py`, and so must resolve each
citation by parsing its `source` and looking the field up — surfaced two
citations that named the wrong field:

| where | cited | the field named actually holds |
|---|---|---|
| `verdict.py:606`, throttled qps | `119.1` | `load.completed` = **35731** |
| `verdict.py:670`, budget | a monthly figure | `costs["config"]` — **never a key** |

The first is a sibling-field error: `value` came from `load.achieved_qps` and
the source named `load.completed`. The second is an unsubstituted placeholder;
the analogous line in `corpora/export_teaser_data.py:1042` interpolated the
label correctly.

**What makes this a finding rather than a bug report:** the wrong citations
survived the claim invariant, two other real-report tests, a published
fixture, and the teaser. Nothing in the project compared a `source` against
its `value` until a UI was asked to render the two side by side. A drawer
that shows "the field this came from, and the value at that field" cannot
help but check it — which is why the defect was found by the feature rather
than by a test.

The repair is a property, not a string:

```python
found, at_field = _walk(data, v.source)
assert at_field == v.value, f"{v.source} holds {at_field!r} but the verdict cites {v.value!r}"
```

asserted across the throttled, sustained and unthrottled branches, so the
pair cannot drift apart again in either direction.

**Couldn't-check:** whether other claim kinds carry the same defect in runs
not on this machine. Three of the four `source` patterns that do not resolve
to a scalar are not defects — two name a container whose cited value is a
leaf inside it (`p95_across_runs` → its `.min`; `qps_max` → its `.qps_max`),
and `(rule)`, `requirements:constraints` and `options[*]` are legitimately
not single fields. A general checker would have to distinguish those four
shapes, and this task did not build one.

---

## Finding 2 — the teaser's provenance is unverified, and nothing checks it

`site/teaser/data/values.json` states, beside every figure, the receipt field
that figure came from. That stated provenance is the thing the page exists to
demonstrate.

Re-running the export against the fixture the page cites **fails**:

    corpora/export_teaser_data.py --report fixtures/arxiv-150k/report/report.json
    KeyError: 'searches'   (build_verify, line 859)

`build_verify` reads a single-engine verify shape — `v["searches"]`,
`v["load"]` at the top level. The published fixture ships the multi-engine
shape, `engines: [qdrant, pgvector]`, with `searches` and `load` one level
down inside each engine. The two cannot both be right, so **whatever produced
the current `values.json` was not this fixture's `verify.json`.**

**What it implies.** The teaser's figures may be perfectly correct. What is
unverified is their *stated provenance* — that this number came from that
field of that receipt. A page whose entire argument is "every figure names
the file and field it came from" is the last place where the link between
figure and file should be unchecked, and it is currently the only published
surface where nothing checks it. The failure mode is not a wrong number; it
is a right number with an unverifiable citation, which is the one thing that
page exists to refuse.

**What a check would look like** (not built here, by instruction):

- The export refuses to run unless `--report` and `--verify` name receipts
  whose digests appear in the cited fixture's `MANIFEST.sha256`, so the page
  can only be built from the fixture it claims.
- After export, every `source` string in `values.json` is resolved against
  those receipts and compared to the value beside it — the same property
  Finding 1 established for `verdict.py`, applied at the publishing boundary.
- The multi-engine shape is handled explicitly, or the export refuses a
  multi-engine `verify.json` by name rather than dying on a `KeyError`.
- The check runs in the suite against the published `site/teaser/data/`, so
  the page and the fixture cannot drift apart again unnoticed.

`site/teaser/` was not touched in this task. The exact changes it needs are
listed under "Observed, not done".

---

## Finding 3 — a receipt carrying a machine-local path cannot be published

`report.json` records `price_table.path` as the absolute path of the checkout
that produced it:

    C:\Users\<developer>\projects\oneground-v2\oneground\cost\prices.example.yaml

That line is redacted here, and it was not redacted when this section was
first written. The identifier scan failed on `tasks/041-interface-read.report.md:145`
— the paragraph explaining that published artifacts must not name a
developer's filesystem, naming one. It is the fifth time this month a report
has been caught by a guard its author did not write, and the first time the
guard caught a report about the very rule it enforces. The general form of the
032 catch holds exactly: the author checks the thing they were thinking about,
and the guard checks the thing they were not.

Stated generally: **a receipt field holding a machine-local path cannot be
published by running the command that produces it.** Either the field is
transformed at publish time by one shared implementation, or the receipt is
not publishable at all. There is no third option, because a tracked file
carrying a developer's home directory fails
`test_no_tracked_file_carries_a_machine_identifier` — as the rebuilt fixture
did, before the transform was applied.

Two consequences worth separating:

- **It is not reproducible.** Two checkouts of the same commit produce
  different `report.json` bytes from their locations alone. That bears on the
  paper's §2 discussion of what must be byte-identical and what may differ:
  this field belongs in the "may differ" list explicitly, or it stops being
  recorded that way.
- **The one shared implementation exists, and was written for a different
  caller.** `corpora/export_teaser_data.public_price_table` does exactly the
  right transform — repo-relative inside the repository, basename outside —
  and its docstring states the principle plainly: *"a published page has no
  business naming a developer's filesystem."* But it lives in the teaser
  exporter, and its `path_note` says "rewritten by the teaser export", which
  is false for every other caller. The fixture rebuild reused it and replaced
  only that note. A second caller reusing a function whose own note names the
  first caller is the shape of a thing about to be copy-pasted.

---

## Finding 4 — a citation that cannot be reconstructed from what it names

The two `to_resolve` claims in the arXiv report cite
`verify_info.json:engine_facts.index_params`. The drawer renders both
`unresolved`, and that is the true answer rather than a limitation of the
drawer.

`engine_facts` lives under `engines[]`, one level below where the source
points, and these claims carry no `member`. But the missing member is the
symptom, not the defect. The claims' own text spans **both** engines —
*"pgvector has not been asked what index families it builds … qdrant has not
been asked …"* — so there is no single engine whose value the sentence rests
on.

**This is not the family the two fixed defects belong to.** Those cited a
field that held a different value; the field was right there and the source
named its neighbour. This one names a per-engine field from a claim about
every engine, and so cannot be reconstructed from what it names at all.

That is why the obvious repair is the wrong one. Rewriting the source as
`verify_info.json:engines[].engine_facts.index_params` would make the entry
resolve while still not saying which engine's value the sentence rests on — a
link that looks right and answers nothing, which is worse than one that says
it cannot answer.

**The real fix is where the claim is written, not where it is rendered:**
either two claims, one per engine, each with `member` set, or one claim citing
both values. Both are report-code changes in `oneground/report`, and neither
belongs to this task. The drawer's `unresolved` entry, with its reason, is the
correct rendering until that happens.

---

## Finding 5 — no two runs in this product can be compared, including two copies of one

**This is what step 7 produced, and it leads everything else that step
produced.**

`docs/LIBRARY.md` §2.2 specifies the comparability verdict, says it is
*"written here and implemented nowhere"*, and predicts its own answer:
*"today the honest value is `couldnt_check`, on the code, because no artifact
records the oneground version that measured a row."* Task 041 was the first of
the three positions depending on it to reach it, so 041 built it. The
prediction is now a measurement.

**Ten of ten pairs of the five local runs are unable to reach `comparable`,
and `code` is unknown in every one.** The sharpest case is not two different
runs but two byte-identical copies of the same one:

| ingredient | state | required |
|---|---|---|
| `code` | **unknown** | yes |
| `libraries` | same | yes |
| `settings` | same | yes |
| `sample` | same | yes |
| `platform` | same | no |
| `python_version` | same | no |
| `machine` | **unknown** | yes |

Same libraries, same requirements digest, same sample digest, same platform,
same interpreter — and the verdict is `couldnt_check`.

### A correction to this finding, and it survives it

As first written, this finding said *no artifact records the oneground
version*. That was wrong, and the error was in the reader rather than in the
artifacts: task 033's block **is** written by current code, into `report.json`
itself, and `facts_of` looked only at the `_info.json` receipts. The
regenerated arXiv report carries
`{"version": "0.1.0", "commit": "43c4a3b…", "dirty": true}`.

The reader now reads it, and the finding holds for a sharper reason:

- **four of the five local runs record no version at all** — their reports
  predate the field, and nothing can add a version to an old artifact
  honestly;
- **the one that records it records `dirty: true`**, meaning uncommitted
  changes were in the interpreter. A commit with a dirty tree does not
  identify the code that ran, so it is `unknown` with that reason rather than
  a match. This is §2.2's own worry made concrete: task 028c found today's
  build answering `recall_at_1` 0.874 where a recorded row said 0.875, and a
  dirty tree is exactly how two runs at one commit come to be two different
  programs.

So the ceiling is real and it has two floors, not one. Stated plainly:
**until a run records the version that produced it *from a clean tree*, no
two runs in this product can be compared — not two runs of different corpora,
not two runs of the same corpus, not two copies of one run.** Every
side-by-side view, every card in the library and every row of the
VectorDBBench bridge inherits that ceiling.

**This is the strongest argument for 043 that exists**, and the correction
strengthens it rather than weakening it. A task that only backfilled the
field would still leave `dirty` and `machine` unanswered. The gap is not
theoretical, not a corner case, and not fixable at the rendering layer: a
missing or unusable version can never be read as a match, so the verdict is
correct and the artifacts are what must change.

## Finding 6 — a gated commit is run in the foreground

Not a defect in the product, and recorded because the next person will be
tempted the same way.

Two suite-and-commit commands were backgrounded while each gated its commit
on the suite passing. The first had not reported when the second started, so
its files were still staged; the second's `git add -A` swept them up, and its
commit message — which described only the comparability work — would have
landed on a commit containing three steps' worth of changes.

**The gate held.** Nothing half-committed, because the commit could not run
until pytest passed, and stopping both left the tree exactly as it was. What
failed was not the gate but the sequencing around it.

The rule, for next time: **a gated commit runs in the foreground.** A second
one started before the first reports will describe contents it does not
contain, and a commit message that misdescribes its own diff is a receipt
that lies — the same class of defect as a citation naming the wrong field,
which is the thing this task exists to have found.

---

## Finding 7 — the report writes a machine token into its own prose

Sixteen of the arXiv report's 37 claim sentences contain the literal string
`couldnt_check` inside the sentence a reader is meant to read:

> `hash_sharded[…]: latency_p95 was not compared across engines because fewer
> than two engines produced a value -- qdrant (couldnt_check), pgvector
> (couldnt_check).`

and `oneground/report/__init__.py:715` writes *"so it is couldnt_check rather
than …"* directly into a claim.

This is the caption rule of task 035 and defect 5 of this task's own interface
review, one layer further in: a value that exists so a machine can compare it
has been printed where a sentence belongs. The interface strips the token
wherever *it* composes a line — a gap heading, a drawer note, a remedy —
because there the heading already says "couldn't check".

**It is not stripped from a claim, and that refusal is the rule rather than a
limitation.** The page renders a claim verbatim; a renderer that edited the
report's sentences would make the screen and the receipt disagree, and a
reader comparing the two would be right to trust neither. An ugly token on
screen is a smaller fault than a page that quietly improves its source.

The fix is in `oneground/report`: `__init__.py:715`, and wherever the
per-engine tuples `(couldnt_check)` are composed. It is report-code work and
this task did not do it.

---

## Finding 8 — one fact, stated fifteen times, outweighs every verdict

Measured on the arXiv report, and found because a page made the shape
visible:

| | claims | characters |
|---|---|---|
| all 16 claims that state a verdict | 16 | **3,659** |
| one `no_engine_comparison` sentence, repeated | **15** | **3,959** |

Fifteen of the 21 claims that state no verdict are the same sentence —
*"&lt;config&gt;: &lt;constraint&gt; was not compared across engines because
fewer than two engines produced a value — qdrant (couldnt_check), pgvector
(couldnt_check)"* — differing only in the configuration label and the
constraint name. They are individually true and collectively one fact: **two
engines were measured and only one produced a value.** Repeating it per
configuration says nothing a reader did not know after the first.

The consequence is not cosmetic. On a page that lists claims, one fact
occupies more room than every verdict in the report put together, so the
thing a reader came for is outnumbered by a restatement.

**The claim invariant already supports the shape this wants.** A `Claim`
carries `quantifier`, `holds_for` and `holds_rule`, and task 019's step 5b
derives `holds_for` from the rows rather than believing it. A claim that is
true once per configuration and identical in substance is a claim *universally
quantified over those configurations*, with one sentence and fifteen members
in `holds_for` — which is what the field is for.

This task did not change it. It is report-code work, it belongs beside
Findings 4 and 7, and the page is the reason it is visible rather than the
place it should be fixed.

---

## Correction to the brief — the demo downloads nothing

Step 2 specifies that `--demo` fetches the fixture it needs "if absent, with
the download **named and sized before it starts** and a refusal if the user
declines". Built as specified, that machinery would never run: the published
`arxiv-150k` fixture's report bundle is in the repository, 256 KB of real
receipts with real digests, and nothing the read half reads is absent. The
only thing a fetch could pull is the 460 MB of vectors, which no page in this
slice reads.

**Recorded as a correction to the brief rather than as a deviation from it.**
A fetch that never fires is a feature that lies about what it does: it
advertises a consent step nobody is ever asked for, and it would have to be
maintained, tested and documented as though it were real. The demo says
`nothing was downloaded: every receipt this page reads is in the repository`,
which is both shorter and true.

The brief's conditional — "if absent" — is doing the work. Nothing is absent,
so nothing is fetched, and the page says which of those two facts it is acting
on.

**What the fixture genuinely does not ship is simulator state**, so the demo
opens the run list, the run's finding and the report with its drawer, and
cannot open the ground or the trace. It cannot open the side-by-side either,
for an unrelated reason: that needs two runs and the demo is one. All three
limits are stated on the page and in `docs/UI.md` as facts about what a
fixture publishes, not as missing features.

---

## What was built

**The contract, generalised** (`oneground/lab/receipt.py`). The rule every
later page inherits: *a view reads the declared fields of one receipt and
returns a drawing.* Four decisions, each recorded with its reason — one
receipt per view; declared fields as paths in the same grammar `report.json`
cites with, so provenance and citation never need translating between
notations; no vector refusal, because the receipts carry none (checked, and
the asymmetry recorded so it does not read as an oversight); an absent field
raises rather than rendering `None`.

**The guard's third kind.** `contract.py` and `guard.py` were already neither
view nor transport. `CONTRACT_MODULES` names them and `unclassified_modules()`
must stay empty: the point is not the number of kinds but that no module can
arrive in the package without someone deciding which rules hold it.
`TRANSPORT_ALLOWLIST` is applied, never widened.

**The run index** (`runs.index_runs`). Transport, reusing
`server.verify_manifests` rather than writing a second digest checker. It
carries recorded values and tallies none — the view counts, because counting
recorded outcomes is drawing a measurement. Both tiers arrive in one shape; a
declared corpus size stays the sentence `"couldnt_check: declared, not
measured"` rather than being cast to a number; a run whose digests fail is
listed with the failing file named.

**A declared path that is never read is refused.** A view's `reads` is the
drawing's stated provenance, so declaring a path and not reading it overstates
what the drawing was built from — the accept-and-ignore shape 026 exists to
refuse, arriving one layer up. The assertion found **two** on the very run
that introduced it: `run_list` declared `report.kind`, which nothing read and
which `tier` already distinguishes, and `manifest.note`, which carries the
couldn't-check reason when a run has no MANIFEST at all and was being dropped
on the floor. The first was removed and the second wired through to the row,
so a run with no manifest now shows why rather than showing nothing. The
contract grew a tooth on first use.

**The fixture rebuild.** `report/report.json` `e75387ff` → `bbd8a8b0`,
`report/report.html` `e462a6b4` → `56dde95e`, MANIFEST updated. 2044 leaves
before, 2107 after, **0 numeric values changed**.

**The command and the pages.** `oneground ui [<runs-dir>]`, defaulting to
`./runs`, is the same server as `oneground lab` with the same token and the
same guard. One page serves both: `boot.js` asks `/api/check` which mode it is
in and loads `lab.js` or `ui.js`, rather than letting one fail and falling
back. `oneground lab <workdir>` is unchanged, and its page is untouched.

Four views, each under the extended contract: the run list, a run's finding,
the report with its evidence drawer, and two runs under the comparability
verdict — plus `RunProgressView` for a run that never reported. Endpoints
`/api/runs`, `/api/headline`, `/api/evidence` and `/api/compare`, each
resolving a run **by name against the index** rather than by joining a path,
so `?run=../../etc` is answered with *no run named …* and a parameter cannot
reach a directory the session never indexed.

**The evidence drawer.** Every claim gets an entry; every entry either
resolves to a file and field or names which of eight kinds it is, and only
`field` and `within` are navigable. Against the real arXiv report: 37 claims,
55 citations. The drawer carries the cited value and the value at the named
field and shows both, which is how it found the two citation defects that
`verdict.py` now refuses.

**`--demo`**, opening the published fixture's own run, downloading nothing,
and saying so — recorded above as a correction to the brief.

**The comparability verdict** at `oneground/comparability.py`, built here
because §2.2 says whichever position reaches it first builds it.

**Step 9, proved twice.** As a test, over a copied directory, digesting every
file before and after a session that visits every page of every run. And
against the developer's own browsing session on `runs/041-ui`: **63 files
before, 63 after, 0 added, 0 removed, 0 changed**, the whole file list
hashing to `b6a8f96052265a82…` on both sides, across four server restarts and
every endpoint fetched. All five MANIFESTs re-verified.

**Step 10, in a real browser, twice over.** My own pass at 1200 px and 500 px
found two defects that every endpoint had passed: `URLSearchParams({run: [a,
b]})` yields `run=a,b`, one parameter holding a comma, so the comparison page
never rendered; and two routes in flight at once each cleared the page and
appended to it, so the finding page drew its three counts twice. Neither was
visible over HTTP.

The developer's pass then found nine more, none of which a machine checking
`__uiState()` would have caught — an absolute path in the header (twice, and
worse at 500 px), an outcome column mixing two registers, a non-link styled
as a link, a header breaking mid-word, a couldn't-check rendered as raw
machine text, and form controls in dark-on-dark. The repair to the first was
structural: no drawing carries an absolute path any more, so no renderer can
leak one. The card layout at 500 px gained the label column it needed to
stop being a fallback.

**The report page was then rebuilt**, on the developer's reading, and the
defect is worth recording because it was the slice's own rule failing at the
last step. The first build rendered every citation of all 37 claims inline at
one density. Equal weight exists to stop a refusal being *quieter* than a
verdict; it does nothing when nothing on the page is quiet, and the two
couldn't-checks were invisible in a wall. The page now leads with the run's
own conclusion, lists one line per claim with its outcome mark, and opens
evidence only for the claim a reader asks about.

**`docs/UI.md`**, organised around *layout drifts, structure does not*, with
equal weight in the data, the no-alignment mark, the dash-is-not-a-zero rule
and the two-tallies rule written as instances of it rather than as a list to
memorise. `docs/LAB.md` keeps its name and gains a pointer; its security
section is cited rather than restated.

## Observed, not done

- **`site/teaser/` needs three changes**, routed to core. Sharpest first:
  `verdict.recommended.constraints[3].source` cites
  `verify.json:load.completed` on the page's **headline recommendation**,
  while the cell displays `119.1`, the achieved rate. In
  `site/teaser/data/values.json` (`deada30f4343864b`): 2 ×
  `verify.json:load.completed` → `verify.json:load.achieved_qps`, and 9 ×
  `report.json:costs[config].monthly_high` → the option's own config label.
  In `site/teaser/app.js:1032`, the hardcoded
  `'verify.json:load.completed · offered = '` → `load.achieved_qps`. No
  resulting digest is given, because Finding 2 means the export cannot
  currently be re-run against the fixture.
- **`tasks/011-cloud-verify-cost.report.md:139`** quotes the old citation. It
  is a dated record and is left alone.
- **Three dormant tests now run** because this branch has a local workdir:
  `receipts/test_provenance.py:174`, `verify/test_matched.py:1185` and
  `report/test_claims.py:421`. All three pass — and all three also pass
  against the *defective* report, which was verified by swapping it back in.
  Nothing rotted; what they never checked is Finding 1.

## Blocked on developer

None. Four findings are report-code work this task deliberately did not do
— **4** (a citation that cannot be reconstructed from what it names), **7**
(a machine token in the report's own prose) and **8** (one fact stated fifteen
times) in `oneground/report`, and **2** (the teaser's unverified provenance)
in `corpora/export_teaser_data.py` and `site/teaser/`, which is core's.
**Finding 5** is task 043's argument and was raised before this merge.
