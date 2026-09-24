# Report: 049-the-checked-set

## Repo state expected vs found

Expected `main` at `fc6fff1` (task 047's merge) with the accepted brief
and nothing in `oneground/intake/` changed since. Found exactly that.

## What was done

Four rulings, taken in order.

### 1. `nearest_fixture` and `queries.source` were the rule finding two
defects, not two disagreements

Both are closed-by-definition domains the rule says should be checked and
were not. Fixed rather than explained away, in `oneground/intake/__init__.py`:

- **`corpus.declared.nearest_fixture`** — `auto` and `none` are the two
  fixed sentinels `analogy.choose()` itself matches on; anything else must
  now name a fixture that is actually built. The known set is **read from
  the fixtures directory at load time** (`analogy.load_fixture_analogies()`),
  not hardcoded — a static tuple here would have gone stale the first time a
  fixture is added, which is the exact defect this task exists to stop
  reproducing. `intake` gained its first dependency on `analogy` for this
  (an absolute import, `from oneground import analogy` — see the guard note
  under Verification).
- **`corpus.sample.queries.source`** — `logs | written | synthetic`, a
  static closed set (`QUERY_SOURCES`), the same shape as `text_length`.
  Previously validated by nothing and, per task 048, read by nothing either.

Both are also now declared in `fields.py:FIELDS`, `nearest_fixture` **without**
a `choices=` tuple — the same reasoning: a static choice list would be
exactly as stale as a hardcoded validation.

**Worth naming rather than leaving implicit: the fix declining to
reproduce the defect it repairs.** This is the third time in this task's
own lineage the same second-order error was in reach and avoided rather
than committed — task 047's ruling against hand-editing `fields.py` from
"twenty-five" to "twenty-six," this task's own `count_refusals()` in place
of a fourth stale citation, and now a validation for `nearest_fixture`
that would itself have been a hardcoded list going stale on the next
fixture built. The care is invisible exactly when it works: a static
`("auto", "arxiv-150k", "stackexchange-150k", "none")` tuple would have
passed every test written against today's fixtures and been silently wrong
the day a fifth one was added — the same shape of failure as the count
that sat wrong for two tasks before anyone measured it.

### 2. `corpus_type` vs. `text_length`: the reason is good; rule 3 is widened

Quoted in full, from `oneground/intake/__init__.py`'s own comment: *"Values
`corpus_type` is matched on. Not a closed set for the user -- an
unrecognised type is carried through and simply matches no fixture, which
is an honest 'no analogy' rather than a wrong one."*

**The reason is good.** `corpus_type` and `text_length` feed the identical
mechanism — one `declared.get(...)` against `analogy.get(...)` comparison
each in `analogy.py`'s scoring — and are still rightly treated oppositely,
because the axis the comment is drawing is not about consumption, it is
about the field's own domain: `corpus_type` is open **by concept** (new
kinds of corpus are always a legitimate answer the fixture set has not met
yet); `text_length` is closed **by definition** (the example file's own
words are "short (<300 chars) | medium | long" — three defined buckets,
nothing a fourth word could name that one of them does not already cover).

Rule 3 was incomplete because it only had this distinction as a fact about
one field. It now states the axis generally (`fields.py`'s module
docstring, component 3), and extends it to `embedding_model` — same
mechanism, same reasoning, previously unstated anywhere — which sits beside
`corpus_type` in `fields.py:OPEN_DOMAIN` rather than as a third
disagreement.

**This is the rule earning its keep twice, not once.** Open-by-concept
versus closed-by-definition was a fact the code already knew, but knew
about exactly one field, in a comment attached to that field alone.
Stating it as a general clause of rule 3 is what let it reach
`embedding_model` — a field nobody was looking at, that nobody proposed as
a case, that fell under the same reasoning purely because the reasoning
was now general rather than local. A summary of the current table could
not have done this: it would have listed `corpus_type` as an exception and
stopped, because a list has no shape to extend past the case that
prompted it. A rule that widens because one case tested it, and then on
its own finds a third case nobody went looking for, is what distinguishes
a rule from a summary of today's table — which is the whole argument this
task was written to make, landing on the field it least expected to.

### 3. Component 4 has three members, declared as one worked example

`ANNOTATIONS` in `fields.py` now holds exactly three cases, not six-plus-
a-flag: the two in-scope `kind:` fields (`corpus.sample.kind`,
`corpus.declared.kind` — the other four `kind:` labels are already fully
explained by rule 1 alone, since their blocks are out of scope; they were
never evidence for rule 4 specifically, and counting them as such would
have overclaimed), the three `sampling.*` fields the example file's own
comment calls *"recorded, not enforced,"* and **`run.mode`, declared as the
rule's own first exception** rather than left a flag: nothing reads it —
`Requirements.tier` is computed from which blocks are present
(`1 if self.sample else (2 if self.declared else None)`), never from this
field — and it is named in `ANNOTATIONS` with that reason, the worked
example of what the brief's sixth item asked for: an exception with a
stated reason, in the same table `OUTSIDE_THE_TABLE` already models,
rather than a silent gap.

### 4. The count is derived; the four citations point at the derivation

`fields.py:count_refusals()` parses `intake/__init__.py` with `ast` and
counts `raise RequirementsError` sites — **28** today (26 at task 047's
tip, +2 for this task's two new refusals). All four places that said
"twenty-five" (`fields.py` twice, `docs/PRACTICE.md`, `docs/UI.md` twice)
now cite `count_refusals()` or `len(OUTSIDE_THE_TABLE)` instead of a digit,
per the ruling: not hand-edited to a fresher number.

### The coverage test, both directions, over all 74

`oneground/intake/test_checked_set.py`. `fields.checked_reason(field)` is
the rule made callable — `(True, reason)` when the field is in `BY_NAME`,
`(False, reason)` when rule 1, 3 or 4 places it outside, `(None, None)`
when nothing does. The main test walks every current leaf of
`requirements.example.yaml` and fails on any `(None, None)` or any
disagreement between the rule's verdict and `BY_NAME`'s actual membership.
A companion test proves rule 1 alone accounts for 44; another proves a
field the rule cannot place fails rather than passing by silence — and I
confirmed this in-process (not merely by inspection) by removing
`run.mode` from `ANNOTATIONS` and calling the test function directly: it
failed, naming `run.mode`, before I restored the entry.

The full accounting, all 74:

| | count | rule |
|---|---:|---|
| checked (`BY_NAME`) | 18 | rules 1-3, positive |
| out of scope | 44 | rule 1 |
| descriptive annotation | 6 | rule 4 |
| deferred (needs a file open) | 4 | rule 3 |
| open domain | 2 | rule 3 |
| **total** | **74** | |

## Measurements

- `fields.count_refusals()`: **28** (was 26 before this task's two new
  refusals; 25 at task-045's tip).
- `len(fields.BY_NAME)`: **23** (21 before this task).
- `len(fields.OUTSIDE_THE_TABLE)`: **11**, unchanged.
- Leaves in `requirements.example.yaml`: **74**, unchanged, pinned by
  `test_the_example_file_has_74_leaves`.
- Rule 1 alone (`constraints`/`simulate`/`verify`/`report`): **44** of 74.

## Verification

Full suite: **1786 passed, 41 skipped**, `.venv\Scripts\python.exe -m
pytest -q`. (1785 on the first run, which caught a real defect before this
was reported — see below — then 1786 after the fix and the nine new tests
in `test_checked_set.py` landed; net of the fixed run vs. task 047's 1777:
+9 new tests here.)

The pinned-environment guard: unaffected (`test_environment.py` not
touched).

The tracked-tree identifier scan: 572 tracked paths before staging the two
new files; re-confirmed 0 findings after (below).

**A guard failure, caught before commit, not routed around.**
`intake`'s first import of `analogy` — written initially as `from .. import
analogy`, a relative import — failed
`oneground/lab/test_server.py::test_everything_the_server_imports_passes_
the_guard` with `[('oneground/intake/__init__.py', [(27, 'import', '..')])]`.
Traced to the cause rather than silenced: the test resolves a module's
package for relative-import checking as `name.rpartition(".")[0]`, which is
correct for an ordinary module (`oneground.pod.cli` → `oneground.pod`) and
**wrong for an `__init__.py`**, where `__package__` equals the module's own
full name (`oneground.intake`, not `oneground`). Confirmed directly:
`importlib.util.resolve_name("..analogy", "oneground.intake")` correctly
gives `oneground.analogy`; `resolve_name("..analogy", "oneground")` — what
the test actually computes — raises `ImportError`, which
`transport_violations` reports as an `import` violation rather than
resolving it. `analogy` is not in `guard.MEASURING`; the import is not
actually forbidden. Fixed by switching to an absolute import,
`from oneground import analogy`, which needs no relative resolution and
sidesteps the bug rather than exploiting it. **Not fixed: the test
harness's package-resolution heuristic itself**, which is wrong for any
`__init__.py` using a relative import — none had, until this task, so
nothing had exercised it. **Worth its own sentence: a guard check that
resolves a relative import's package wrongly for `__init__.py` files has
never been exercised on one — a coverage claim inside the guard that
exists to check coverage claims, of exactly the shape this task's own
subject is.** Named under Observed, not done, and left there deliberately
— it is its own small, scopeable task, not something to fold into this
one on the way past it.

## Observed, not done

**`oneground/lab/test_server.py`'s guard-check package resolution
(`name.rpartition(".")[0] or name`) is wrong for `__init__.py` modules.**
It produces a false `import` violation for any relative import inside one,
because `__package__` for an `__init__.py` is its own full dotted name, not
its parent's. Worked around here by using an absolute import in `intake`;
the harness itself is untouched, and the next `__init__.py` to use a
relative import will hit the same false positive.

**`docs/UI.md`'s "the other 53"** (a `requirements.example.yaml` leaf count
against a stale `21`-field denominator, predating task 046's own precise
58/74 measurement) is now doubly stale — the real gap was 58 before this
task and is 56 after it — and was not part of the four citations this
brief named. Not touched.

**The 21-still-unread-but-now-partly-fixed set.** Task 048 counted 21 of
the (then) 58 unchecked fields as read by something. Two of those 21 —
`nearest_fixture`, `corpus_type` — are addressed here (one validated, one
explained); the other 19 are untouched and remain exactly task 048's
finding: read, not validated, not this task's subject.

## Repo now contains

Changed:

- `oneground/intake/__init__.py` — `nearest_fixture` and `queries.source`
  validated; `QUERY_SOURCES` added beside `DECLARED_TEXT_LENGTHS`, with
  its comment widened to state the closed-by-definition/open-by-concept
  axis generally; `from oneground import analogy`
- `oneground/intake/fields.py` — `OUT_OF_SCOPE_BLOCKS`, `ANNOTATIONS`,
  `DEFERRED`, `OPEN_DOMAIN`, `count_refusals()`, `checked_reason()`; two
  new `Param` entries (`queries.source`, `nearest_fixture`); module
  docstring gains "What intake validates, and why," the four-component
  rule; both "twenty-five" citations now derive
- `docs/PRACTICE.md` — the `intake.RequirementsError` instance in §7.4.1
  no longer states a count; cites `count_refusals()` and names task 047 as
  what it caught
- `docs/UI.md` — both "twenty-five"/"25" citations now point at
  `count_refusals()`/`OUTSIDE_THE_TABLE` instead of a digit
- `oneground/intake/test_checked_set.py` — new: the coverage test, both
  directions, over all 74 current leaves; mutation tests for the two new
  refusals; the completeness mutant, verified in-process
- `tasks/049-the-checked-set.report.md` — this file (replaces the
  checkpoint version)

Not committed: sitting in the working tree, per "I will rule on the whole
before it merges."

## Blocked on developer

**The whole of this task**, per your own framing. Recount, rule, the two
fixes, the widened rule 3, `run.mode`'s declared exception, the derived
citations, and the coverage test are all here together. Ready to commit
and push to `task-049` for review; holding before any merge into `main`
until you've ruled on it.
