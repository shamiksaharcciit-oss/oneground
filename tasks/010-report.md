# Task 010 — `oneground report`: the first verdicts

## Expected repo state
Task 009 committed; tree clean. A workdir exists from running
characterize → simulate → verify on smoke (recreate if not). Report the
workdir's file list.

## Why
Every command so far measures. This one judges — and the house rules bind
it hardest: three outcomes per option, verdicts only from same-environment
measurements, couldn't-check never rounded up, and every number in the
report traceable to a file in the workdir with its kind.

## Do
1. **`oneground/report/`** — `oneground report <requirements.yaml>`:
   reads `constraints` from the requirements file and the workdir's
   `characterization.json`, `simulate.json`, `verify.json` (optional),
   their `_info` files, and MANIFEST.
2. **Verdict rules** (`report/verdict.py`, pure functions, tested):
   - one row per (family, config) from `simulate.json`, joined with
     `verify.json` rows where the engine config matches.
   - per constraint: `meets` / `fails` / `couldnt_check`, each with a
     reason string and the source field.
     * recall floor: from `simulate` (recall@k at the requested k); always
       decidable if the row exists.
     * storage amplification, memory budget: from `simulate.footprint`;
       decidable.
     * latency p95 / QPS: **only** from `verify.json` rows whose
       `latency_shape` is not couldn't-check **and** whose environment is
       the one the constraint targets; otherwise couldn't-check with the
       reason ("no verify row", "environment noise", or "measured on
       <env>, constraint targets <env>"). Never from simulation.
     * budget: from the cost model when present (task 011), else
       couldn't-check.
   - an option's overall outcome: `fails` if any constraint fails; `meets`
     if every constraint meets; else `couldnt_check`, listing which.
   - **indistinguishable**: two `meets` options whose recall differs by
     less than the calibration tolerance (0.01 until the calibration
     history exists) are reported as indistinguishable on recall and are
     separated only on constraints where they differ measurably; the
     report says so in words.
   - **not run**: families in the requirements file's `simulate.families`
     that produced no rows (budget, refusal) are listed as not run with
     the reason; never omitted.
3. **Decision log**: an ordered list of sentences, each generated from a
   rule firing, naming the constraint, the value, the threshold, and the
   source file+field. The recommendation is the top `meets` option by
   the user's `rank_by` (default: fewest constraints at margin, then
   lowest storage, then lowest fan-out) — and the log's final entry
   states what would be needed to turn each couldn't-check into a
   verdict.
4. **Outputs** to the workdir: `report.json` (the rows, verdicts, log —
   measurement + judgement clearly separated by key), `manifest.yaml`
   (the recommended configuration in deployable form: family, params,
   engine + version if verified, and the digests of every input), and
   `report.html`.
5. **`report.html`** — single self-contained file, no CDN. Use the
   design tokens from `docs/design/` (create it: slate base #1B2432,
   panel #243040, ink #E7EAEF, muted #8B96A5, ochre #C99A3B; outcome
   colours teal #4FC1AD meets, coral #E36C5E fails, amber #D9A441
   couldn't-check; Space Grotesk for interface text, IBM Plex Mono only
   for digests and receipts; both loaded from the system, fallback to
   generic). Sections in this order: the recommendation with its three
   outcomes; the options table (every row, every constraint, coloured by
   outcome, with the source field on hover); the ground (embed
   `docs/img` variant B when the run has a projection, else the
   characterization numbers as a panel); the decision log; the receipt
   table (every input file, kind, digest); a footer stating the
   calibration status ("calibration history: not yet available"). No
   charts in this task. Read `/mnt/skills/public/frontend-design/SKILL.md`
   equivalent guidance is not available to you — apply the tokens and
   keep it typographic and quiet; the recommendation is the only
   emphasised element.
6. **Run it three ways** and include the outputs:
   - smoke workdir with constraints it meets → recommendation + log.
   - smoke with an impossible constraint (p95 ≤ 1 ms) → every option
     couldn't-check on latency (Windows noise) and the log's final entry
     naming the pod run as the way to decide.
   - arXiv-150k workdir from task 008's simulate (no verify) with
     `recall_at_k.min: 0.95, storage_amplification_max: 2.0` → expected:
     `single_node_hnsw` and `hash_sharded` meet, indistinguishable on
     recall; `semantic_sharded` fails storage; latency couldn't-check for
     all. Paste the decision log verbatim.
7. Tests: verdict rules on synthetic rows for every branch above,
   including indistinguishable and not-run; an HTML smoke test that the
   file contains no verdict words for couldn't-check rows and contains
   the receipt table.

## Acceptance
- The three runs produce the expected outcomes; the arXiv log reads as a
  correct account of task 008's table.
- `report.json` separates measurement from judgement by key.
- No verdict is ever derived from a simulated latency; test proves it.
- `manifest.yaml` is produced and lists input digests.
- HTML opens offline; tokens applied.

## Do not
- Introduce a cost model (011). Add charts. Change any measurement.
