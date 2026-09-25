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
(2), mostly synthetic. Real-data: `verify.json` exists for **only two**
targets — `runs/arxiv-smoke/` (the small smoke fixture, against local
pgvector and qdrant containers) and `runs/acme-existing/` (a `target:
existing` run against a local qdrant). **No `verify.json` exists anywhere
for arxiv-150k, stackexchange-150k or sec-filings-10k at full scale.**
Machine locality: both real runs found are local containers
(`localhost`); no evidence `verify` has ever run against a pod-hosted
engine, despite `runpod.py` existing and being tested.

**`report`** (`oneground/report/__init__.py` + `claims.py` + `verdict.py`
+ `html.py`, ~4700 lines together). Tests: the largest surface of the
four, ~156 functions across ten files, mostly prose-invariant / property
tests. Real-data: `report.json`/`report.html` present for
`arxiv-150k-via-characterize`, `stackexchange-150k-via-characterize`,
`arxiv-smoke`, `support-tickets-2026q3`; the `arxiv-smoke` one shows a
real calibration block (measured vs. simulated pgvector recall, deviation
0.0), i.e. it consumed a real verify.json, not a synthetic one. Machine
locality: every `report.json`-producing run traces to a local `build_
info.json`; none has ever been produced from a pod-origin chain.

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
