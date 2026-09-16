# oneground

![The ground view: 150,000 arXiv abstracts, coloured by how many regions each vector must be copied into](docs/img/ground_thumbnail.png)

Choosing a vector store, an index, and a sharding scheme is usually decided by
vendor leaderboards, a blog post, and whatever the last team did. oneground
measures that decision on **your own embeddings**, against exact k-NN ground
truth, and writes down every number with the seeds and digests needed to
re-derive it. It is local-first and offline: your vectors never leave the
machine, and there is no telemetry.

Part of the [oneproof](https://oneproof.dev) suite — the *Choose* door.

---

## Install

**A virtual environment is required.** The package pins numpy, faiss-cpu and
scikit-learn exactly, so installing it into the system Python replaces the
versions of whichever of those, and of their dependencies, it already has.

On macOS or Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install oneground
oneground --help
```

In Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install oneground
.venv\Scripts\oneground.exe --help
```

Python 3.12 or newer. Extras, each named for the capability it unlocks:

| extra | for |
| --- | --- |
| `[embed]` | handing oneground text instead of vectors |
| `[view]` | the ground view and the fixture builder's projection |
| `[qdrant]` | `oneground verify` against a real Qdrant |
| `[pgvector]` | `oneground verify` against a real PostgreSQL + pgvector |
| `[pod]` | `oneground pod`; names the capability and installs nothing |
| `[calibrate]` | reading the ANN-Benchmarks HDF5 |
| `[test]` | running the suite |

An extra installs the **client**, never the engine. The Qdrant server and the
PostgreSQL server are yours to run, as a container or a binary. `oneground
verify --up` will compose the pinned container when you ask it to, and nothing
starts if you do not.

```bash
pip install 'oneground[qdrant]'      # or 'oneground[qdrant,pgvector]'
```

The quotes are for zsh, which treats brackets as a glob.

To work on oneground rather than with it, on macOS or Linux:

```bash
git clone https://github.com/oneproof/oneground
cd oneground
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

In Windows PowerShell:

```powershell
git clone https://github.com/oneproof/oneground
cd oneground
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
```

One command per line, on purpose: `&&` is a parse error in Windows
PowerShell 5.1.

**Use that venv's interpreter explicitly.** Every command that writes a
canonical artifact refuses to run when your numpy, faiss-cpu or scikit-learn
differ from `requirements.txt`, and prints which. A measurement computed under
different libraries is not the measurement the pins describe. `--allow-unpinned`
proceeds and stamps the artifact `unpinned environment` so every reader of it
can see that.

## Characterize your corpus

Copy [`requirements.example.yaml`](requirements.example.yaml) — it is the
schema by example — point it at your vectors, and run:

```bash
oneground characterize requirements.yaml
```

The minimum it needs is a sample of vectors, some queries, and a seed:

```yaml
oneground: 1
run:
  name: support-tickets-2026q3
  seed: 20260910
  workdir: ./runs/support-tickets-2026q3
corpus:
  sample:
    kind: receipt
    vectors: {path: ./data/sample_vectors.npy}
    queries: {path: ./data/queries.npy, count_min: 50}
    target_sample_size: 20000
```

You get five numbers about the shape of your corpus:

| measure | what it answers |
|---|---|
| `intrinsic_dimensionality` | how many dimensions the data actually occupies, against how many the embedding declares |
| `boundary_crispness` | do vectors sit clearly inside one region, or on a boundary between two |
| `ambiguous_query_rate` | what share of queries cannot be routed confidently to a single shard |
| `skew_top10_share` | how much of the corpus lands in the ten largest of 256 regions |
| `drift` | what a partition trained on the past does to queries from the future |

and a directory of receipts beside them:

```
runs/support-tickets-2026q3/
  characterization.json   the measurements                     (receipt)
  sample_ids.json         which rows were measured             (receipt)
  queries_ids.json        which queries were used              (receipt)
  build_info.json         versions, device, input digests      (declared)
  MANIFEST.sha256         a digest for each of the above
```

**Receipt** means re-derivable: same inputs and seed, same bytes.
**Declared** means recorded rather than re-derivable — timestamps, library
versions, the host. The two are never blurred, and anything that could not be
measured is reported as `couldnt_check` with the reason, never filled in from
a guess. Ask for drift without a timestamp column and you get
`"couldnt_check: no timestamp_field"`, not a number.

## Check your installation against a public fixture

Two public fixtures ship with the project: **arxiv-150k**, 150,000 arXiv
abstracts (CC0), and **stackexchange-150k**, 150,000 Stack Overflow questions
(CC BY-SA, per post). Both are embedded with pinned weights and published with
exact ground truth and measured values. They exist so a stranger can confirm
an installation reproduces the numbers this project publishes — they are
**not** a leaderboard.

The small fixture runs from a fresh clone with nothing downloaded:

```bash
oneground fixture verify arxiv-smoke
```

The full ones need their vectors, which ship as release assets rather than in
the repository. A tarball extracts to `fixtures/<id>/`, wherever you extract
it; point verify at that folder:

```bash
tar -xzf arxiv-150k-v1.tgz
oneground fixture verify arxiv-150k --asset <where you extracted it>/fixtures/arxiv-150k
```

Each digest and each published value comes back **verified**, **contradicted**
or **couldn't-check**, with the reason. A value that needs an artifact you
have not downloaded is couldn't-check — never a pass, and never silence.
The two fixtures side by side, with every measure and both reference results,
are in [docs/FIXTURES.md](docs/FIXTURES.md).

The picture at the top is arxiv-150k. Almost all of it is one colour:
**84% of the vectors sit close enough to four different regions that they must
be copied into all of them.** The categories separate visibly, which is why
semantic sharding looks obviously right — and on this corpus it loses, 0.932
recall at 3.7x storage against 0.997 at 1x for a single flat index. On
stackexchange-150k it loses by more: 0.869 at 3.9x. That result is why the
tool exists.

---

## How this tool is checked against numbers that are not its own

Every recommendation is only as good as the instrument behind it, so the
instrument is measured too — against published ANN-Benchmarks results on a
corpus and a ground truth oneground did not produce, and against real engines
on your own sample.

```bash
oneground calibrate show      # the history, and the latest outcome per check
```

[docs/VALIDATION.md](docs/VALIDATION.md) is the whole picture: the three
layers, what runs weekly, and — the part worth reading first — which measures
are **validated against a reference** and which are still **predictions with
no external counterpart** (boundary crispness, ambiguous query rate, drift).
A `contradicted` result blocks a release; `couldn't-check` never does, and is
never rounded up.

---

## What exists today

Everything in this list is in `0.1.0` and has been run end to end.

**The four commands.**

- **`oneground characterize`** — the five measures on your own sample, with
  receipts. Vectors (`.npy`, `.parquet`) or text (`.jsonl`) plus a pinned
  model; text longer than the model's `max_seq_length` is **counted and
  warned about before it is embedded**, because truncation is the one intake
  fault that leaves no trace in any number downstream. Tier 2
  (`corpus.declared`) describes a corpus you have not embedded yet; it
  produces a fixture analogy and capacity arithmetic and **never a verdict**.
  See [docs/INTAKE.md](docs/INTAKE.md).
- **`oneground simulate`** — `single_node_hnsw`, `hash_sharded` and
  `semantic_sharded` as runnable families over your sample, against exact
  k-NN, with loss decomposed into partitioning vs. index.
- **`oneground verify`** — a real engine on the same sample. **Two adapters:
  Qdrant and PostgreSQL + pgvector**, measured in turn on one host so the two
  rows are comparable. Locally, or in a matched environment on a pod where
  latency under load is attributable. `runs: N` repeats the load phase with
  the engine restarted between runs and reports the **spread**, and the
  latency verdict is `couldnt_check` when the runs straddle the threshold.
  `measure_ceiling: true` adds `qps_max`, the highest rate an engine sustains
  before latency or errors break — which is never read by the verdict about
  the rate it was offered. See [docs/VERIFY.md](docs/VERIFY.md).
- **`oneground report`** — the trade-off surface, three outcomes per option
  (meets / fails / couldn't-check), a decision log naming every source field,
  and a deployable manifest. Where two engines were measured, each carries its
  own number and its own verdict, everywhere.

**And around them.**

- **`oneground fixture verify`** — recompute a fixture's digests **and its
  published values** and report verified / contradicted / couldn't-check for
  each.
- **`oneground fixture build`** — rebuild a fixture from its spec and seeds.
- **`oneground pod`** — run a session on rented hardware, with the money
  boundary documented in [docs/POD.md](docs/POD.md). Sessions run a pre-baked
  image **pinned by digest**, never by a tag.
- **`oneground calibrate`** — measure this installation against published
  ANN-Benchmarks values and against real engines, and keep the history. See
  [docs/VALIDATION.md](docs/VALIDATION.md).

**Two public fixtures**, built the same way and published side by side in
[docs/FIXTURES.md](docs/FIXTURES.md):

- **arxiv-150k**, `status: verified` — 150,000 arXiv abstracts (CC0). Every
  digest and every published value reproduced on a second machine and a second
  operating system, under the same pinned versions.
- **stackexchange-150k**, `status: built` — 150,000 Stack Overflow questions
  (CC BY-SA, per post), specified in full before it was built. Two of its
  rows are `couldnt_check` on a laptop, with the reason recorded.

They disagree about time and agree about architecture, which is the finding
this release leads with.

## What is planned

Nothing below is implemented, and oneground will not pretend otherwise. None
of it carries a date.

- **More engine adapters** — Milvus and Weaviate are the named next two. The
  `VectorEngine` protocol and its conformance suite are the gate, and passing
  the suite is the unit of contribution: an adapter that passes is an adapter,
  and nothing else is. See [CONTRIBUTING.md](CONTRIBUTING.md) and
  [docs/ADAPTERS.md](docs/ADAPTERS.md).
- **Chunking measurement** — how a chunking rule changes what is retrievable,
  measured rather than asserted. The position, the four candidate ground
  truths and the ones that are refused are written down in
  [docs/CHUNKING.md](docs/CHUNKING.md); no code implements it.
- **The lab** — the ground view and query traces as interactive renderers over
  the same simulator state the numbers come from.
- **Proposals** — small, testable policy functions that turn a
  characterization into a suggested starting configuration.

The full plan, including what would make the project change course, is in
[docs/CHARTER.md](docs/CHARTER.md).

## Principles

- Your data or nothing. No recommendation from a canned corpus.
- No engine of our own, no favourite. Every engine behind one adapter.
- Receipts (re-derivable) and declarations (bytes frozen), never blurred.
- `couldnt_check` is never rounded up to a verdict.
- Runs on your machine. Your vectors never leave it. No telemetry.
- Nothing labelled as capability that is only planned.
