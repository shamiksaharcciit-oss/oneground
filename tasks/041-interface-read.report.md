# Report: 041-interface-read

*In progress. The findings below were produced while building and are
recorded as they were found, rather than held to the end.*

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

None.
