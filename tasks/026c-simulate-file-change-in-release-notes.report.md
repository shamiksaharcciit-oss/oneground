# Report: 026c-simulate-file-change-in-release-notes

## Repo state expected vs found

`main` at `75cee24` (026b), clean apart from `tasks/020-simulator-state.md`:
found. `v0.1.0` on `872e7a6`, not moved.

## What was done

`RELEASE_NOTES.md`, in the same entry as 026b's (*Configurations are validated
against each family's declared parameters*), gains the file change:

- `simulate.json` rows for `single_node_hnsw` and `hash_sharded` no longer list
  `shard_depth` in their `params`, because neither family ever read it;
- so a `0.1.0` run of the same configuration writes a different file from a
  preview run, while no number and no label moved;
- both fixtures were recomputed on this code under the pinned versions, and
  every value `fixture verify` recomputes reproduced: 8 of 8 for `arxiv-150k`
  and 8 of 8 for `stackexchange-150k`, each inside its published tolerance.

The sentence says "every value `fixture verify` recomputes", not "every
published value". Each fixture publishes four more (the semantic-sharded
routing ceiling and copy percentiles) that the command does not recompute, as
026 made its summary say.

## Measurements

Both runs from the checkout at `75cee24`, with the release-notes edit
uncommitted in the working tree, under the project venv (numpy 2.5.3,
faiss-cpu 1.15.0, scikit-learn 1.9.0: pinned). `--asset` pointed at this
machine's extracted asset folder for each fixture. About 450 MB of physical
memory was free at the start.

| fixture | values | digests | wall clock |
|---|---|---|---|
| `arxiv-150k` | **8 verified**, 0 contradicted, 0 couldnt_check | 17 verified | 18 m 18 s |
| `stackexchange-150k` | **8 verified**, 0 contradicted, 0 couldnt_check | 11 verified | 24 m 35 s |

Every value line, as printed:

```
$ oneground fixture verify arxiv-150k --asset <this machine's extracted asset>
values
  verified      intrinsic_dimensionality                recomputed 32.5533, published 32.55, delta 0.00325699, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0362467, published 0.036, delta 0.000246667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0754, published 0.075, delta 0.0004, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.8915, published 0.891, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.523212, published 0.522, delta 0.00121244; after recomputed 0.551401, published 0.549, delta 0.00240097; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9968, published 0.997, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.9318, published 0.932, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.71516, published 3.715, delta 0.00016, tolerance 0.01
```

```
$ oneground fixture verify stackexchange-150k --asset <this machine's extracted asset>
values
  verified      intrinsic_dimensionality                recomputed 37.4635, published 37.46, delta 0.00349716, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0114467, published 0.011, delta 0.000446667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0693533, published 0.069, delta 0.000353333, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.9085, published 0.908, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.483067, published 0.485, delta 0.00193321; after recomputed 0.451868, published 0.45, delta 0.00186766; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9938, published 0.994, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.86835, published 0.869, delta 0.00065, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.89743, published 3.897, delta 0.000433333, tolerance 0.01
```

## Verification

- The parameter-list change is in `RELEASE_NOTES.md`, under the same entry:
  done.
- Both fixtures' recomputed values reproduce, numbers not bytes: 16 of 16
  verified, above.
- `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED. The test holding
  `RELEASE_ASSETS` to the release notes: passed. Identifier scan with this
  report staged: 0 findings.

Suite not re-run: this commit changes only `RELEASE_NOTES.md` and adds this
report. The suite passed at 871 on `75cee24`.

## Observed, not done — a decision for the developer

**`stackexchange-150k`'s two semantic-sharded values reproduced on this
machine for the first time.** `semantic_sharded.recall_at_10` recomputed
0.86835 against a published 0.869; `.storage_amplification` 3.89743 against
3.897; both inside the 0.01 tolerance. When the fixture was published this
machine ran out of memory recomputing them, which is why
`fixtures/stackexchange-150k.fixture.yaml` carries `status: built` and not
`verified`.

Several documents say those two are couldn't-check "on the machine that cut
this release":
- `RELEASE_NOTES.md`'s *On the machine that cut this release* block;
- `docs/FIXTURES.md`;
- `docs/EXTERNAL_RUN.md`.

Those statements are historical and were true when written; nothing here
changes them. **Whether this run moves `stackexchange-150k` to `status:
verified` is a fixture-spec change and yours.** The facts that bear on it:
- the fixture was built on a Linux pod with a CUDA GPU (`build_info.json`:
  platform Linux-6.8.0, device cuda, NVIDIA RTX PRO 4500 Blackwell, session
  `20260912-100920`);
- this run is on this Windows laptop, a second machine, under the same pins;
- that is the bar `arxiv-150k` met for `verified`: built on Linux with CUDA,
  reproduced on Windows.

Before this run, six of the eight had reproduced here and two could not be
recomputed. Now all eight have.

## Repo now contains

    RELEASE_NOTES.md                                             the file-change sentence and the recompute result
    tasks/026c-simulate-file-change-in-release-notes.report.md   this report

## Blocked on developer

1. Retag `v0.1.0` at this commit (subject `task 026c:`) and rebuild.
2. Decide on `stackexchange-150k`'s status, above.
