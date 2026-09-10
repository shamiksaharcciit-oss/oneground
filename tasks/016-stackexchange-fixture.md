# Task 016 — The StackExchange fixture: a ground that looks different

## Expected repo state
`main` after 014b; T3 live. Work on `main`; commit `task 016:`; do not
push — the developer pushes. This task's build runs through
`oneground pod` and needs the developer's `y` once.

## Why
v0.1 promises "a second fixture where the ground looks different." arXiv
under bge-base has crispness 0.036 and semantic sharding loses. A Q&A
corpus with short posts and many overlapping topics may look different —
or may not. Either answer is the fixture's job to report; this task must
not be steered toward a corpus that makes semantic sharding win.

## Do
1. **Source.** Resolve a public StackExchange dataset live and pin it:
   prefer a Hugging Face dataset of StackExchange posts with a CC BY-SA
   licence and per-post `creation_date` and `tags`/site (e.g. a multi-site
   dump), ≥ 500k posts. Record URL, revision/sha, licence, and the
   attribution requirement (CC BY-SA needs attribution and share-alike —
   state how the fixture satisfies both in `license_notice`). If no
   suitable dataset can be pinned, stop and report the candidates with
   why each fails; do not substitute a synthetic corpus.
2. **Spec** `fixtures/stackexchange-150k.fixture.yaml`, mirroring
   arxiv-150k: 150k base + 2k held-out queries; text template
   `{title}. {body_first_500_chars}` (strip HTML; state the rule); queries
   are titles; stratified by year; hot categories by site or top tag;
   same seeds *pattern* but distinct values (seed `20260911`); same
   measure definitions and tolerances; drift cutoff chosen at the year
   that splits the corpus ~60/40 (state it); `embedding.device: cuda`;
   `status: planned`; every value `TO_BE_FILLED`; an `analogy:` block for
   Tier 2 (`corpus_type: qa`, `text_length: short`, `topics_trend: true`,
   `time_ordered: true`).
3. **Builder generality.** `corpora/build_fixture.py` currently assumes
   arXiv field names. Make the spec declare its field map (`id`, `title`,
   `body`, `categories`, `date`) and the builder read it; smoke and
   arxiv-150k must rebuild byte-identically (regression gate, as in 007).
4. **Session** `sessions/stackexchange-build.yaml` for `oneground pod`:
   GPU (resolve live), the dataset download as a setup step with its
   digest verified, `run: bash corpora/run_fixture_build.sh` generalised
   from `run_arxiv_150k.sh` (take the spec id as env), outputs small +
   large tarballs, caps `{max_hours: 1.5, max_usd: 2.50}`. `plan` must
   resolve read-only before you ask for the `y`.
5. **Build** (developer types `y`): drive `watch`, fetch, verify. Publish
   values as in task 003b/005 (from the files, not a pasted block),
   `status: built`, findings block: crispness, ambiguity, copies
   histogram, the two reference recalls, drift pair, and the one-line
   comparison to arxiv-150k — written from the numbers, whichever way
   they fall.
6. **Simulate + report** locally on the sample (`requirements.stackexchange-150k.yaml`,
   same constraint set as arXiv minus latency): paste the decision log.
   If semantic sharding meets here, say so; if it loses again, say so.
7. **Ground view export + teaser data** are NOT in this task — the page
   stays arXiv-only for the 16th. Produce the `ground_view_*.parquet`
   only (they're declared artifacts); the second-corpus page section is
   a later brief.
8. `fixture verify stackexchange-150k --asset` from the fetched files
   where possible; report digests and any values checkable locally.
9. Docs: `docs/FIXTURES.md` — the two fixtures side by side (source,
   licence, model, size, the five measures, the reference results).

## Acceptance
- Dataset pinned with licence and attribution satisfied, or a stop
  report with candidates.
- Builder is field-map driven; smoke + arxiv-150k byte-identical.
- One pod session, zero pods left, cost reported.
- Spec `status: built` with values from the files; findings written
  from the numbers.
- Decision log pasted; FIXTURES.md exists.

## Do not
- Choose or tune the corpus to produce a particular result. Touch
  `site/teaser/`. Push. Raise caps.
