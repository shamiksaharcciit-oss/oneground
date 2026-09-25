# Report: 055-vectordbbench-importer

## Repo state expected vs found

Expected `main` at `fa68894` (the recorded-finding merge) with the exporter
and its round-trip verification done (task 051) and no importer anywhere in
`oneground/bridge/`. Found exactly that; branch `task-055` created from
`main` at that commit.

## What was done

**Item 1's research, first, and it changed items 3, 4 and part of item 5.**
`vectordb-bench==2.0.0` was downloaded from PyPI (cached locally already, the
same copy `docs/BRIDGE.md`'s own research used) and read directly —
`vectordb_bench/models.py`'s `TestResult`/`CaseResult`/`Metric`,
`vectordb_bench/interface.py::_async_task_v2` (where a case's outcome is
decided), and the real result files the package ships under
`vectordb_bench/results/*/result_*.json`. Three things the position paper
said about what comes back do not hold against the source, and the brief and
`docs/BRIDGE.md` §4 are both corrected here rather than worked around:

1. **No composite score is ever in a per-case result file.** It is computed
   downstream, across every provider's file at once, by the package's own
   `results/getLeaderboardData.py` and its frontend scoring code — never
   persisted beside the raw numbers a single result file carries. "Never
   import the composite" turned out to be a scope statement, not a
   field-level filter: the importer reads one provider's result file and
   never opens a leaderboard file, so there is no composite present to
   exclude in the first place.
2. **A failure or timeout carries no reason string and no captured
   duration.** `_async_task_v2` catches the exception, logs it
   (`log.warning`), and discards it — only a `label` survives to the file:
   `"?"` (`ResultLabel.OUTOFRANGE`) for a caught `LoadTimeoutError` or
   `PerformanceTimeoutError`, `"x"` (`ResultLabel.FAILED`) for anything
   else. Confirmed against real shipped files: every non-normal case in
   `results/Milvus/result_20230727_standard_milvus.json` and others carries
   `qps: 0, recall: 0` and a label, nothing more. The brief's item 3 asked
   for "the specific timeout value that fired," which the file does not
   contain; the importer reports which of the two failure *kinds* occurred
   and, where the case's own configuration declares a concurrency-search
   timeout (`case_config.concurrency_search_config.concurrency_timeout`),
   names that as the configured value for that one stage — not as the
   timeout that fired, which nothing in the file distinguishes from a
   load-stage timeout.
3. **VectorDBBench's own version and the host it ran on are not recorded
   anywhere.** Not in `TestResult`, not in `CaseResult`, not in
   `TaskConfig`, not in any real result file the package ships. The brief's
   item 4 asked for both as required labels; they are `null` with a stated
   reason on every row instead — the same shape `docs/PROPOSALS.md` §2.1
   already uses for a model version a provider does not report.

**`docs/BRIDGE.md` §4 corrected to match**, with the file format and schema
this research found (the exact file path pattern, `TestResult`/`CaseResult`
field names, and the label values), and the three points above stated where
the section previously overclaimed.

**The importer**, `oneground/bridge/import_result.py`:

- `read_result_file(path)` — loads one `result_*.json`, refuses (named) a
  missing file, invalid JSON, or a file not shaped like a `TestResult`.
- `import_case(case_result)` — one `CaseResult` to one row: raw numbers
  (`qps`, `serial_latency_p50/p95/p99`, `recall`, `ndcg`, `load_duration`,
  `insert_duration`, `optimize_duration`, `max_load_count`) named by field,
  never the whole `metrics` dict, on a normal case; `couldnt_check` with the
  reason and the configured concurrency timeout (or `null`, named) on a
  failed or timed-out one. `vectordbbench_version` and `host` are `null`
  with a stated reason on every row.
- `provenance_from_card(card)` — the three-key provenance (ground truth,
  query subset, corpus/requirements digest) a bridge row carries, read from
  the exporter's own `vdbbench_card.json`. The ground truth digest is
  `neighbors.parquet`'s own sha256 from the card's `files`, not a
  description of it; the query subset digest is the seeded receipt task 051
  added — closing the gap `docs/BRIDGE.md` §4 flagged as "still absent" —
  and this is the first place that receipt is read rather than only
  written.
- `assemble_table(rows_with_provenance)` — §4's table rule, refused at
  construction: there is no code path that returns a table this function
  has not itself checked every row of against the first.

**One design correction found while building item 5, reported rather than
built past.** The brief's item 5 named `oneground.comparability.
rows_may_share_a_table` as the function to consult for the table-rule
verdict. It is the wrong function. `rows_may_share_a_table` requires two
axes to agree: `measured` (sample, ground truth, query subset — exactly
§4's three keys) *and* `measuring` (oneground's own code, libraries,
platform, python version, machine). A VectorDBBench row was not measured by
oneground and has no `measuring` half — every one of those five keys reads
`unknown` on the bridge side regardless of what `measured` says, which
makes that function's `comparable` branch **unreachable for any table a
bridge row is in**. Using it as written would have made `assemble_table`
refuse every bridge table unconditionally — a defect that would not have
shown up in a same-run round-trip test unless that test specifically
checked for `comparable` rather than merely "no exception," which is why
this is called out here rather than left to be found later. `assemble_table`
instead reimplements only the three keys §4's own blockquote names, reusing
`MEASURED_KEYS` and `oneground.comparability`'s same/differs/unknown
primitives rather than inventing a second comparison — the three-valued
*meaning* is not duplicated, only which keys are asked about is narrower,
and that narrowing is what §4 actually specifies.

**Path B's line, folded in as one sentence** (per developer instruction,
kept out of a separate commit): `docs/CHUNKING.md`'s path-A/path-B table now
carries a note that `sentence`'s `self_recall@5`/`containing_hit@5` predate
task 054's floor unification and were not re-measured — `fixed` and
`structure`, the two strategies the table's headline finding compares,
produced bit-identical chunks before and after, so nothing the table
concludes depends on that column being current.

## Measurements

- 37 of 37 tests pass in `oneground/bridge/` (18 new in
  `test_import_result.py`, 19 existing in `test_export.py` and
  `test_query_subset.py`, unaffected).
- Three real mutants, each proven by a failing-then-passing assertion:
  `test_a_composite_score_field_is_never_imported` (a synthetic
  `composite_score` key injected into a fixture's `metrics`, absent from the
  import); `test_a_failed_case_imports_as_couldnt_check_not_a_number` and
  its timeout sibling (a fixture per label, asserting `couldnt_check` and
  the specific reason text per label); `test_rows_with_a_different_ground_truth_refuse_construction`
  and its query-subset sibling (two provenances differing on one of the
  three keys, `assemble_table` raising named).
- A fourth mutant for the design correction above:
  `test_matching_bridge_rows_assemble_despite_carrying_no_measuring_facts`
  asserts `rows_may_share_a_table` itself returns something other than
  `"comparable"` for two identical bridge provenances (proving the
  unreachability claim is real, not asserted), then asserts
  `assemble_table` still succeeds — if a future edit reintroduces the
  broader function as the guard, this test fails.
- Fixtures are shaped from the real schema this task's research found (field
  names, the `":)"`/`"x"`/`"?"` label values, the `concurrency_search_config`
  nesting), not invented independently of it.

## Verification

Full suite: pending, running now on this branch (see below). `oneground/
test_environment.py`, `identifier_findings()` and the `site/teaser/` diff:
pending the same run, reported at the merge per the established pattern.

## Observed, not done

**No CLI command**, per the brief's "Do not" and §7's own open question
about where the export/import pair belongs — a caller reaches
`import_result.read_result_file`/`assemble_table` as library functions,
exactly as `export()` is reached today.

**The load-stage timeout's configured value is not reported at all**, only
the search-concurrency one. VectorDBBench's `LoadTimeoutError` is
constructed with a duration (`models.py`'s own `LoadTimeoutError.__init__`
takes one), but that duration is not part of `TaskConfig`'s persisted
schema the way `concurrency_search_config.concurrency_timeout` is — it
comes from a global constant (`CONCURRENCY_TIMEOUT = 3600` in the package's
`__init__.py`) the result file never repeats. Naming it would mean either
hardcoding VectorDBBench's own default into this importer (a defect this
paper's own §3.2 already warns against — an assumed default silently
disagreeing with a real one) or leaving it `null` with a reason, which is
what `import_case` currently omits rather than adds. Worth a small follow-up
if a load-timeout case turns out to matter in practice; not added
speculatively here.

## Repo now contains

Changed:

- `docs/BRIDGE.md` — §4 rewritten with the real result-file schema and the
  three corrections above
- `docs/CHUNKING.md` — one sentence noting `sentence`'s path-B columns
  predate task 054 and were not re-measured
- `oneground/bridge/__init__.py` — docstring updated to name the importer
- `tasks/055-vectordbbench-importer.md` — items 3, 4 and 5 annotated with
  what item 1's research corrected, in place rather than silently reworked

New:

- `oneground/bridge/import_result.py` — the importer
- `oneground/bridge/test_import_result.py` — 18 tests, four of them mutants
- `tasks/055-vectordbbench-importer.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-055`, and merging into `main` once its
checks are green, per standing instruction.
