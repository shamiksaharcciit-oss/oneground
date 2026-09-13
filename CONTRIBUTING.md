# Contributing to oneground

oneground measures a retrieval architecture decision on your own vectors and
writes down every number with the seeds and digests needed to re-derive it.
Contributions are welcome, and they are held to that standard rather than to a
style guide.

## The one rule everything else follows from

**Three outcomes, always kept apart: verified, contradicted, couldn't-check.
couldn't-check is never rounded up.**

A measurement that could not be made is not a measurement that failed, and
neither is a measurement that passed. Code that collapses the three — a
default, a fallback, a `try/except` that returns a number — will be asked to
name what it could not check and why.

Related, and just as load-bearing:

- **Receipts and declarations are never blurred.** A receipt is re-derivable
  from the seeds and rules recorded beside it. A declaration is bytes someone
  froze. Both are legitimate; calling one the other is not.
- **Never move a gate to pass.** No widening a tolerance, changing a seed, or
  adjusting a threshold to turn a contradiction into a verdict. If a check
  fails, diagnose which layer is responsible and report that.
- **Nothing labelled as capability that is only planned.** The README's
  "What is planned" section is load-bearing; keep it honest in both
  directions.

## The four contribution units

### 1. An engine adapter

The highest-value contribution, and the one with the clearest gate.

Every engine sits behind the `VectorEngine` protocol in
`oneground/adapters/base.py`. There is no default engine and no favourite; an
adapter that special-cases itself anywhere outside its own directory will not
be merged.

**The gate: the conformance suite.** `oneground/adapters/conformance.py`
runs the same battery against every registered adapter —
`run_conformance(name, factory, endpoint_desc)` — plus a protocol check that
walks every adapter in the registry. A new adapter is merged when it passes
unmodified, against a real running engine: not when the suite is adjusted to
accommodate it, and not on a stub. If a real engine cannot satisfy a
conformance test, that is a finding worth writing up, and the suite changes
only after the finding is recorded and agreed.

**Two engines pass it today: Qdrant and pgvector.** Milvus and Weaviate are
the named next two, and nothing about either is written. The acceptance
criterion for a third is a test run, not a maintainer's opinion, and that is
deliberately what makes this the contribution unit.

An adapter must also report `describe()` honestly: `engine_facts` is what the
engine says about itself, marked `declared`, and it is never inferred from
what oneground asked for. Task 013 turned on that distinction —
`fixture verify` compares `index_params` (what was built) against
`engine_params` (what was requested), and an adapter that echoed the request
back would have made the check meaningless.

See [docs/ADAPTERS.md](docs/ADAPTERS.md).

### 2. An architecture family

A runnable simulator under `oneground/models/`, implementing the `Model`
protocol: `build`, `search`, `ceiling`, `footprint`.

**`ceiling()` is mandatory and is the point.** It reports exact search over
everything the architecture's routing can reach, so recall loss decomposes
into *routing* loss and *index* loss. A family without a ceiling produces a
recall number nobody can attribute, which is what this project exists to
replace.

`footprint()` must be honest about what it estimates. `memory_bytes` is a
vector payload plus a graph term, not an allocator's behaviour, and it is
labelled an estimate everywhere it is printed.

See [docs/MODELS.md](docs/MODELS.md).

### 3. A fixture

A public corpus with frozen ground truth and published values, so anyone can
check that their installation reproduces them. Fixtures are for learning and
for verifying an install. **They are never a leaderboard**, and a pull request
that ranks engines or families on a fixture will be closed.

A fixture spec declares its own tolerances. `oneground fixture verify`
recomputes every published value from the release asset and compares each
against *that spec's* tolerance — never one supplied at the command line.

Two ship today: `arxiv-150k` (`verified`) and `stackexchange-150k` (`built`),
compared line for line in [docs/FIXTURES.md](docs/FIXTURES.md). A spec is
written in full, with every value `TO_BE_FILLED`, **before** its build runs,
so the answer cannot be steered by the rules; a spec whose `status` is still
`planned` is deliberately not matchable for Tier 2 analogies.

**The gate: a fixture reaches `status: verified` only when every digest and
every published value reproduces, in the pinned environment.** Not most of
them. Not "close enough". arxiv-150k sat at `built` for four tasks because one
value — drift — was not reachable by the verifier, and it was not marked
verified until it was.

If your corpus is worth analogising against for Tier 2 users, add an
`analogy:` block: what the corpus *is like*, in the vocabulary
`corpus.declared` uses. Those are declared fields, and matching on them never
produces a verdict.

### 4. A policy

A small function in `policies/` that turns measurements into a proposal, with
tests. Policies read the report's numbers; they never recompute them.

## The calibration gate

`oneground calibrate` measures the tool's own error, in public, and appends to
`calibration/history.jsonl`. That file is **append-only**. A contradicted line
is kept, not fixed; a tolerance is never widened to turn a contradiction into
a pass.

Three layers, and a contribution that changes any measured value has to say
which it affects:

| layer | what it checks | blocking? |
| --- | --- | --- |
| `layers` | corpus reachability, metric agreement, recall accounting | yes |
| `curve` | our simulator against published ANN-Benchmarks numbers | advisory on glove — it compares two HNSW implementations that genuinely differ |
| `engine` | our simulator against a real engine, on your own corpus | yes |

See [docs/VALIDATION.md](docs/VALIDATION.md) for which measures are validated
against a reference and which are only predictions.

## Practicalities

**Use the pinned environment.** Every command that writes a canonical artifact
refuses to run when numpy, faiss-cpu or scikit-learn differ from
`requirements.txt`, and prints which. On Windows that means invoking
`.venv\Scripts\python.exe` explicitly — bare `python` is often the system
interpreter. `--allow-unpinned` proceeds and stamps the artifact.

**Tests.** Anything with a contract gets one: adapter conformance, policy
signatures, fixture verification, CLI wiring. A test that only passes on
synthetic data says so in its name — the suffix `_synthetic` is used
throughout, and a test whose name lacks it is claiming to check something
real.

```bash
.venv/Scripts/python.exe -m pytest oneground -q
```

**Dependencies** are pinned exactly, in `requirements.txt` and in
`pyproject.toml`. A new one is added with its version and a sentence saying
what needs it.

**Commits** say what changed and why, and name what was measured rather than
what was intended. The git log is part of the receipt trail.

## Reporting a contradiction

If oneground tells you a published value is contradicted on your machine,
that is the most useful bug report this project can receive. Please include:

- the full `oneground fixture verify <id>` output, including the interpreter
  line at the top
- your platform and `pip freeze`
- whether the digests verified (a digest contradiction and a value
  contradiction are different problems)

A value that differs under different library versions is expected and is
reported as couldn't-check, not as a contradiction. A value that differs under
the *pinned* versions is a real finding.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
