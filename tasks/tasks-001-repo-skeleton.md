# Task 001 — Repo skeleton and fixture pipeline dry run

## Expected repo state
An empty or near-empty directory containing only: CLAUDE.md, this brief,
`build_fixture.py`, `arxiv-150k.fixture.yaml`. If anything else is present,
list it in the report before proceeding.

## Goal
Stand up the repository layout from CLAUDE.md, place the fixture tooling in
its home, and prove the fixture pipeline runs end to end on a small synthetic
source — so the real build on RunPod (task 002) is a single command.

## Do
1. Create the layout: `fixtures/ models/ adapters/ policies/ corpora/
   oneground/ docs/ tasks/ tasks/scratch/`, each with a one-paragraph
   README.md saying what belongs there (take the wording from CLAUDE.md).
2. Move `arxiv-150k.fixture.yaml` to `fixtures/arxiv-150k.fixture.yaml` and
   `build_fixture.py` to `corpora/build_fixture.py`. Update the usage text in
   the script's docstring to the new paths. Do not change any logic.
3. Create `.venv` (Python 3.12), install pinned: numpy, faiss-cpu, pyyaml,
   zstandard, sentence-transformers, umap-learn. Record exact versions in
   `requirements.txt`.
4. Write `corpora/make_synthetic_source.py`: emits a fake arXiv-format
   JSONL (id, title, abstract ≥ 200 chars, categories from ~12 real arXiv
   category strings with skew toward cs.LG/cs.CL, update_date spanning
   2007–2025) — 6,000 records, seeded. This is for pipeline testing only;
   say so in its docstring.
5. Write `fixtures/arxiv-smoke.fixture.yaml`: a copy of the arxiv-150k spec
   with `fixture.id: arxiv-smoke`, `sampling.target_size: 2000`,
   `queries.count: 200`, and a note in `license_notice` that it is synthetic
   test data. Do not change seeds, thresholds, or tolerances.
6. Run the pipeline on the synthetic source with `--skip-projection`:
       python corpora/build_fixture.py --spec fixtures/arxiv-smoke.fixture.yaml \
           --source <synthetic.json> --out fixtures/
   This downloads bge-base-en-v1.5 (~440 MB) once. The k-means warnings
   about too few points are expected at this size.
7. Write `oneground/fixture_verify.py` implementing
   `oneground fixture verify <id>` in its minimal form: recompute every file
   digest against MANIFEST.sha256 and report per-file verified / contradicted.
   Value-reproduction (recomputing characterization within tolerance) is a
   later task — leave a clearly marked TODO, do not stub it with a pass.
8. Run the verifier on `fixtures/arxiv-smoke/` and include its output.
9. Add a `.gitignore` covering `.venv/`, `fixtures/*/vectors.npy`,
   `fixtures/*/projection.npy`, `fixtures/*/sample.jsonl.zst`, and model
   caches. Small artifacts (MANIFEST, characterization.json, query_ids.json,
   ground_truth.npy) are committed.

## Acceptance
- `fixtures/arxiv-smoke/` exists with MANIFEST.sha256 listing every artifact
  except projection.npy.
- `build_fixture.py` printed all TO_BE_FILLED values without error; paste
  them into the report verbatim (they are synthetic — do not write them into
  any YAML).
- `fixture_verify.py` reports verified for every file it checks.
- The weights hash printed is a real sha256, not None. If it is None, report
  the filename found in the HF cache — do not patch around it.
- `requirements.txt` pins every dependency to the installed version.

## Do not
- Touch the arxiv-150k spec's values.
- Download the real arXiv snapshot (that is task 002 and needs the
  developer's Kaggle credentials).
- Create a git remote or push anywhere. `git init` locally is fine.

## Report
Standard format from CLAUDE.md. Under Measurements include: wall-clock of
the pipeline run, peak RSS if observable, and the full TO_BE_FILLED block.
