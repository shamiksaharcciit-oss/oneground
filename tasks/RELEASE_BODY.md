# oneground 0.1.0

Measure a retrieval architecture decision on your own vectors, against exact
k-NN ground truth, and keep the receipt.

Four commands are real and measured, two engines have adapters, and two public
fixtures are published with their receipts so you can check that your install
reproduces our numbers before you trust it on yours. Everything else in the
charter is planned and has no date; this release says so rather than implying
otherwise.

```
pip install oneground

oneground characterize requirements.yaml   # five measures on your own sample
oneground simulate     requirements.yaml   # architectures against exact k-NN
oneground verify       requirements.yaml   # real engines: Qdrant, pgvector
oneground report       requirements.yaml   # verdicts, with every source named
oneground lab          runs/my-run         # look at a run, read-only
oneground propose      runs/my-run ...     # measure one change you wrote
```

Three outcomes, always kept apart: **verified**, **contradicted**,
**couldn't-check**. couldn't-check is never rounded up to a verdict. Every
number in a report names the file and the field it came from.

## Try it without downloading anything

Two commands, no account, no GPU, no clone, no particular directory layout:

```
pip install oneground
oneground --version                  # 0.1.0
oneground fixture verify arxiv-smoke
```

The package carries each fixture's spec, manifest and ground truth, so this
works from any directory. `arxiv-smoke` ships inside the wheel and publishes
no values yet, so it checks digests and returns in seconds — it tells you the
install is intact. To check that your machine reproduces a *measurement*,
download one of the assets below and point `--asset` at wherever you unpacked
it:

```
tar -xzf arxiv-150k-v1.tgz
oneground fixture verify arxiv-150k --asset fixtures/arxiv-150k
```

That one recomputes the characterization, the drift pair and both reference
configurations over 150,000 vectors and compares each against the fixture's
own published tolerance. Budget about ten minutes on a machine with a few
spare gigabytes of RAM. It names every precondition it is missing in one run —
the fixture, the pinned environment, the release asset — with what to do about
each, and exits 2 rather than half-checking.

## What is new since `0.1.0-preview`, in the terms you would notice

**A second engine, and a comparison that is fair by construction.** Qdrant and
pgvector run in turn on one host, with the same corpus, the same queries and
the same index parameters. Each carries its own number and its own verdict
everywhere, and `report.json` names the engines on which an architecture
cleared every engine-scoped constraint.

**A latency verdict that knows how precise it is.** Two preview sessions
measured the same configuration at 38.22 ms and 42.82 ms against a 40 ms
constraint and reported `meets` once and `fails` once, with nothing about the
architecture changing in between. Repeat the load phase with `verify.runs: N`,
the engine restarted between runs, and the verdict is `meets` only if the
worst run meets, `fails` only if the best run fails, and couldn't-check
otherwise — carrying no number, because a couldn't-check with a number invites
the reading it exists to prevent.

**A throughput ceiling that is not the offer.** `qps_max` is measured with the
throttle off, reported as its own row with its own caveat, and never read by
the sustained-rate verdict. The two answer different questions.

**A second fixture.** `stackexchange-150k`, 150,000 Stack Overflow questions,
built to the same rules as `arxiv-150k` so the two read line for line. The two
corpora agree about architecture and disagree about time: semantic sharding
loses on both, by more on Stack Overflow, while drift runs the opposite way.

**A truncation warning, before anything is embedded.** Text longer than the
model's limit used to be cut silently, and nothing downstream could tell —
ground truth is computed from the same truncated vectors, so recall stays high
and self-consistent while every number describes a corpus that is not the one
on disk. `characterize` now counts with the model's own tokenizer first, warns,
and records the count.

**Every sentence in a report is checked against the rows it cites.** A report
that said "both carry meets" about an engine that had failed shipped once. The
check now runs before the report is written.

**Configurations are validated against each family's declared parameters.** A
requirements file naming a key the family does not read is now refused, with
the list of keys it does read. Before this, such a key was accepted, folded
into the configuration's label and ignored, while the run reported numbers as
if it had been applied. **A file that used to run with a misspelled key will
now stop, and that is deliberate.** No working configuration changes, and no
published number moved: both fixtures were recomputed on this code under the
pinned versions, and every value `fixture verify` recomputes reproduced — 8 of
8 for `arxiv-150k`, 8 of 8 for `stackexchange-150k`, each inside its published
tolerance.

**Cheaper cloud runs.** Pod sessions use a pre-baked image pinned by digest,
never by a tag, so a session installs nothing; a missing digest refuses the
run rather than falling back.

**A lab you can look at a run in.** `oneground lab runs/my-run` starts a
local, read-only server on your own machine — loopback by default, and
serving anywhere else needs a flag and prints what that exposes — and draws
what a sweep measured: where the regions are, which vectors the ε closure
copies into more than one of them, and what moves when ε does. It serves a
run's own files and writes nothing; every drawing is a projection and says so,
because a picture of 768 dimensions in two is illustrative and never evidence.
Run `simulate` with `--emit-state` first, so the run records what each family
did. See [docs/LAB.md](docs/LAB.md).

**A proposal loop with no model in it.** `oneground propose <workdir>
--policy p.yaml --prediction q.yaml` measures one parameter change you wrote
yourself, against a prediction you wrote **before** the run, and publishes a
card saying whether it held. The prediction is written first and the run cites
its digest, the baseline row is the one your workdir already has — cited by
digest, never re-measured — and the side-effect budget is a first-class part
of the verdict: a change whose recall rose exactly as promised and whose
storage budget broke is *did not hold*, with the breach named first. Failures
are published with the same completeness as successes, and a card may never
say a change is good, recommended or deployable, or say anything about a
corpus other than the one it ran on. **This is tier 1: you write the policy.**
The model-written tier described in
[docs/PROPOSALS.md](docs/PROPOSALS.md) is not built, there is no `--model`
flag, and nothing in this release sends anything anywhere.

## The release assets

Two, one per full fixture. Neither is in the repository: 480 MB does not
belong in git. The small `arxiv-smoke` fixture ships in the wheel and needs no
download.

```
oneground-0.1.0-py3-none-any.whl
  sha256  a6203b7845ca58c4f3042f368c071a2455d78a9518ad35af21799fd4c8fdfad5

oneground-0.1.0.tar.gz
  sha256  1c2eb6ba4bb7479e051136b3fbc5da5c05d2b1ae68e2046f72b9b3081fbf4e14

arxiv-150k-v1.tgz
  483,467,899 bytes
  sha256  437ac5db45cdb2c1c8cc21707816d508981327a0152d86283151be032d3310f2

stackexchange-150k-v1.tgz
  460,106,909 bytes
  sha256  2871c61333bbe80adf124ff64ff15831ebd593f24bf180a3ae71edf72054484e
```

Both tarballs were packed with `--owner=0 --group=0 --numeric-owner` and
`gzip -n`, so no header names the account or the machine that packed them.
Every member's digest is listed in `RELEASE_NOTES.md` and was streamed out of
the tarball and compared against that fixture's `MANIFEST.sha256` in the
repository.

## Known limits

- **A sample is not your corpus.** oneground measures a seeded sample, not
  your twenty million vectors. That is what makes the measurement affordable,
  and every number is a statement about a sample with the sampling rule
  recorded beside it.
- **Retrieval, not generation.** Nothing here measures answer quality.
  Chunking — the decision that most changes both — is not measured at all yet.
- **No engine can be ranked without an adapter.** Two exist. An engine with no
  adapter is absent, not slower, and absence is never reported as a result.
- **Two engines measured as deployed, not as tuned.** No `COPY`, no unlogged
  tables, no quantization, for either; `verify.json` records how each was
  configured so "default" is checkable rather than asserted.
- **Single-client latency is unattributable** on any hardware this runs on: a
  loopback round trip is the same order as an HNSW query, so a p95 constraint
  with no offered rate returns couldn't-check and always will.
- **`couldn't-check` is an outcome**, not a failure to report. A release that
  shows more of it than the last one has usually got more honest.
- **Tier 2 issues no verdicts.** A declared corpus gets a fixture analogy and
  capacity arithmetic, both labelled, and nothing else.
- **`pytest` is the supported test runner.** Running a test file directly
  collects only the tests defined above that file's `__main__` block, which in
  several modules is a fraction of them.

Full notes, every member digest and the provenance trail: `RELEASE_NOTES.md`
in the repository. Every task brief and every task report is in `tasks/` —
including the runs that failed and what they cost.
