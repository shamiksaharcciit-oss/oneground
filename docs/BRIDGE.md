# oneground — the VectorDBBench bridge: the position, before the code

*20 September 2026. Written before implementation, in the order the five
earlier positions were written: the exam before the code. Every claim
about VectorDBBench below was read from the source of `vectordb-bench
2.0.0`, downloaded from PyPI, not from its documentation.*

---

## 1. The question

oneground answers *what should I build* — across chunking, embedding,
index algorithm and partitioning — on the user's own corpus. When it
finishes, a second question is left standing: **which engine should run
it?** oneground has two adapters. VectorDBBench 2.0.0 has more than
forty, including Milvus, Qdrant, Weaviate, Elastic, pgvector,
pgvectorscale, pgdiskann, AlloyDB, LanceDB, MongoDB, Redis, Pinecone,
TiDB, ClickHouse, Vespa and S3 Vectors.

Building forty adapters is not a plan. Handing the chosen configuration
to a harness that already speaks to them is.

## 2. What makes this honest, and it is not obvious

The obvious objection is that two tools reporting "recall" are reporting
two quantities. Here they are not, and the reason is specific.

**VectorDBBench does not compute ground truth for a custom dataset. It is
given it.** `CustomDataset` declares `gt_file = "neighbors.parquet"` and
`gt_neighbors_field = "neighbors_id"`, and recall is computed as
`len(hits) / count` by set intersection against the ids supplied —
`calc_recall(count, ground_truth, got)` takes the truth as an argument
and derives nothing.

So oneground's exact k-NN over the user's sample **is** the answer key
VectorDBBench grades against. Their recall and oneground's recall are the
same measurement, against the same truth, on the same corpus. That is the
fact this whole bridge rests on, and if a future version of
VectorDBBench changed it, the bridge would have to be reconsidered rather
than patched.

## 3. What is exported, and what is declared

### 3.1 The three files

Read from `CustomDataset` and `CustomDatasetConfig`:

| file | columns | oneground source |
|---|---|---|
| `train.parquet` | `id` int, `emb` float32 array | the sample's vectors |
| `test.parquet` | `id` int, `emb` float32 array | the query set |
| `neighbors.parquet` | `id` matching test, `neighbors_id` int array | the exact k-NN ground truth |

Split training files use `train-[i]-of-[n].parquet`. Every field name is
configurable (`train_id_name`, `train_col_name`, `test_col_name`,
`gt_col_name`), so oneground adopts the defaults rather than renaming
anything.

### 3.2 Three parameters that must be set, not defaulted

- **`metric_type`.** The config object defaults to `L2`; the CLI defaults
  to `COSINE`. oneground's vectors are normalised and its ground truth is
  inner product. A default taken from either side would silently grade
  against a different metric than the truth was computed with, and the
  numbers would look fine. The export sets it explicitly and the receipt
  records it.
- **`with_gt`.** Defaults true, and `--skip-custom-dataset-with-gt`
  exists. The export sets it explicitly; an export whose ground truth was
  skipped is a different experiment wearing the same name.
- **`file_count`.** Must match the number of `train-*` files actually
  written, or the load is silently short.

### 3.3 The query set is a declared subset

VectorDBBench copies the full query set into every concurrent process, so
it recommends around 1,000 test vectors. oneground's fixtures use 2,000.
The export therefore takes a **seeded subset**, declared with its seed and
its size, and the ground truth is subset to match. A run against 1,000 of
2,000 queries is not the same run as one against all of them, and the
card says which.

## 4. What comes back, and what may sit beside what

**Imported:** per-case raw measurements — QPS, latency percentiles,
recall, index build time, load duration — each labelled with the engine,
its version, VectorDBBench's version, and the host it ran on.

**Never imported:** VectorDBBench's composite scores. Its scoring
computes each system's result relative to the best value per case and
takes a geometric mean across cases; a system that fails or times out is
assigned a value twice as bad as the worst observed — half the lowest
QPS, double the maximum latency. That is a couldn't-check rounded into
the scale so an aggregate stays computable. It is a defensible choice for
a leaderboard and the opposite of oneground's rule, and importing it
would import the rounding.

**A failure stays a failure.** A VectorDBBench case that fails or times
out is reported as `couldnt_check` with the reason and the timeout that
fired, never as a low number.

**The table rule.** A VectorDBBench measurement may sit in the same table
as an oneground measurement **only** when both used the same ground
truth, the same query subset and the same corpus digest — which the
export guarantees and the card must assert, not assume. Everything else —
different engine versions, different hosts, their standard cases — is a
separate table with its own heading.

## 5. What this does not become

- **oneground does not vendor, fork or bundle VectorDBBench.** It writes
  the three files and a config, and reads results back. The user installs
  and runs VectorDBBench themselves, exactly as they run their own
  extractor. Same rule as the chunking position: declared, not run.
- **It does not resolve what VectorDBBench cannot.** No architecture
  decision comes back from it, because it does not make one. The
  integration runs one way: oneground decides the architecture on your
  data, then a shortlist is benchmarked across many engines.
- **It does not replace `verify`.** oneground's own attribution rules —
  same environment, same configuration, the round-trip refusal, three
  runs with a spread — apply to oneground's numbers. A VectorDBBench
  number carries VectorDBBench's rules, is labelled as theirs, and is
  never used to settle an oneground constraint.

## 6. The claim this earns

> The architecture was chosen on your corpus, against an answer key
> computed from it. The same corpus, the same queries and the same answer
> key were then handed to an independent benchmark, which measured your
> shortlist across engines we do not maintain.

That is a stronger claim than either tool makes alone, and it costs one
exporter and one importer rather than forty adapters.

## 7. What this position does not settle

- Whether to import their filtered-search and streaming cases, which have
  no oneground equivalent and would need their own comparability rule.
- Whether the export belongs in `report` (the shortlist is known there)
  or as its own command. Probably the latter, since it produces files for
  a tool we do not run.
- The scalar-labels path (`scalar_labels.parquet`, `label_percentages`),
  which VectorDBBench supports for filtered search and oneground has no
  concept of.
- Whether a returned VectorDBBench recall that **disagrees** with
  oneground's own for the same configuration is a finding about the
  engine, about their harness, or about ours. It is at least one of the
  three, and the paper claims nothing about which — but that disagreement
  would be worth more than agreement, and the design should make it
  visible rather than smooth it.

## 8. Sequencing

Not before the UI's read slice, and not before more of oneground's own
adapters exist — the bridge is most valuable when there is a shortlist to
hand over, and least valuable as a substitute for having measured
anything oneself. The first implementation is the **exporter and its
verification**: write the three files, load them back, and assert the
round trip preserves the vectors and the ground truth exactly. The
importer follows.

*The exam, before the code.*
