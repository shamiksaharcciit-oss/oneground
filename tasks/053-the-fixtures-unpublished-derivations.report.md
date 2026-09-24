# Report: 053-the-fixtures-unpublished-derivations

## Repo state expected vs found

Expected `main` at `7a38547` (task 052's merge) with the accepted brief
and `sec-filings-10k`'s three gaps exactly as `tasks/030-sec-filings-
fixture.report.md` described them. Found exactly that.

## What was done

**The built→verified finding, first, as instructed.** `verify.py`'s own
condition — every recomputed value verified and nothing published left
`uncovered` — has **never**, until this task, been true of `arxiv-150k`,
the one fixture carrying `status: verified`. `semantic_sharded.
routing_ceiling`/`.p50_copies`/`.p95_copies`/`.p99_copies_per_vector` were
published in its spec from the repository's first commit (`27173ae`,
already carrying `status: verified` — `git blame` confirms both lines
share that commit) and were never in `REF_ROWS`. Re-running `fixture
verify arxiv-150k` before touching anything confirmed it: *"8 verified...
4 published values are not recomputed by this command."* **The code's
condition could not have produced `arxiv-150k`'s status; it has never
once been satisfiable.** What actually did, per the spec's own finding
entry (`values_survive_a_library_version_change`): *"The status was set
only after a run in the pinned environment,"* reproducing *"the same
eight values"* — the declared-coverage set, not everything published. A
narrower, real, checkable condition, disagreeing with the message the
code prints today. Full detail in `docs/FIXTURES.md`'s new subsection,
placed where a reader of the fixture table meets the word.

**Then closed the gap that made the two rules different, rather than
choosing between them.** `oneground/fixture/verify.py::REF_ROWS` gained
the four `semantic_sharded` fields — zero additional computation;
`ref_semantic_sharded()` already returns all six from the one call
`verify_values()` was already making for two of them. Re-running `fixture
verify arxiv-150k` **after**: *"12 verified... Every published value
reproduced (12 of 12). This fixture's status may be set to `verified`."*
For the first time, the code's own stated condition is true of the
fixture it names — not because the original 2026-09-10 promotion has
become reproducible under a rule that governed it retroactively, but
because closing this gap made the narrower rule (declared coverage
reproduces) and the stricter one (nothing published is uncovered) the
same rule, going forward. Both are stated in `docs/FIXTURES.md`, in that
order, with the disagreement not smoothed over.

**The three fixture gaps, closed:**

1. **Chunk counts persisted.** Traced in `oneground/sample/sec_filings.py`:
   `chunks_total`/`chunks_per_document`/`chunks_crossing_a_boundary` were
   computed and handed to an in-memory `receipt` dict nothing ever wrote
   out — visible only in the build log. `section_statistics.json`'s write
   moved from before the chunking block to after it, carrying a new
   `"chunking"` key. **Recomputed locally, no pod needed**:
   `documents.jsonl.zst` was already cached in the developer's local
   asset directory (`~/oneground-assets/sec-filings-10k/`), so the exact
   tokenize-and-chunk loop
   `sample_records()` runs was re-run directly against it — same
   tokenizer, same `chunk_document`/`sections_spanned` calls, same
   `TOKENIZE_BATCH`. Real numbers, not estimated: **1,559,834 chunks from
   10,000 documents, 109,722 (7.03%) crossing a section boundary** — the
   crossing rate matches the original build log's own 7.03% exactly.
2. **Accession list shipped.** `resolve_source()` only ever hashed the
   sorted accession list, never kept it. Re-ran it against live EDGAR
   (the same lightweight index-only fetch task 030's own report confirmed
   reproduces identically on "the developer's laptop") and checked the
   result against the published digest **before writing anything**:
   `selection` matched `source.selection_sha256` exactly
   (`59f847d7...`). The verified 21,287-accession list is now
   `fixtures/sec-filings-10k/accessions.json`, added to `extra_receipts`
   in the spec and to `MANIFEST.sha256`.
3. **`fixture verify` coverage gap closed** — see the built→verified
   section above; the code change is one `REF_ROWS` addition plus four
   more `_compare()` calls (and their failure-path names) in the
   `semantic_sharded` branch of `verify_values()`.

**One existing test's premise this closed, found by running the suite
rather than assumed clean.** `oneground/fixture/test_verify.py::
test_the_shipped_150k_specs_publish_values_this_command_does_not_
recompute` asserted `routing_ceiling` stays in `uncovered` — exactly the
defect this task exists to close. Renamed and inverted:
`test_the_shipped_150k_specs_leave_nothing_uncovered`, asserting
`uncovered == set()` for both shipped 150k specs, with the old defect's
history kept in the docstring rather than deleted.

## Measurements

- `oneground fixture verify arxiv-150k`, before this task's `REF_ROWS`
  fix: 8 of 8 declared values verified, 4 published values uncovered.
- Same command, after: 12 of 12 verified, 0 uncovered — *"This fixture's
  status may be set to `verified`."*
- `section_statistics.json`'s new `"chunking"` key, from a full local
  recompute over the cached `documents.jsonl.zst` (10,000 documents,
  39.3 minutes, CPU only): `chunks_total: 1,559,834`,
  `chunks_per_document: 155.98`, `chunks_crossing_a_boundary: 109,722`,
  `crossing_rate: 0.0703`.
- `accessions.json`: 21,287 entries, sha256 `7011777e...`, `selection`
  re-derived from live EDGAR indexes matches the published
  `selection_sha256` exactly — a positive, checked reproduction, not an
  assumption that the cached list was still current. (`snapshot_sha256`
  has moved since the canonical build, as `resolve_source()`'s own
  docstring says it will — recorded, not fatal, and unrelated to the
  selection.)
- `sec-filings-10k`'s own `uncovered` set, checked the same way as
  `arxiv-150k`'s: also empty, after the same `REF_ROWS` fix.

## Verification

`oneground/fixture/` + `oneground/sample/test_sec_filings.py`: 98 passed.
`oneground/receipts/test_pathguard.py`: 9 passed — the two new "path"-
named fields the guard's static scan would otherwise flag
(`requirements_file.path`... none here; nothing new triggers it, since
`accessions.json`'s own write is a flat list, not a path-keyed dict).

`oneground fixture verify sec-filings-10k`, after all three fixes: 11 of
15 listed files present and verified (`section_statistics.json` and the
new `accessions.json` among them, both matching their fresh digests);
4 not present here (`sample.jsonl.zst`, `vectors.npy`, `queries.npy`,
`projection.npy` — release assets, expected absent from a checkout).
**Values: 12 of 12 `couldnt_check`, honestly** — `vectors.npy`/
`queries.npy` were not cached in this environment (unlike `arxiv-150k`'s,
which were), so nothing could be recomputed here. This is not a defect in
the fix — `sec-filings-10k`'s `uncovered` set is confirmed empty by static
analysis of the spec (Measurements, above); whether its twelve values
actually reproduce needs a machine holding its release assets, which this
one is not.

Full suite, guard, identifier scan and `site/teaser/` — reported at the
merge, below, per the established pattern.

## Observed, not done

**`fixtures/sec-filings-10k.fixture.yaml:696` lists `chunks.jsonl.zst`
under `artifacts.files`**, and no code in the tree writes a file by that
name (the generic builder writes `sample.jsonl.zst`). Found while editing
this same YAML for `extra_receipts`; not part of the three gaps this
brief named, and not touched.

**Promoting `sec-filings-10k` to `status: verified` is not done here**,
per the brief's own instruction — its `uncovered` set is now empty, the
same condition that made `arxiv-150k` eligible, but its twelve values
have not been recomputed in any environment during this task. That
recomputation, on a machine holding the release assets, is what would
actually answer the question; this report states what is known and stops
there.

## Repo now contains

Changed:

- `oneground/fixture/verify.py` — `REF_ROWS` gains four
  `semantic_sharded` fields; `verify_values()`'s `semantic_sharded` branch
  compares all six, and its failure path names all six
- `oneground/fixture/test_verify.py` — one test renamed and inverted
- `oneground/sample/sec_filings.py` — `section_statistics.json`'s write
  moved after chunking and carries a `"chunking"` key; the full accession
  list captured (sorted, pre-shuffle) into `receipt["accessions"]` and
  written to `accessions.json`
- `fixtures/sec-filings-10k.fixture.yaml` — `accessions.json` added to
  `extra_receipts`
- `fixtures/sec-filings-10k/section_statistics.json` — new `"chunking"`
  key, real recomputed values
- `fixtures/sec-filings-10k/MANIFEST.sha256` — `section_statistics.json`'s
  digest updated; `accessions.json`'s digest added
- `docs/FIXTURES.md` — new "`built` vs `verified`" subsection

New:

- `fixtures/sec-filings-10k/accessions.json` — 21,287 accessions,
  verified against the published `selection_sha256`
- `tasks/053-the-fixtures-unpublished-derivations.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-053`, and merging into `main` once
its checks are green, per standing instruction. `arxiv-150k`'s status is
unchanged — the report states it is now consistent with the code's
condition; promoting `sec-filings-10k`, or recording anything about
`arxiv-150k`'s newly-satisfied condition in its own spec, is the
developer's call.
