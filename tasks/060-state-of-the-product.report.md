# Report: 060-state-of-the-product

## Repo state expected vs found

No specific repo state was assumed — this task is an inventory of `main`
as it stands at `bb4bf4c` (task 059's merge), read directly.

## What was done

**Method.** Every claim below was checked against the tree itself — source
files, test files, and the actual contents of `runs/` — not against
`tasks/*.report.md`, which are claims about a moment and were used, where
used at all, only to know where in the tree to look, never as evidence of
what is true now. Four research passes covered characterize/simulate/
verify/report; the lab and the interface's read and write halves;
chunking, index algorithms and reranking; and a two-directional diff
between `docs/*.md` and the tree. Proposals tier 1 and path 2, the bridge
exporter and importer, the library validator and multi-node fan-out were
checked directly, having been built or read in full this session.

For every capability: **Built** (a real implementation, cited), **Tests**
(what exercises it, and whether synthetic-only or real-data), **Real-data
run** (evidence in `runs/` of execution against a real fixture, a real
engine, or real infrastructure — as opposed to a unit test's temp
directory or a mocked call), **Machine locality** (whether every piece of
evidence for it traces to this one developer machine).

## Measurements

### The four core commands

**`characterize`** (`oneground/characterize.py`, 665 lines,
`_cmd_characterize` in `cli.py`). Tests: `test_characterize.py`, 14
functions, synthetic. Real-data: strong — `characterization.json` +
`build_info.json` present in ten-plus `runs/` directories
(`arxiv-150k-via-characterize`, `stackexchange-150k-via-characterize`,
`034-index-arxiv-150k`, `support-tickets-2026q3`, `acme-existing`, and
others), each citing a real vectors file by sha256. Machine locality:
**every one of these runs shows `environment_id: local:windows-amd64`**
— `characterize` itself has never been observed running anywhere but this
machine, including in `runs/032b-state-pod/`, whose `build_info.json` is
still local despite that run's later stages being pod-executed.

**`simulate`** (`oneground/simulate/__init__.py`, 882 lines). Tests:
`test_simulate.py`, 16 functions, synthetic; no separate fixture-based
test file. Real-data: `simulate.json`/`simulate_info.json` present in the
same `runs/` set, plus `044c/` sweep outputs loading real 150,000×768
vector arrays. Machine locality: **mixed** — `runs/032b-state-pod/`
carries `platform: Linux-6.8.0-124-generic...` and a real pod `host.txt`
(AMD EPYC 7352), confirming `simulate` has run on a pod at least once; the
`034-index-*` sweeps and `arxiv-150k-via-characterize` are local-only.

**`verify`** (`oneground/verify/__init__.py`, 1483 lines, plus
`load.py`, `runpod.py`, Docker Compose files for pgvector/qdrant). Tests:
`test_verify.py` (54) + `test_matched.py` (74) + `test_load_multi_node.py`
(2), mostly synthetic. Real-data: **an earlier version of this report
said `verify.json` existed for only `arxiv-smoke` and `acme-existing`,
and undercounted; corrected here after `runs/arxiv-150k-via-
characterize/verify.json` was found directly, not via the research pass
that missed it.** `verify.json` exists for **three** targets: `arxiv-
smoke` (local pgvector and qdrant containers), `acme-existing` (a
`target: existing` run against a local qdrant), and **`arxiv-150k-via-
characterize`** — a real, full-scale (150,000 vectors) run against
qdrant, `elapsed_seconds: 2637`, a real load test (200 qps achieved
sustained, real p50/p95/p99 latency), and a real calibration block
(measured recall 0.9992 against simulated 0.99755). **`verify.json` does
not exist for stackexchange-150k or sec-filings-10k** — confirmed absent
in both `stackexchange-150k-via-characterize` and `stackexchange-150k-
via-characterize-full150k`; sec-filings-10k has never gone through
`characterize`→`simulate`→`verify`→`report` as one pipeline at all, only
through chunking. Machine locality: the two smaller runs are local
containers; **`arxiv-150k-via-characterize/verify_info.json` shows
`platform: Linux-6.8.0-117-generic...`, `requirements_file.path:
/workspace/oneground/requirements.arxiv-150k.pod.yaml` — a real pod
run**, contradicting this report's own earlier, uncorrected claim that
`verify` had never run against a pod-hosted engine.

**`report`** (`oneground/report/__init__.py` + `claims.py` + `verdict.py`
+ `html.py`, ~4700 lines together). Tests: the largest surface of the
four, ~156 functions across ten files, mostly prose-invariant / property
tests. Real-data: `report.json`/`report.html` present for
`arxiv-150k-via-characterize`, `stackexchange-150k-via-characterize`,
`arxiv-smoke`, `support-tickets-2026q3`; the `arxiv-150k-via-
characterize` one is real and substantive — `summary: {couldnt_check: 2,
fails: 6, meets: 0, options: 8}`, `recommendation: null` (nothing met
every constraint) — computed from the real verify.json above, not a
stub. Machine locality: **two environment blocks, correctly kept apart**
(the same distinction `docs/PRACTICE.md`'s "four homes of one claim"
entry is about). `run_environment.environment_id` — the machine that
*wrote* `report.json` — is `local:windows-amd64` for every report.json
found, including this one: `report` itself has only ever executed
locally. But `environment.environment_id` — what the verdicts are
*about* — is the pod id (`1ombs4scr257a5`, `verify_target: runpod`) for
`arxiv-150k-via-characterize`, because that report's constraint verdicts
are judgements over the real pod-run verify data above. **This report's
first version conflated the two** — stating flatly that no report.json
had "ever been produced from a pod-origin chain," which is true of the
writing process and false of the data at least one report judged.

**CLI wiring**: confirmed. All four are real argparse subcommands in
`cli.py`, and `dispatchable_commands()` derives the guard-coverage list
from the parsers themselves, not a hand-maintained one — `oneground/
test_environment.py` asserts every dispatchable command is guarded or
explicitly exempted, which exercises these four as real dispatch targets.

### The lab and the interface

**The lab, read half** (`oneground lab <workdir>` — `oneground/lab/
server.py`, `~1485` lines, `LabServer`, guard-enforced via `guard.py`).
Tests: `test_server.py` (26) + `test_lab.py` + four more files; some
spawn real subprocesses, not just in-process calls. Real-data: `test_ui_
browser.py` drives a **real headless browser over CDP** against the real
`arxiv-150k` fixture (7 passed) — a genuine served-HTTP-then-rendered
session, not a mock. Machine locality: CDP browser discovery is
Windows-path-hardcoded; no evidence of execution elsewhere.

**Interface, read half** (`oneground ui`, many-runs mode — same
`LabServer`, `/api/runs`, `/api/headline`, `/api/compare`, `/api/jobs`
etc.). Tests exist (`test_ui_browser.py`'s directory-mode tests) but are
**all skipped on this checkout** — they require `runs/041-ui`, which is
not present. Real-data: not found; the tests that would prove it don't
run here. Machine locality: n/a (unproven).

**Interface, write half** (`/api/compose/write`, `/api/jobs/run`,
`/api/jobs/cancel`, forwarded to a separate `oneground/supervisor.py`
process — `CAPABILITY`/`WRITE_ENDPOINTS` share exactly two powers:
writing a requirements file, and running/stopping stages via the
supervisor; `pod up` is excluded by the same money boundary this
project's CLAUDE.md states). Tests: `test_supervisor.py` (19 functions,
real subprocess launches against a stub CLI) + `test_compose.py` (mostly
synthetic). Real-data: **not found** — no `supervisor.json` exists
anywhere in `runs/`, meaning there is no artifact evidence anyone has
ever enqueued a real job through this path against a real corpus.
Machine locality: n/a (unproven).

### Chunking, index algorithms, reranking

**Chunking** (`oneground/chunk/`, five modules, ~1400 lines). Tests: 86
functions across four files, all synthetic (zero references to
`fixtures/`). Real-data: `runs/chunking-sec-filings-10k/` — a full run,
all three strategies, against the real sec-filings-10k fixture. Machine
locality: **this one ran on a pod**, not locally — the session log's
paths are `/workspace/oneground`/`/workspace/sec-filings-10k`, the
RunPod network-volume convention, and no `local:windows-amd64` marker
appears in it.

**Index algorithms** (`oneground/models/indexes.py`, faiss-backed, four
algorithms × three families sharing one code path). Tests: 88 functions
across four files; `test_parameters.py` globs real `fixtures/*`. Real-data:
strong — `runs/034-index-arxiv-150k/` and `034-index-stackexchange-150k/`
show full 12-configuration sweeps (~50 minutes measured) against real
ground truth built from real fixture vectors; nprobe sweeps in `039-*`
too. Machine locality: **every index-algorithm run found is
`local:windows-amd64`**, including `032b-state-pod/`'s `build_info.json`
— that file specifically was not regenerated on the pod for that run,
only its state/host record was. (A different stage, `verify.json` in
`arxiv-150k-via-characterize`, does carry a real `runpod` environment id
— pod capability exists and has been used generally, just not observed
for an index-algorithm sweep specifically.)

**Reranking** (`oneground/models/rerank.py`, 212 lines — exact rescoring
plus a routing/candidate/ordering loss decomposition). Tests: 22
functions. Real-data: `runs/035-rerank-arxiv-150k.json` and the
stackexchange equivalent — real 28-row sweeps, 2,000 queries, against the
real fixtures. Machine locality: **not found either way** — neither
output file carries an `environment_id` field at all.

### Proposals tier 1, path 2, the bridge, the library, multi-node

**Proposals tier 1** (`oneground/proposals/propose.py` + `card.py` +
`prediction.py` + `verdict.py`, task 028). Tests: extensive, in `test_
propose.py`/`test_proposals.py`. Real-data: confirmed directly —
`runs/arxiv-150k-via-characterize/proposals/` holds two real cards
(`semantic_sharded_epsilon-0.1-to-0.2/`, `semantic_sharded_probe-1-to-2/
`), each a real measured proposal against the real arxiv-150k fixture.
Machine locality: both cards' `environment.environment_id` is
`local:windows-amd64` — tier 1 has only ever run on this machine.

**Proposals path 2** (`oneground/proposals/translate.py`, task 059, this
session). Tests: 14, against a real local HTTP server (genuine sockets),
but with a **scripted, fake model response** — no real LLM was called.
Real-data: none — no `translation_card.json` or `policy.yaml` exists
anywhere in `runs/`; every exercise of this module has been inside a
test's own temp directory, against a synthetic `characterization.json`/
`manifest.yaml`, not a real `characterize`/`report` output. Machine
locality: entirely this machine, entirely this session.

**Bridge exporter** (`oneground/bridge/export.py` + `query_subset.py`,
task 051). Tests: real round-trip tests (synthetic corpus). Real-data:
**none found** — no `vdbbench_card.json` and no `.parquet` file exists
anywhere under `runs/`. The exporter has never been run against a real
fixture's real vectors; every test of it uses a small synthetic corpus
built in the test file itself. Machine locality: n/a (never run outside
tests).

**Bridge importer** (`oneground/bridge/import_result.py`, task 055, this
session). Tests: 18, against fixtures shaped from VectorDBBench 2.0.0's
own real shipped example result files (read as reference, not executed)
— not against a file the exporter above ever actually produced, since
the exporter has never run for real. Real-data: none. Machine locality:
this machine, this session.

**Library card validator** (`oneground/library/card_schema.py`, task
058, this session). Tests: 13, entirely against hand-built synthetic card
dicts — no code exists yet to build a real library card from a real
proposal, so no real card has ever been validated. Real-data: none.
Machine locality: this machine, this session.

**Multi-node fan-out** (`oneground/verify/load.py::run_load_per_node`,
task 057, this session). Tests: 2, one exercising a **real three-node
Qdrant cluster** (real Docker containers, real network, real measured
qps/latency spread) — but on 500 synthetic random vectors, not a real
fixture corpus, and the cluster was created, exercised and torn down
within this task. Real-data (fixture-scale): none. Machine locality: this
machine, this session — Docker Desktop and WSL2 were installed on this
machine specifically to run this test.

### What docs describe that the tree does not contain

1. **`docs/EXTERNAL_RUN.md`** presents `pip install oneground` plus
   downloading `arxiv-150k-v1.tgz` "from the release page" as a plain,
   working instruction for an outside verifier, with no caveat about
   which release. `docs/RELEASE.md` itself records that only `0.1.0-
   preview` was ever published — a later, dated `0.1.0` was built
   (`dist/oneground-0.1.0-py3-none-any.whl` exists locally) and
   deliberately withheld, its tag deleted. Confirmed: `git tag` shows
   only `v0.1.0-preview`. A reader following `EXTERNAL_RUN.md` today has
   no way to know, from that document alone, that a newer build exists
   and was intentionally not published.
2. **`docs/MULTI_NODE.md`** §3 already states this about itself (it is a
   self-flagged position paper), but worth naming here too: it documents
   that `describe()`'s `nodes` field never worked, contradicting what an
   older reader of `docs/ADAPTERS.md` alone (which does not mention the
   defect) would assume the field does. Fixed since, as task 056 — the
   doc was correct at the moment it was written and is not a current
   mismatch, listed for completeness.

Checked and ruled out as false positives: `oneground/receipts/cites.py`
(named in `docs/PRACTICE.md` §5, but the doc narrates the exact move that
produced it — not a surprise); every other cross-checked path in
ADAPTERS, BRIDGE, CLAIMS, CHUNKING, INTAKE, UI resolved to real, matching
code.

### What the tree contains that no doc describes

No substantial, tested, undocumented capability at the package level was
found — this codebase's own docs (`PRACTICE.md`, `STATE.md` especially)
narrate implementation history in enough detail that most candidates
checked out as documented by concept even where not by exact module path
(`oneground/truth/exact_knn`, `oneground/adapters/coverage_cli.py`,
`oneground/chunk/selfretrieval.py`). One item outside strict scope: the
top-level `policies/` directory (named in `CLAUDE.md`'s own repository
layout as holding "small policy functions with tests") contains only a
README — no actual policy modules — but since no `docs/*.md` file
mentions `policies/` at all, this is not a doc/tree mismatch by the
letter of the question; noted rather than counted.

## Addendum — three follow-up questions, checked directly

**1. Corrected above, in place.** The original version of this report
undercounted `verify.json`: it exists for `arxiv-150k` at full scale, on
a real pod, and the report's own earlier claim that `report` had never
judged pod-origin data was wrong in the same way — both corrected in
the `verify`/`report` entries above rather than left standing beside a
correction. The accurate shape: `verify`/`report` have real output for
three targets (`arxiv-smoke`, `acme-existing`, `arxiv-150k`), never for
stackexchange-150k or sec-filings-10k.

**2. `supervisor.json` and the durable job record.** Checked precisely,
not just for the address file. `supervisor.json`
(`oneground/supervisor.py`'s `ADDRESS_NAME`) is deleted on a clean
`stop()` by design — its absence alone would not mean no job ever ran,
only that nothing is running *now*. The durable record is a separate
file, `jobs.json` (`oneground/jobs.py::JOBS_NAME`), written into
`<runs_dir>/jobs.json`, plus per-job logs under `<runs_dir>/logs/`.
**Neither exists anywhere on this filesystem** — `find` across the whole
checkout, not just `runs/`, returns nothing for `jobs.json` or a
`runs/*/logs/` directory. So the finding is stronger than "no supervisor
is currently running": no job this supervisor ever ran, however it
ended, has left a durable trace anywhere in this checkout. Whatever was
watched running in a browser either wrote into a `runs_dir` outside this
repository entirely, or its record was removed afterward; the tree
itself does not distinguish those two.

**3. The `runs/032b-state-pod` receipt disagreement.** `build_info.json`
is not wrong. Checked three independent ways: its `platform` field
(`Windows-11-10.0.26200-SP0`) is a raw `platform.platform()` read, not a
classification that could misfire the way `environment_id` alone could;
its `requirements_file.path` cites `tasks/scratch/020-ref-arxiv.yaml`, a
real, older, local-only requirements file from task 020; and its
`built_at` (2026-09-15T13:06:21Z) is **four days before** this
directory's own `simulate_info.json.run_at` (2026-09-19T16:17:20Z) —
which itself is genuinely pod-executed (`platform: Linux-6.8.0-124-
generic...`, `cuda_device_name: NVIDIA RTX PRO 4000 Blackwell`,
`requirements_file.path: /workspace/oneground/requirements.arxiv-150k.
determinism.032b.pod.yaml`), matching `host.txt`'s own AMD EPYC dump.

`sample_ids.json` is **byte-identical** (same sha256) between `runs/032b-
state-local/` and `runs/032b-state-pod/` — the same corpus draw underlies
both — while `characterization.json` differs between them (different
sha256, `032b-state-local`'s own `built_at` is 2026-09-19, same day as
the pod simulate run). The shape this evidence supports: `characterize`
for this workdir was run once, locally, on 2026-09-15 (reusing task
020's own reference build rather than a fresh one), and that artifact was
carried into `032b-state-pod/` before `simulate` ran fresh, on a real
pod, four days later. `characterize` and `simulate` are two different
receipts about two different operations that happened in two different
places at two different times — not one receipt lying about itself. The
directory's name is the only imprecise thing in it: "state-pod" names
the stage that ran there last, not everything the directory holds. No
provenance field was found recording a false machine.

## Verification

Not applicable in the usual sense — this report is itself the
verification pass. Every real-data and machine-locality claim above cites
a specific `runs/` path or test file checked directly; guard, identifier
scan, full suite and `site/teaser/` diff for the files this report
actually changed (`docs/PRACTICE.md`'s new entry, this report) are below.

## Observed, not done

This report does not judge any of the above — no capability is flagged
as a problem, and no order or priority is suggested, per instruction.

## Repo now contains

New:

- `tasks/060-state-of-the-product.report.md` — this file

Changed:

- `docs/PRACTICE.md` — a new §2 entry (14): a check's scope encoded a
  tier/path conflation that was correct by omission for as long as
  nothing existed on the axis it blurred; task 059 arriving on that axis
  is what exposed it, the same conflation that also produced the
  stock-take's own path-2/tier-2 misreading days earlier.

## Blocked on developer

Nothing. Committing, pushing to `task-060`, and merging into `main` once
its checks are green, per standing instruction.
