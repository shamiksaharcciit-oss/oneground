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

Both the column names and the **file stems** are configurable —
`train_id_name`, `train_col_name`, `test_col_name`, `gt_col_name` for the
columns, and `train_name`, `test_name`, `gt_name` (`"train"`, `"test"`,
`"neighbors"`) for the files. oneground adopts every default and renames
nothing.

### The id space: positions, in both files

**`train.parquet.id` and `neighbors.parquet.neighbors_id` carry positions
in the sample array, not source record ids.** This is a ruling, not an
observation, because two self-consistent choices existed and picking one is
what stops half an exporter being written against each.

The reasons, in order: VectorDBBench never sees a source id and has no use
for one — `calc_recall` intersects two sets of integers and asks nothing
about what they name; positions are what `exact_knn` already returns, so
nothing is recomputed or translated; and one id space removes the failure
where one side is translated and the other is not.

**The trap this closes, which would otherwise have shipped.**
`ground_truth.npy` holds indices into the sample array. `sample_ids.json`
holds the source ids of the rows that were sampled. On a run that takes the
whole corpus these are the same list — `arxiv-150k`'s `sample_ids` is
`[0, 1, 2, …]` — so positions and source ids coincide and any exporter
looks correct. On a run that subsamples they diverge completely:

```
stackexchange, 20,000 drawn from 150,000
  sample_ids[:6]           [3, 7, 13, 15, 22, 42]
  ground_truth range       0 .. 19,999        (positions)
  gt position 3,870   ->   sample_ids[3,870]  = source id 29,212
  gt position 12,444  ->   sample_ids[12,444] = source id 93,214
```

An exporter written and tested against `arxiv-150k` alone passes, and is
wrong on every subsampled run — which is most of what a user brings. The
numbers would be correct integers in the wrong space, and recall computed
from them would be a plausible number that means nothing. The same shape as
the cross-document spans in the chunking position: right values, wrong
frame, and no error anywhere to catch it.

**One conversion the exporter must make.** `queries_ids.json` records the
query ids as **strings** — `characterize` writes `[str(q) for q in
query_ids]` — while `sample_ids.json` holds integers and
`test.parquet.id` is declared int. The exporter converts; it does not
assume the two receipts agree on type because they agree on meaning.

### 3.2 Five parameters that must be set, not defaulted

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
- **`use_shuffled`.** Defaults `False`, and it does not merely reorder:
  it changes the **filename prefix** that `compose_train_files` produces,
  from `train` to `shuffle_train`. Left unset it is harmless; set by
  someone reading the config as a performance knob it renames every file
  the export wrote.
- **`with_scalar_labels`.** `CustomDataset` declares it **`True`**, with
  `scalar_labels_file = "scalar_labels.parquet"`. oneground writes no such
  file and has no concept of scalar labels, so the export sets this
  **`False`** explicitly. §7 treats scalar labels as a future question;
  the default reaches into the export today.

**The split-file name is zero-padded, and this paper had it wrong.** An
earlier draft gave the format as `train-[i]-of-[n].parquet`. The source is
`str(i).rjust(2, "0")`, so eight shards are:

```
train-00-of-8.parquet  train-01-of-8.parquet  …  train-07-of-8.parquet
```

An exporter following the earlier wording writes files VectorDBBench will
not find. There is also a **second naming path** the draft did not mention:
`CustomDataset.train_files` uses `compose_train_files` only when
`"," not in train_file and file_num > 1`; otherwise it splits `train_file`
on commas and appends `.parquet` to each stem. Two mechanisms produce the
train file list, and an export that writes one and configures the other
loads nothing.

### 3.3 The query set is a declared subset

VectorDBBench copies the full query set into every concurrent process, so
it recommends around 1,000 test vectors. oneground's fixtures use 2,000.
The export therefore takes a **seeded subset**, declared with its seed and
its size, and the ground truth is subset to match. A run against 1,000 of
2,000 queries is not the same run as one against all of them, and the
card says which.

**Today's receipts cannot express that, and this section read as though
they could.** `queries_ids.json` records the whole query set;
`characterization.json` records `n_queries` as a scalar. Nothing records a
subset — no seed, no size, no selection — because no oneground command has
ever taken one. So a card written from the receipts as they stand cannot
say which 1,000 of 2,000 were used.

What must be added, in shapes the tree already has rather than new ones:
the subset's **seed and size recorded** the way `sampling` is recorded for
the corpus, and the **selected ids written as a receipt** the way
`queries_ids.json` writes the full set. Both are additive and neither
recomputes anything. Until they exist, the export cannot honestly subset,
and an export that subsets without them is producing a run nobody can
identify afterwards.

## 4. What comes back, and what may sit beside what

**This section named what comes back without having read the file it
comes back in, and task 055 corrected it against the source rather than
building past the gap.** `vectordb-bench==2.0.0` writes one JSON file per
provider run, `results/<Provider>/result_<date>_<label>_<provider>.json`
— a `TestResult`: `run_id`, `task_label`, and `results`, a list of
`CaseResult`. Each case carries `metrics` (`Metric`'s own fields — `qps`,
`serial_latency_p50/p95/p99`, `recall`, `ndcg`, `load_duration`,
`insert_duration`, `optimize_duration`, `max_load_count`, among others),
`task_config` (which engine, `db`; its `db_config.version`, when the
config declares one; the case and stage configuration), and `label` —
`":)"` for a normal case, `"x"` (`ResultLabel.FAILED`) or `"?"`
(`ResultLabel.OUTOFRANGE`) otherwise.

**Imported:** per-case raw measurements — QPS, latency percentiles,
recall, index build time, load duration — labelled with the engine
(`task_config.db`) and its version (`task_config.db_config.version`,
when present).

**Two of the four labels this section originally named are not in the
file at all.** Neither VectorDBBench's own package version nor the host
it ran on appears anywhere in `TestResult`, `CaseResult` or `TaskConfig`
— not in the schema, not in any of the real result files shipped in the
package itself. Read `null`, with the reason stated, the shape §2.1 of
`docs/PROPOSALS.md` already uses for a model version a provider does not
report: declared absent rather than guessed or silently dropped.

**Never imported:** VectorDBBench's composite scores. Its scoring
computes each system's result relative to the best value per case and
takes a geometric mean across cases; a system that fails or times out is
assigned a value twice as bad as the worst observed — half the lowest
QPS, double the maximum latency. That is a couldn't-check rounded into
the scale so an aggregate stays computable. It is a defensible choice for
a leaderboard and the opposite of oneground's rule, and importing it
would import the rounding. **No per-case result file contains one to
exclude** — the composite is computed downstream, across every
provider's file at once, by the package's own leaderboard script, never
persisted beside the raw numbers a single result file carries. The
exclusion this position calls for is satisfied by scope — the importer
reads one provider's result file and never opens a leaderboard file —
not by filtering a field out of what it reads.

**A failure stays a failure, and this section overstated what the file
says about why.** A VectorDBBench case that fails or times out is
reported as `couldnt_check`, never as a low number — that much holds.
What does not: **VectorDBBench's own runner catches the exception, logs
it, and discards it** (`interface.py::_async_task_v2`); only the `label`
survives to the file. A captured `LoadTimeoutError` or
`PerformanceTimeoutError` writes `"?"`; any other exception writes
`"x"`. Neither carries a reason string, and neither carries the duration
the process actually ran before it gave up — that information exists
only in that run's console output, which oneground never sees, because
oneground does not run VectorDBBench (§5). What the file *does* still
let a reader ask: which of the two kinds of failure occurred, and —
where the case's own configuration declares one — the *configured*
timeout for the search-concurrency stage (`case_config.
concurrency_search_config.concurrency_timeout`). That is the configured
value for one stage, not *the* timeout that fired; nothing in the file
says which stage's timeout ended the case, or distinguishes a load
timeout from a search one.

**The table rule.** A VectorDBBench measurement may sit in the same table
as an oneground measurement **only** when both used the same ground
truth, the same query subset and the same corpus digest — which the
export guarantees and the card must assert, not assume. Everything else —
different engine versions, different hosts, their standard cases — is a
separate table with its own heading.

**The claim invariant cannot enforce this**, for the same reason it cannot
catch the hybrid position's ground-truth trap: 019 checks that a sentence
follows from the rows it cites, and the *provenance* of a row — which
ground truth, which query subset, which corpus — is not one of its inputs.
A VectorDBBench row and an oneground row placed in one table would each be
individually true of themselves, and the invariant would pass the table.

So the rule is structural, and refused at construction on 026's and 034's
pattern:

> **A row belongs to the ground truth, the query subset and the corpus
> digest it was measured against.** Two rows may share a table only when
> all three match. A table that cannot be built cannot be rendered, and no
> reviewer has to notice.

**The verdict now exists, and the structural refusal is still needed.**
`docs/LIBRARY.md` §2.2's three-valued verdict is implemented in
`oneground/comparability.py` — by task 041 at run level, extended by 043 to
rows via `rows_may_share_a_table`, which carries exactly the two lists this
section's rule turns on.

That does **not** retire the refusal above, and the distinction matters. The
verdict answers *may these two rows share a table*; it cannot prevent a table
being built from rows that may not. 019's invariant still cannot enforce it,
for the reason given: a row's provenance is not one of its inputs. So the rule
stays structural — **refused at construction, with the verdict as what the
construction consults** rather than as a substitute for it.

**One ingredient this paper needs is still absent.** `rows_may_share_a_table`
declares `query_subset` and it is always `None`, because §3.3 above records
that no receipt expresses it — no seed, no size, no selection. Declared rather
than omitted, so a comparison over it is `couldnt_check` and visibly so. Until
that receipt exists, **two rows can never be `comparable` under this rule**,
only `couldnt_check` — which is the honest state and is worth knowing before
anyone builds the exporter expecting a green verdict.

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

**Before starting the exporter, know that the table rule cannot pass yet.**
`comparability.rows_may_share_a_table` is implemented (task 043) and today it
can return `not_comparable` or `couldnt_check` and **never `comparable`** —
because `query_subset` is one of the three things a row must agree about, no
receipt expresses it (§3.3), and an ingredient that is always unknown makes
the verdict couldn't-check however well everything else matches.

That is not a defect in the rule and it is not a reason to weaken it. It means
**§3.3's receipt is a prerequisite of the exporter, not a companion to it**:
build the query-subset seed and selection receipt first, or the exporter will
produce files whose rows the project's own rule cannot admit to a table. An
implementer who discovers this from the code rather than from here will have
written the exporter already.

*The exam, before the code.*
