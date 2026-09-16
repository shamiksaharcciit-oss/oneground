# oneground 0.1.0

Measure a retrieval architecture decision on your own vectors, against exact
k-NN ground truth, and keep the receipt.

This is the first release with a preview week behind it. Four commands are
real and measured, two engines have adapters, two public fixtures are
published with their receipts. Everything else in the charter is planned, has
no date, and this release says so rather than implying otherwise — see
[docs/CHARTER.md](docs/CHARTER.md).

## What works today

```
pip install oneground

oneground characterize requirements.yaml   # five measures on your own sample
oneground simulate     requirements.yaml   # architectures against exact k-NN
oneground verify       requirements.yaml   # real engines: Qdrant, pgvector
oneground report       requirements.yaml   # verdicts, with every source named
oneground fixture verify arxiv-150k        # does this install reproduce ours?
oneground calibrate show                   # what our own error has measured
oneground pod ...                          # a session on rented hardware
```

Three outcomes, always kept apart: **verified**, **contradicted**,
**couldn't-check**. couldn't-check is never rounded up. Every number in a
report names the file and field it came from.

## What is new since `0.1.0-preview`

**A second engine, and a comparison that is fair by construction.**
`verify.engines: [qdrant, pgvector]` runs each engine in turn on one host,
with the same corpus, the same query set and the same index parameters. Both
carry their own number and their own verdict everywhere — in the decision log,
in the options table, in the recommendation panel. `report.json` gains
`engines_meeting`: the engines on which an architecture cleared every
engine-scoped constraint, which is the answer to "so which one do I deploy?".

**A latency verdict that knows how precise it is.** Two sessions in the
preview measured the same configuration at 38.22 ms and 42.82 ms against a
40 ms constraint, and reported `meets` once and `fails` once with nothing
about the architecture changing between them. `verify.runs: N` now repeats the
load phase with the **engine restarted between runs**, reports min / median /
max / spread, and the verdict is:

| | when |
|---|---|
| `meets` | the **worst** run meets it |
| `fails` | the **best** run fails it |
| `couldnt_check` | otherwise — and it carries **no value**, because a couldn't-check with a number attached invites the reading it exists to prevent |

**A throughput ceiling that is not the offer.** `verify.measure_ceiling: true`
ramps concurrency with the throttle removed and stops on an error rate over
0.5% or a p99 over five times the first rung's. `qps_max` is reported as its
own row with its own caveat and is **never read** by the `qps` verdict — the
engine's ceiling and the rate it sustained answer different questions.

**A second fixture.** `stackexchange-150k`: 150,000 Stack Overflow questions,
built to the same rules as arxiv-150k so the two read line for line, and
specified in full with every value `TO_BE_FILLED` before the build ran. The
two corpora **agree about architecture and disagree about time** — semantic
sharding loses on both, by more on Stack Overflow (0.869 against 0.932
recall@10), while drift runs the opposite way (0.485→0.450 against
0.522→0.549). Side by side in [docs/FIXTURES.md](docs/FIXTURES.md).

**A truncation warning, before anything is embedded.** Text longer than the
model's `max_seq_length` used to be cut silently, and nothing downstream could
tell: ground truth is computed from the same truncated vectors, so recall
against it is high and self-consistent while every number describes a corpus
that is not the one on disk. `characterize` now counts with the model's own
tokenizer **before** embedding, warns, and writes `truncated_count` to
`build_info.json`. `0` means nothing was cut; `null` means nothing looked.

**Faster, cheaper cloud runs.** Pod sessions run a pre-baked image pinned by
**digest**, never by a tag — Qdrant, PostgreSQL + pgvector and the pinned
venv are in the image, so a session installs nothing. A missing digest is
never a reason to fall back to a tag: `verify` refuses before anything is
created. `pod status` prints where a session's setup time went.

**A checked claim invariant.** Every generated sentence in a report must be
reconstructible from the rows it cites — the options it quantifies over, the
values it quotes and the source field each came from — and the check runs
before the report is written. It exists because the same defect shipped once:
a report that said "both carry meets" about an engine that had failed. See
[docs/CLAIMS.md](docs/CLAIMS.md).

**Configurations are validated against each family's declared parameters.**
Every architecture family now declares the parameters it reads, with their
types and valid ranges. A requirements file that names a key the family does
not declare is refused, with the declared list; so is a key the family would
ignore — a constant it fixes, or a grid entry for a parameter it does not
sweep. Before this, such a key was accepted, written into the configuration's
label and silently ignored, while the run reported numbers as if it had been
applied. **A file that used to run with a misspelled key will now stop, and
that is deliberate.** No working configuration changes: a key that was
silently ignored was never applied, so every number measured without it is
the number measured with it. One file does change: `simulate.json` rows for
`single_node_hnsw` and `hash_sharded` no longer list `shard_depth` in their
`params`, because neither family ever read it, so a `0.1.0` run of the same
configuration writes a different file from a preview run — no number and no
label moved. To show that no measurement moved with it, both fixtures were
recomputed on this code under the pinned versions: every value `fixture
verify` recomputes reproduced, 8 of 8 for `arxiv-150k` and 8 of 8 for
`stackexchange-150k`, each inside its published tolerance.

## The release assets

Two, one per full fixture. Neither is in the repository: 480 MB does not
belong in git. The small `arxiv-smoke` fixture ships in the repo and needs no
download.

```
arxiv-150k-v1.tgz
  483,467,899 bytes
  sha256  437ac5db45cdb2c1c8cc21707816d508981327a0152d86283151be032d3310f2

stackexchange-150k-v1.tgz
  460,106,909 bytes
  sha256  2871c61333bbe80adf124ff64ff15831ebd593f24bf180a3ae71edf72054484e
```

Both were packed with `--owner=0 --group=0 --numeric-owner` and `gzip -n`, so
no header names the account or the machine that packed them. Their members are
byte-for-byte the ones listed below.

Every member digest below was streamed out of the tarball and compared against
that fixture's `MANIFEST.sha256` in this repository.

**`arxiv-150k-v1.tgz`**

| member | bytes | sha256 |
| --- | --- | --- |
| `vectors.npy` | 460,800,128 | `141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa` |
| `queries.npy` | 6,144,128 | `dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b` |
| `sample.jsonl.zst` | 49,920,799 | `404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655` |

**`stackexchange-150k-v1.tgz`**

| member | bytes | sha256 |
| --- | --- | --- |
| `vectors.npy` | 460,800,128 | `067d8ffbdf16f08f0a43e3fa1fccb3ca4a62093cd8f00069038f7d88bee17f30` |
| `queries.npy` | 6,144,128 | `465a37757bd7dd1daef7ac2bf9a62a9c32deb8d32e907493cc75c22e4ac76b54` |
| `sample.jsonl.zst` | 26,813,350 | `2ab675cc3c20a0ff97602c26d070c24d307a97a4f69529ea37d7fd145c74ef0e` |

### Verifying your installation against one

Anyone can run this. It needs no account, no GPU, no clone and no particular
directory layout — `--asset` points at wherever you extracted the tarball.

```
python -m venv .venv                       # Python 3.12 or newer
. .venv/bin/activate                       # Windows: .venv\Scripts\activate
pip install oneground

oneground --version                        # 0.1.0

# no download needed -- the smoke fixture publishes no values yet
oneground fixture verify arxiv-smoke

# download an asset from this release and extract it anywhere:
tar -xzf arxiv-150k-v1.tgz
oneground fixture verify arxiv-150k --asset fixtures/arxiv-150k

tar -xzf stackexchange-150k-v1.tgz
oneground fixture verify stackexchange-150k \
    --asset fixtures/stackexchange-150k
```

The package carries each fixture's spec, manifest and ground truth, so the
command works from any directory; the vectors, queries and sample are in the
release asset, and `--asset` says where you put them. Inside a clone of the
repository the clone's copy of the fixture is used instead, and the output
says which copy it read.

**It names everything it is missing, in one run.** Before the digests it
prints three preconditions — the fixture, the pinned environment and the
release asset — each found or missing, with how to supply what is missing: the
asset's name, its size, this release's page and the `--asset` flag. A run that
is missing a precondition checks what it can, recomputes no value that needs
the missing thing, and exits 2.

**Digests come back in seconds. Values take about ten minutes** — each
recomputes the characterization, the drift pair and both reference
configurations over 150,000 vectors, and compares each against that fixture's
own tolerance.

**That ten minutes assumes the machine is not paging.** The recomputation
loads the fixture's 460 MB of vectors and builds indexes over them, so it wants
a few spare gigabytes; on a laptop already short of RAM the same work takes far
longer in wall clock for the same few minutes of CPU — the run that cut this
release took **2 h 06 m for 588 seconds of CPU**, about 95% of it waiting on
page faults, with 225 MB of physical memory free. The answer is identical when
it finishes; only the clock is different.

**With too little memory some values cannot be recomputed.** The value
recomputation needs a few hundred megabytes contiguous. When the machine
cannot give it, that value is reported `couldnt_check` with the failed
allocation as its reason, the other values carry on, and the command exits 0
if nothing is contradicted. The digests are checked before any value, so the
bytes are confirmed either way, and the summary says so. Slow and short of
memory are different outcomes and want different responses: the first wants
patience, the second wants memory.

On the machine that cut this release:

```
arxiv-150k          digests 11 verified, 0 contradicted, 0 couldnt_check
                    values   8 verified, 0 contradicted, 0 couldnt_check

stackexchange-150k  digests 11 verified, 0 contradicted, 0 couldnt_check
                    values   6 verified, 0 contradicted, 2 couldnt_check
```

The arXiv fixture on `main` carries 17 digests, because a published report
(`fixtures/arxiv-150k/report/`, declared) was added after the `v0.1.0` tag; the
tagged release carries the 11 above.

`fixtures/arxiv-150k.fixture.yaml` carries `status: verified` because of that
run — on Windows, against a build made on Linux with a CUDA GPU, under the
same pinned versions.

`fixtures/stackexchange-150k.fixture.yaml` carries `status: built`, which is
the weaker claim and is the accurate one. Its digests check and its values are
measured, but two — `semantic_sharded.recall_at_10` and
`.storage_amplification` — are **couldn't-check** on the machine that cut this
release, which runs out of memory recomputing the 256-shard reference over
150,000 vectors. Recorded with the reason, and not rounded up.

**No value is reproduced if your numpy, faiss-cpu or scikit-learn differ from
the pinned versions.** That is deliberate: a value recomputed under different
libraries has not been reproduced under the pins the fixture claims. The
command says which package differs and by how much, and that a fresh virtual
environment with `pip install oneground==0.1.0` installs the pinned set; it
recomputes no value and exits 2. With `--allow-unpinned` it recomputes them
anyway, and every value that agrees comes back `couldnt_check` with its
numbers shown.

## Licences

The tool is **Apache-2.0**.

**arxiv-150k.** The arXiv metadata (titles, abstracts, categories, dates) is
released under **CC0 1.0** via the arXiv dataset on Kaggle and Hugging Face.
The asset redistributes a sampled subset of that metadata plus vectors derived
from it. Abstract text is included for the learner interface only.

**stackexchange-150k.** Stack Overflow post content is **CC BY-SA**, at
version **2.5, 3.0 or 4.0 per post**, taken from each record's own
`ContentLicense` field rather than assumed — the sample carries the licence
version alongside the post id, so a redistributor can attribute each record
correctly. Source: the Internet Archive Stack Exchange dump via Hugging Face
`mikex86/stackoverflow-posts` at a pinned revision. Attribution and share-alike
apply to the text; the vectors are derived from it.

The embedding model, `BAAI/bge-base-en-v1.5`, is MIT-licensed and is **not**
redistributed in either asset — the vectors are, the weights are not.

## Known limits

- **A sample is not your corpus.** oneground measures 20,000 vectors drawn by
  a seeded rule, not the 20 million you have. That is the point — it is what
  makes the measurement affordable — and it means every number is a statement
  about a sample, with the sampling rule recorded beside it.
- **Retrieval, not generation.** Nothing here measures answer quality, and no
  number in a report is evidence about what an LLM does with what was
  retrieved. Chunking — the decision that most changes both — is not measured
  at all yet; the position is written down in
  [docs/CHUNKING.md](docs/CHUNKING.md) and no code implements it.
- **No engine can be ranked without an adapter.** Two exist: Qdrant and
  pgvector. An engine with no adapter is not slower or faster here, it is
  absent, and absence is never reported as a result. The conformance suite is
  the gate; see [CONTRIBUTING.md](CONTRIBUTING.md).
- **Two engines measured as deployed, not as tuned.** `COPY`, unlogged tables,
  `synchronous_commit=off`, quantization: absent for both, deliberately.
  `verify.json` records how each was configured so "default" is checkable
  rather than asserted.
- **Single-client latency is unattributable** on any hardware this runs on. A
  loopback round trip is the same order as an HNSW query, so a `p95_ms`
  constraint with no `at_qps` returns couldn't-check and always will. Latency
  under load is attributable, and that is what a verdict uses — and on a pod
  fast enough that even the loaded round trip dominates, the row says
  "unanswerable in this environment" rather than inviting a rerun that cannot
  help. See [docs/VERIFY.md](docs/VERIFY.md).
- **`couldn't-check` is an outcome, not a failure to report.** It is what you
  get when the evidence does not decide the question, it is never rounded up
  to a verdict, and a release that shows more of it than the last one has
  usually got more honest rather than worse.
- **Tier 2 issues no verdicts.** A declared corpus gets a fixture analogy and
  capacity arithmetic, both labelled, and nothing else. See
  [docs/INTAKE.md](docs/INTAKE.md).

## Provenance

Every task brief and every task report is in `tasks/`. They are the receipt
trail for how each number here was arrived at, including the runs that failed
and what they cost.
