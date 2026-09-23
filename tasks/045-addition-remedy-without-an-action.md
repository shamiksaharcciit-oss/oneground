# Addition to 045 — two couldn't-check claims that name an obstacle and no action

*Found in task 044, which did not cause it and does not own it. For the
interface stream to fold into `tasks/045-report-code-findings.md`.*

## What fails

`oneground/lab/test_evidence.py::test_every_couldnt_check_claim_carries_a_remedy`
fails on `runs/arxiv-150k-via-characterize`, claims `[33, 34]`. Both are
`to_resolve` entries sourced from
`verify_info.json:engine_facts.index_params`, and both read:

> *"To decide latency_p95: this configuration was not the one verified — the
> verify run built hnsw in a single namespace, which is not a hash_sharded
> deployment. This row's architecture was simulated and never built, so a
> measurement of the built index says nothing about it."*

(The second is the same sentence for `qps`.)

## Why it matters more than a failing test

The sentence is **correct, thorough, and unactionable**. It explains the
obstacle in detail and never says what would remove it. The couldn't-check
rule exists so a reader learns what to do next, and the remedy is the only
part of a couldn't-check a reader can act on — so this is the rule failing at
precisely the point where it carries all of its value. A reason without a
remedy ends in nothing to do, which is the test's own docstring.

## 1. Check the routing before writing any text

**Do this first, and do not write a sentence until it is answered.**

`report/claims.py:how_to_resolve` already returns a remedy for the
`not_verifiable_here` and `coverage_unresolved` kinds:

```python
remedy = getattr(verdict, "remedy", "")
kind = getattr(verdict, "couldnt_check_kind", None)
if remedy and kind in ("not_verifiable_here", "coverage_unresolved"):
    return f"To decide {name}: {remedy}."
```

These two claims describe exactly a not-verifiable-here situation — the
configuration was never built — and they came out of a different branch. So
the likely defect is **a missing `couldnt_check_kind` or `remedy` on the
verdict**, not missing prose in the function.

If that is what it is, **a hand-written sentence would have papered over a
routing fault with better prose**: the claim would read well, the test would
pass, and every other verdict taking the same path would keep arriving
unrouted. Fix the routing and the sentence follows; write the sentence and the
routing stays broken and invisible.

## 2. The action, once the routing is understood

> **To decide `latency_p95`: verify this configuration, built as
> `hash_sharded`, on a real engine.**

That is the missing half. The obstacle is that the verify run built `hnsw` in
a single namespace; the remedy is a verify run whose deployment matches the
row's architecture. Same sentence for `qps`.

Whether this becomes a `remedy` string on the verdict (likely, per item 1) or
a branch in `how_to_resolve` depends on what item 1 finds.

## 3. The test has not really been run

`_draw` skips an untracked workdir when it is absent, and
`runs/arxiv-150k-via-characterize` is local and untracked. A fresh clone skips
the case entirely.

**A test green in CI and red only where an untracked workdir happens to exist
is a test that has not really been run.** It is the same shape as the
regression fixture this stream has just made tracked: a check whose subject
is not in the repository is a check whose result depends on who is running it.

So this addition is also a request for **a tracked workdir that exercises the
not-verifiable-here path**, so the case fails for everyone or for no one. The
pre-fix report fixture already in `lab/testdata/` is the precedent.

One related fact, for dating the defect rather than for blame:
`test_evidence.py` arrived with 041, so task 036's full-suite runs were green
on the same machine with the same run directory — the test post-dates the
workdir, not the other way round.

## Established, not assumed

Task 044 did not cause it: the failure reproduces **identically with 044's
changes stashed**, and 044 writes into no artifact that a claim is built from.
044 merged onto it knowingly rather than holding a clean change hostage to
it — recorded in that task's merge report.
