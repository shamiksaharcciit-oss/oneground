# Report: 042-family-conformance

> **Addendum, task 042b.** Finding 2 is **fixed**: `semantic_sharded` now
> refuses `centroids > len(vectors)` with `indexes.IndexTooSmall`, raised
> before the `context` shortcut so the same configuration cannot be refused
> from one caller and accepted from another. That family now passes all eight
> decidable checks, and the suite's totals below become **23 passes, 1 fail,
> 3 couldn't-check**. Finding 1 (`hash_sharded`) is left open on purpose, for
> its own decision. The measurements below are as first taken and are not
> rewritten. Section 4.1 of `docs/FAMILIES.md` now carries the three
> suite-was-wrong findings as a warning to whoever extends it, rather than
> leaving them only here.

## Repo state expected vs found

Expected, and found:

- Three registered families in `oneground/models/`, each implementing the
  protocol in `base.py`. Found.
- An adapter conformance suite to take the shape from,
  `oneground/adapters/conformance.py`, with its `main()` reporting per engine.
  Found.
- `propose`'s *requires a family that does not exist* refusal, in
  `oneground/proposals/policy.py:NO_SCOPE`. Found.
- `docs/CHARTER.md` naming a family as a contribution unit, in Phase 3b's
  neighbourhood. Found.

**Two things the brief did not say, and both changed the work:**

1. **A family conformance file already exists** —
   `oneground/models/test_conformance.py`, 27 tests parameterised over the
   registry, covering configs, build determinism, search shape, `ceiling >=
   recall`, footprint sanity and the state contract. So the gap the brief
   names is narrower than "families have no conformance suite": what was
   missing is a **command** a contributor can run against an unregistered
   file, per-check reporting with reasons, and four requirements nobody had
   written down. The new module does not replace that file, and both run.
2. **`ceiling()` is not the protocol's only unlisted method.** The protocol
   is six methods, not the four `CONTRIBUTING.md` lists — `configs` and
   `state` are missing there. Reported below, not fixed.

## What was done

- `oneground/models/conformance.py` — the suite: nine checks, one command,
  `--module` for an unregistered family.
- `examples/random_sharded/` — the worked example, deliberately bad,
  unregistered.
- `docs/FAMILIES.md` — the contributor document.
- `oneground/models/test_family_conformance.py` — 14 tests, mostly mutants.
- `oneground/cli.py` — `oneground models conformance` wired and declared
  unguarded, with why.
- `oneground/proposals/policy.py` — the refusal names the document.
- `docs/CHARTER.md` — Phase 3b2: what the contribution unit concretely is,
  and that none has come from outside.

Nothing was weakened. No gate, threshold, tolerance or seed was changed, and
**no shipped family was modified** — the two that fail a check are reported
as findings, per the brief.

## Measurements

### The suite against the three shipped families

`oneground models conformance`, synthetic 1500 × 32 corpus, 40 queries, k=10.
Full output: `tasks/scratch/042-conformance-shipped.log`.

| family | passes | fails | couldn't-check |
|---|---|---|---|
| `hash_sharded` | 7 | **1** | 1 |
| `semantic_sharded` | 7 | **1** | 1 |
| `single_node_hnsw` | **8** | 0 | 1 |
| **total** | 22 | **2** | 3 |

The three couldn't-checks are the same one: the cross-environment half of the
state contract, which one machine cannot answer.

### Finding 1 — `hash_sharded` accepts more shards than it has vectors

Reproduced without the suite
(`tasks/scratch/042-verify-the-two-findings.py`), 1500 vectors:

```
config accepted:  hash_sharded[M=16,efSearch=64,shards=1501]
build succeeded.
  footprint.shards  =  960        (the artifact)
  footprint.fanout  = 1501.0      (what the config asked for)
  label says        = 1501
```

`build` skips empty shards (`if len(member) == 0: continue`), so a
configuration asking for more regions than there are vectors produces a
**smaller** partition than its own label names, and `footprint()` then reports
**two mutually inconsistent numbers for one build**: 960 shards with a fan-out
of 1501. A row carrying both would price a query at 1501 shard searches over a
960-shard index. Nothing refuses it and nothing warns.

The protocol requirement violated: *an impossible configuration is refused
with a `ParameterError` naming what is wrong.*

### Finding 2 — `semantic_sharded` lets faiss raise where a refusal belongs

```
config accepted:  semantic_sharded[M=16,centroids=1501,efSearch=64,epsilon=0.2,probe=2]
build raised:     RuntimeError  (faiss::Clustering::train_encoded)
```

A `ParameterError` is dropped as one row and reported (task 034's rule). A
`RuntimeError` **stops the sweep**. On the arxiv-150k sweep that is up to five
hours of measured rows lost to one unbuildable configuration.

The refusal it needs already exists three call-frames away and is the control
in the same script:

```
single_node_hnsw[index=ivf,nlist=1501,nprobe=4]
  -> ParameterError: index=ivf asks for nlist=1501 cells over 1500 vector(s);
     faiss cannot train more cells than it has points. Lower ...
```

`indexes.build` refuses over-large `nlist` with exactly the message this
wants. The two families simply do not apply the same rule to their own
partition knobs.

### The worked example, and its measured inferiority

`examples/random_sharded` passes all eight decidable checks
(`tasks/scratch/042-conformance-example.log`). Against `hash_sharded` on the
suite's corpus (`tasks/scratch/042-random-vs-hash.py`):

| family | shards | probe | recall@10 | ceiling@10 | routing loss | fanout |
|---|---|---|---|---|---|---|
| hash | 4 | all | 1.0000 | 1.0000 | 0.0000 | 4.0 |
| random | 4 | 1 | 0.2750 | 0.2750 | 0.7250 | 1.0 |
| random | 4 | 2 | 0.5175 | 0.5175 | 0.4825 | 2.0 |
| hash | 8 | all | 1.0000 | 1.0000 | 0.0000 | 8.0 |
| random | 8 | 1 | 0.1525 | 0.1525 | 0.8475 | 1.0 |
| random | 8 | 2 | 0.2900 | 0.2900 | 0.7100 | 2.0 |

Two things worth more than the example itself:

**Its ceiling tracks `probe/shards` to within 0.03** — 0.2750 against 0.25,
0.5175 against 0.50, 0.1525 against 0.125. A random partition probing P of N
reaches a random P/N of the corpus, which is what its docstring claims and
what a test now asserts.

**Recall equals ceiling in every row**, so index loss is exactly zero and
every point of loss is routing. It is the first family in this suite with a
non-trivial routing loss at all: all three shipped families reach everything
at every configuration the suite builds, so **none of them can demonstrate the
decomposition the protocol exists to produce.** That is the example's real
job.

**And it is not simply worse.** It loses on recall (0.2900 against 1.0000) at
**lower fan-out** (2 against 8). Quoting only the recall gap would be the
one-scale defect task 039b just wrote a rule about, so both are here.

### The suite's own false findings, and how they were caught

Three of its first results were wrong. All three are recorded because a gate
whose early errors are invisible is a gate nobody can trust.

| what it reported | why it was false | fix |
|---|---|---|
| `candidates` is a knob that does nothing, in all three families | it is read only when `rerank=exact`, which the covering grid never set | keys gated by `belongs_to` are reached by a constructed configuration, and reported as *uncovered* rather than *dead* when they cannot be |
| `M` and `efSearch` are unreachable, in every family | `index` **elides at its default** (034's no-re-label rule), so `params.get("index")` is `None` in every HNSW config | belonging is decided by `base._belonging_problem`, the validator's own function, instead of reimplemented |
| `single_node_hnsw` passes *refusals, not crashes* | `nlist` on an HNSW config is refused **for belonging**, which says nothing about size — it passed without testing anything | the check picks a configuration the knob belongs to |

The second is the same trap as reading 034's reference rows by index name, and
the third is a check passing for the wrong reason, which is worse than a check
failing.

### Cost

The suite runs in about 8 seconds per family on the laptop. `examples` and the
14 new tests add 2.96 s to the test suite.

## Verification

| check | result |
|---|---|
| Suite runs against any family by name and reports per check with reasons | **PASS** — `--family`, and refusals name the protocol requirement |
| Suite runs against an **unregistered** family | **PASS** — `--module examples/random_sharded/model.py` |
| All three shipped families measured, every failure reported | **PASS** — 2 failures, both reported, neither absorbed |
| No check weakened to accommodate a shipped family | **PASS** — no check's threshold changed; the three suite fixes were false-positive fixes, each recorded above |
| `random_sharded` exists under `examples/`, passes, is not selectable | **PASS** — 8 passes, 0 fails; not in `REGISTRY`, asserted by a test |
| `random_sharded`'s inferiority measured and reported | **PASS** — table above |
| `docs/FAMILIES.md` written for an outside reader | **PASS** — see caveat below |
| `propose`'s family refusal names the document | **PASS** — `policy.py:NO_SCOPE` |
| Charter says what the unit concretely is, and that none came from outside | **PASS** — Phase 3b2 |
| The suite has teeth | **PASS** — 7 mutants, each caught by the check it breaks and no other |
| Full test suite | **PASS** — 1279 passed, 2 skipped |
| Identifier scan of new files | **PASS** — 0 |

**Couldn't check:**

- **Whether `docs/FAMILIES.md` is sufficient for an outside reader.** The
  acceptance criterion is "a person who has not seen this codebase could
  implement a family from it", and I wrote it, so I am the worst available
  judge. What can be said is that the worked example was written *from* the
  document's structure and passes the suite. What would settle it is somebody
  outside this team using it.
- **The cross-environment half of the determinism contract**, for all four
  families. Reported as its own couldn't-check by the suite, naming
  `oneground pod` and `compare_state.py --cross-environment`.
- **Whether the two findings would fire on a real sweep.** Both need a
  configuration nobody would write by hand. They are reachable from a grid —
  `shards: [1501]` is a typo away — but no published requirements file
  contains one.

## Observed, not done

- **Neither finding was fixed in this task.** The brief says report, not
  repair. Finding 2 was then fixed as **042b** on the developer's instruction,
  because it stops a sweep. Finding 1 remains, and is one `ParameterError` in
  `hash_sharded.build` refusing `shards > len(vectors)`, with
  `indexes.build`'s message to copy.
- **`footprint.fanout` can disagree with `footprint.shards`** in
  `hash_sharded` even below the refusal threshold — it reports the requested
  count, not the built one. **Fixing the refusal does not fix this**, which is
  why finding 1 is two decisions rather than one: the fan-out should be
  `min(requested, built)` the way the example computes it, and that is true at
  every shard count, not only impossible ones.
- **`CONTRIBUTING.md` §2 lists four protocol methods, not six.** `configs`
  and `state` are missing, so a contributor reading the entry point learns a
  protocol two methods short of the real one. One line; the brief named
  `docs/CHARTER.md` and not this file.
- **The suite is synthetic only, by design**, and the brief's "150k checks run
  locally or are reported as couldn't-check with their cost" does not bite:
  none of the nine checks is a claim about a published value, so a 150k run
  would cost hours and change no outcome. A family's *numbers* still need a
  real corpus; its *contract* does not.
- **`test_conformance.py` and `conformance.py` overlap** on ceiling, build
  determinism and the state contract. Both run and neither is redundant — one
  is a pytest gate over the registry, the other a command over a file — but a
  future task could make the pytest file drive the command and keep one
  definition of each check.

## Repo now contains

New:

- `oneground/models/conformance.py` — the suite
- `oneground/models/test_family_conformance.py` — 14 tests, 7 of them mutants
- `examples/random_sharded/model.py` — the worked example
- `docs/FAMILIES.md` — the contributor document
- `tasks/042-family-conformance.report.md` — this file

Changed:

- `oneground/cli.py` — `oneground models conformance`, and its `UNGUARDED`
  entry saying it writes no file and reads no fixture
- `oneground/proposals/policy.py` — `NO_SCOPE` names `docs/FAMILIES.md`
- `docs/CHARTER.md` — Phase 3b2

Scratch (`tasks/scratch/`, gitignored):

- `042-conformance-shipped.log`, `042-conformance-example.log`
- `042-verify-the-two-findings.py` — both findings without the suite
- `042-random-vs-hash.py`, `042-random-vs-hash.log`

Branch `task-042`, pushed, and merged to `main` after 042b landed on it.

## Blocked on developer

Nothing.

One decision remains, and it is **two** decisions rather than one:
`hash_sharded` should refuse `shards > len(vectors)`, **and** `fanout` should
report the shards that were built rather than the ones that were asked for.
The second is true at every shard count, so a refusal alone would leave a
configuration that builds 3 shards and prices queries at 4 if one came back
empty. Neither is authorised by this brief.
