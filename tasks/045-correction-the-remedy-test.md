# Correction to 045 — the remedy test is a stale artifact, not a failing check

*From task 044b, correcting an attribution made in the 044 merge report and in
the addition that preceded it. For the interface stream.*

## What was said, and what is true

The 044 merge report recorded
`test_every_couldnt_check_claim_carries_a_remedy` as a **pre-existing failure
of working code**, attributed to two claims that name an obstacle and no
action.

**That attribution is retired.** The code is fixed. The failure is a stale
artifact:

| | |
|---|---|
| the fix | `951450f`, 23 September — `verdict.py` now sets `couldnt_check_kind`, 6 references |
| the artifact under test | `runs/arxiv-150k-via-characterize/report.json`, last written **14 September** |

The test reads claims out of a `report.json` on disk. **Fixing the writer does
not rewrite files already written.** So this is not a failing check of working
code — it is a check of an artifact produced by code that no longer exists,
nine days stale, on the one machine that holds it.

The stream's own finding stands and is larger than the correction: all 29
couldn't-check verdicts set neither field, several carrying the action inside
`reason` — the right words in the wrong field, which reads as done.

## This strengthens the tracked-case requirement

The addition already asked for a tracked workdir exercising the
not-verifiable-here path, on the grounds that a test green in CI and red only
where an untracked workdir happens to exist is a test that has not really been
run.

The correction makes that sharper rather than softer. **The test is not merely
running on an arbitrary machine's data — it is running on data that predates
the fix it is checking.** Three failure modes in one:

1. On a fresh clone it **skips**, so the routing fix has no test that
   demonstrates it.
2. On this machine it **fails**, against an artifact the fix could not have
   touched.
3. There is **no configuration in which it currently passes because the code
   is right** — which means the fix shipped without a check that can confirm
   it.

A tracked case fixes all three at once: it would have failed before `951450f`,
pass after it, and do both identically everywhere.

## What not to do

**Do not regenerate `runs/arxiv-150k-via-characterize`.** It is
`test_evidence`'s `TIER1` subject and several other tests read it;
regenerating changes what they see, and it would also make the failure
disappear without anything having been demonstrated — the worst of both, since
the routing fix would still have no test.

The fix is a tracked case, not a fresh artifact.
