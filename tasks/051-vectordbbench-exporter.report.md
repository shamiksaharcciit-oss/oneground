# Report: 051-vectordbbench-exporter

## Repo state expected vs found

Expected `main` at `693f1bb` (task 050's merge) with `docs/BRIDGE.md` as
the reviewed spec and nothing built against it yet. Found exactly that.

## What was done

**§3.3 built first, as its own prerequisite.** `oneground/bridge/
query_subset.py`: `select(n_available, size, seed)` is `loaders.subsample`'s
own method (`np.random.default_rng(seed).choice(...).sort()`) applied to
the query array instead of the corpus; `write()` records seed, size,
`n_available`, the selected positions and the ids at those positions in
one receipt, `query_subset.json`, refusing to overwrite an existing one —
`write_prediction`'s discipline, not characterize's own multi-file
convention, because this receipt is written by a separate call after
characterize has already finished and closed its own manifest.

**The exporter.** `oneground/bridge/export.py::export()`. Re-derives the
sample and the full query set from the paths the requirements file names
(`characterize` never writes vectors back to disk — confirmed by reading
its `run()` in full before writing anything here) using the same
`_sample_indices()` reconstruction `simulate` already uses, rather than a
second implementation of it. Writes `train*.parquet` (single file or
zero-padded shards), `test.parquet`, `neighbors.parquet`, and a card
(`vdbbench_card.json`) with the five parameters set explicitly.

**The rulings, followed rather than re-derived:**

- **Positions, in both files.** `train.parquet.id` is `0..n_base-1`;
  `neighbors.parquet.neighbors_id` is exactly what `exact_knn` returns —
  positions into `base`, never `sample_ids.json`'s source ids. Proven by
  the test that exercises the actual trap: a subsampled run (300 of 2,000)
  whose `sample_ids.json` genuinely diverges from `0..299`, asserting the
  written ids are the positions and the vectors at those positions are the
  right ones (`test_ids_are_positions_in_the_sample_not_source_ids`).
- **The five explicit parameters** — `metric_type: "IP"` (the ground
  truth is inner product over already-normalized vectors, stated as fact
  rather than either of `CustomDatasetConfig`'s two disagreeing defaults),
  `with_gt: true`, `use_shuffled: false`, `with_scalar_labels: false`
  (`CustomDataset` itself defaults this `true`; oneground writes no scalar
  labels, so this is a correction, not a restatement), `file_count` —
  always written, asserted in `test_the_card_states_the_five_parameters_
  explicitly`.
- **Zero-padded shard naming.** `_shard_names()`: `train.parquet` alone
  for `file_count == 1`; `train-00-of-N.parquet` (`str(i).rjust(2, "0")`)
  for more than one — not `train-[i]-of-[n]`, the earlier draft's wording
  the position paper itself corrected. `test_shards_are_zero_padded_two_
  digits` asserts the literal names, including that `[` appears nowhere.
- **The query subset, declared with its seed** — every export call writes
  `query_subset.json` before computing anything from it; there is no path
  through `export()` that skips it.

**One conversion the paper named and I had to decide how to enforce.**
`queries_ids.json` holds strings; `test.parquet.id` is declared int. The
exporter casts each selected query's id to int for both `test.parquet.id`
and `neighbors.parquet.id` (which must match it) — and where a query's id
is not numeric (an arbitrary string id from a `.jsonl` source, which the
paper's own conversion note does not explicitly cover), `export()` refuses
by name rather than inventing a position. This is my own extension of the
ruling to a case the position paper states the fact of but does not settle
the failure mode for; flagged here rather than presented as something
`docs/BRIDGE.md` already decided.

## Measurements

None the way task 048/049 mean the word — this task built a tool and
verified it, and the round-trip assertions below are the closest
equivalent: exact equality, not a tolerance.

## Verification

`oneground/bridge/` — 19 tests, all green: 8 in `test_query_subset.py`, 11
in `test_export.py`, covering the round trip, the id-space trap, the
naming, the card, the subset receipt's own discipline, and four refusals
(no characterize run, a subset larger than available, an id that will not
cast to int, writing the same subset twice).

**A real defect the round-trip test caught, before this was reported.**
The first version of `_write_vector_table` built pyarrow list columns via
`pa.array([row.tolist() for row in vectors])` — `.tolist()` promotes each
float32 value to a Python `float` (float64) before pyarrow narrows it back
down, and the two ends of that detour are not always bit-identical.
`test_the_three_files_round_trip_the_vectors_and_the_ground_truth` failed
on values differing in the seventh decimal place — small enough to look
like display noise, large enough that "the round trip preserves the
vectors... exactly" (§8) was not true. Fixed by building the list column
from the array's own flattened bytes (`_list_column`, `pa.ListArray.
from_arrays` over a `pa.array` built directly from the numpy buffer),
which is now what every vector and neighbour-id column goes through.

**Two more, caught by the full suite rather than by anything in `oneground/
bridge/` itself.** `oneground/receipts/test_pathguard.py` refused the
card's `requirements_file.path` and `query_subset.path` — both flagged by
name (`PATH_KEY`) as fields that had not gone through `receipts.
public_path`/`public_paths_in`, whatever their actual value. Wrapped both
in `public_paths_in(...)`, the established idiom (`oneground/report/
__init__.py`'s `price_table` field), rather than judging a bare filename
like `query_subset.json` safe enough to skip the sanitiser the static
guard cannot see the value to verify. `oneground/test_invocation.py`
refused both new `"oneground": producing_version()` sites for carrying no
`"invocation"` beside them — the project-wide pairing convention the
report on characterize's own artifacts (task 049's research) had already
named; both receipts now carry it. That same test pins the total count of
paired sites at an exact number, by design ("a writer that was forgotten
is exactly the failure this cannot tolerate") — updated from 12 to 14 for
this task's two legitimate new ones, in `oneground/test_invocation.py`
itself.

Full suite, guard, identifier scan and `site/teaser/` — reported alongside
the merge, per the established pattern.

## Observed, not done

**No CLI command.** `docs/BRIDGE.md` §7 leaves "does the export belong in
`report` or as its own command" explicitly unsettled ("probably the
latter"). `export()` is a library function, callable and tested; adding a
command decides a question the position paper does not, so it is not
added here.

**`comparability.py`'s `query_subset` field is still always `None`.**
Wiring the card's `query_subset` block into `rows_may_share_a_table` was
never this task's job (§8: "the exporter and its verification. The
importer follows") and §4's own warning stands — an export produced today
still cannot be admitted to a comparability-checked table. The card
records enough (seed, size, sha256) that a future task could wire it in
without re-deriving the shape; it does not do so itself.

**The importer.** Not built, per §8's own sequencing and the instruction.

**`metric_type: "IP"`, not independently verified against a live
VectorDBBench install.** `vectordb-bench` is not installed in this
environment and is not a project dependency (§5: oneground vendors
nothing). The value follows §3.2's stated fact — "oneground's vectors are
normalised and its ground truth is inner product" — literally, but I could
not cross-check it against `MetricType`'s actual enum spelling the way
`docs/BRIDGE.md`'s own author apparently did against the downloaded
source. One web lookup against a public mirror of `vectordb_bench/backend/
dataset.py` returned field names (`train_id_field`, `test_file`, `gt_file`,
...) that do not match `docs/BRIDGE.md`'s own prose (`train_id_name`,
`test_name`, `gt_name`, ...) closely enough to trust as a correction — it
may be a different version, or an imprecise summary, and I did not treat
either document as authoritative over the other. The card writes what
`docs/BRIDGE.md` states as file-level facts (file names, column names,
the five parameters) and does not attempt to construct a live
`CustomDatasetConfig` object, which is the user's own step when they
install VectorDBBench themselves (§5).

## Repo now contains

New:

- `oneground/bridge/__init__.py`, `query_subset.py`, `export.py`
- `oneground/bridge/test_query_subset.py`, `test_export.py`
- `tasks/051-vectordbbench-exporter.report.md` — this file

Changed:

- `oneground/test_invocation.py` — the pinned writer-site count, 12 to 14

## Blocked on developer

Nothing. Committing, pushing to `task-051`, and merging into `main` once
its checks are green, per standing instruction.
