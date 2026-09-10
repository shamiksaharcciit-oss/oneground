# oneground 0.1.0-preview

Measure a retrieval architecture decision on your own vectors, against exact
k-NN ground truth, and keep the receipt.

This is a **preview**. Three commands are real and measured; the rest of the
charter is planned and this release says so rather than implying otherwise.
See [docs/CHARTER.md](docs/CHARTER.md) for what is planned and when.

## What works today

```
pip install oneground

oneground characterize requirements.yaml   # five measures on your own sample
oneground simulate     requirements.yaml   # architectures against exact k-NN
oneground verify       requirements.yaml   # a real engine (Qdrant)
oneground report       requirements.yaml   # verdicts, with every source named
oneground fixture verify arxiv-150k        # does this install reproduce ours?
oneground calibrate show                   # what our error has measured
oneground pod ...                          # a session on rented hardware
```

Three outcomes, always kept apart: **verified**, **contradicted**,
**couldn't-check**. couldn't-check is never rounded up. Every number in a
report names the file and field it came from.

## The release asset

`arxiv-150k-v1.tgz` — 150,000 arXiv abstracts embedded with
`BAAI/bge-base-en-v1.5`, with frozen exact ground truth. It is **not** in the
repository: 483 MB does not belong in git.

```
arxiv-150k-v1.tgz
  483,468,013 bytes
  sha256  0b7a0209fa4085683950e4715d49597c820cadc575b4a4fe85ef2d4f5365c015
```

Its three members, each digest matching `fixtures/arxiv-150k/MANIFEST.sha256`
in this repository:

| member | bytes | sha256 |
| --- | --- | --- |
| `vectors.npy` | 460,800,128 | `141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa` |
| `queries.npy` | 6,144,128 | `dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b` |
| `sample.jsonl.zst` | 49,920,799 | `404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655` |

### Verifying your installation against it

Anyone can run this. It needs no account, no GPU, and no particular directory
layout — `--asset` points at wherever you extracted the tarball.

```
python -m venv .venv                       # Python 3.12 or newer
. .venv/bin/activate                       # Windows: .venv\Scripts\activate
pip install oneground

oneground --version                        # 0.1.0-preview (0.1.0rc1)

# download arxiv-150k-v1.tgz from this release, then extract it anywhere:
tar -xzf arxiv-150k-v1.tgz

git clone https://github.com/oneproof/oneground && cd oneground
oneground fixture verify arxiv-150k --asset ../fixtures/arxiv-150k
```

The clone is for the fixture's published values and manifest, which are in the
repository; the 483 MB of vectors are in the release asset, and `--asset` says
where you put them.

**Digests come back in seconds. Values take about ten minutes** — it
recomputes the characterization, the drift pair and both reference
configurations over 150,000 vectors, and compares each against the fixture's
own tolerance. On the machine that cut this release:

```
summary: digests 11 verified, 0 contradicted, 0 couldnt_check
         values   8 verified, 0 contradicted, 0 couldnt_check
```

`fixtures/arxiv-150k.fixture.yaml` carries `status: verified` because of that
run — on Windows, against a build made on Linux with a CUDA GPU, under the
same pinned versions.

**It will report `couldnt_check` for every value if your numpy, faiss-cpu or
scikit-learn differ from `requirements.txt`.** That is deliberate: a value
recomputed under different libraries has not been reproduced under the pins
the fixture claims. The command says which package differs and by how much.

## Licence

The tool is **Apache-2.0**.

The arXiv metadata in the asset (titles, abstracts, categories, dates) is
released under **CC0 1.0** via the arXiv dataset on Kaggle and Hugging Face.
This asset redistributes a sampled subset of that metadata plus vectors
derived from it. Abstract text is included for the learner interface only.

The embedding model, `BAAI/bge-base-en-v1.5`, is MIT-licensed and is **not**
redistributed here — the vectors are, the weights are not.

## Known limits in this preview

- **Single-client latency is unattributable** on any hardware this runs on.
  A loopback round trip is the same order as an HNSW query, so a `p95_ms`
  constraint with no `at_qps` returns couldn't-check and always will. Latency
  under load is attributable, and that is what a verdict uses. See
  [docs/VERIFY.md](docs/VERIFY.md).
- **One engine adapter** (Qdrant). The `VectorEngine` protocol and its
  conformance suite are the contribution gate for more; see
  [CONTRIBUTING.md](CONTRIBUTING.md).
- **`qps_max` is not implemented.** `qps` answers whether an engine sustained
  the rate it was offered, which is a different question from what its ceiling
  is, and the two must never share a row.
- **Tier 2 issues no verdicts.** A declared corpus gets a fixture analogy and
  capacity arithmetic, both labelled, and nothing else. See
  [docs/INTAKE.md](docs/INTAKE.md).

## Provenance

Every task brief and every task report is in `tasks/`. They are the receipt
trail for how each number here was arrived at, including the runs that failed
and what they cost.
