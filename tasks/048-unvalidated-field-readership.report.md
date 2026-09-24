# Report: 048-unvalidated-field-readership

A measurement only, per instruction: item 7 of
`tasks/046-contract-changes.report.md` is not rulable until this number
exists, and nothing is proposed here.

## The question

Of the 58 leaf fields `requirements.example.yaml` documents that
`oneground/intake/fields.py`'s table validates none of, how many does any
production code path actually read?

## Method

1. Flattened `requirements.example.yaml` to dotted leaf paths (dicts
   recurse, scalars and lists are leaves). **74**, matching task 046's
   count exactly.
2. Diffed against `intake.fields.BY_NAME` (the validated-field table). **16**
   in the table, **58** not — matching task 046's count exactly.
3. For each of the 58, searched every production `.py` file under
   `oneground/` (excluding `test_*.py` and `fields.py` itself) and every
   `.js`/`.html` under `oneground/lab/` for the field's own last path
   segment, then read the surrounding code at each hit to judge whether it
   is actually that field — not a same-named key on an unrelated dict — and
   whether the value, once read, affects anything (a computation, a gate, a
   string written to an artifact or the page). A property that exists but
   is never called does not count as read; nothing calls it, so nothing is
   affected by its value.

## Measured

**21 of the 58 are read by something. 37 are read by nothing.**

Read (21), with where:

| field | reads it |
|---|---|
| `constraints.recall_at_k.k` | `report/verdict.py`, `report/__init__.py` |
| `constraints.recall_at_k.min` | `report/verdict.py`, `report/__init__.py` |
| `constraints.latency.p95_ms` | `report/verdict.py`, `report/__init__.py` |
| `constraints.latency.at_qps` | `report/verdict.py`, `report/__init__.py` |
| `constraints.latency.concurrency` | `report/verdict.py` |
| `constraints.storage_amplification_max` | `report/verdict.py`, `report/__init__.py` |
| `constraints.memory_budget_gb` | `capacity.py`, `cost/__init__.py`, `report/verdict.py`, `report/__init__.py` |
| `constraints.monthly_budget.amount` | `report/verdict.py` |
| `constraints.monthly_budget.currency` | `report/verdict.py` |
| `corpus.sample.metadata.path` | `characterize.py` |
| `corpus.sample.metadata.timestamp_field` | `characterize.py`, `intake/__init__.py` |
| `corpus.declared.embedding_model` | `analogy.py`, `characterize.py` |
| `corpus.declared.corpus_type` | `analogy.py`, `characterize.py` |
| `corpus.declared.nearest_fixture` | `analogy.py` |
| `simulate.families` | `simulate/__init__.py`, `report/__init__.py` |
| `simulate.node_counts` | `simulate/__init__.py` |
| `simulate.ground_truth_k` | `simulate/__init__.py`, `proposals/propose.py` |
| `simulate.budget.max_configs` | `simulate/__init__.py` |
| `simulate.budget.max_minutes` | `simulate/__init__.py` |
| `verify.target` | `verify/__init__.py`, `report/__init__.py` |
| `verify.duration_minutes` | `verify/__init__.py`, `verify/runpod.py` |

Unread (37) — nothing in `oneground/` (production `.py`, or the lab's `.js`/
`.html`) reads the value:

    run.mode
    constraints.kind
    constraints.growth.horizon_months
    constraints.growth.expected_size_at_horizon
    constraints.filtering.fields
    constraints.filtering.typical_selectivity
    constraints.updates.rate_per_day
    constraints.updates.deletes
    constraints.deployment.self_hosted
    constraints.deployment.regions
    constraints.deployment.engines_allowed
    constraints.deployment.engines_excluded
    corpus.sample.kind
    corpus.sample.metadata.filter_fields
    corpus.sample.metadata.category_field
    corpus.sample.queries.source
    corpus.sample.sampling.method
    corpus.sample.sampling.stratify_by
    corpus.sample.sampling.full_corpus_size
    corpus.declared.kind
    simulate.kind
    simulate.report_ceiling
    simulate.report_ratio
    verify.kind
    verify.enabled
    verify.finalists
    verify.engines_pinned.qdrant
    verify.engines_pinned.pgvector
    verify.cost_model.source
    verify.cost_model.as_of
    verify.cost_model.error_band
    report.kind
    report.formats
    report.include_ground_view
    report.include_query_traces
    report.include_decision_log
    report.publish_receipt

## Finding A — `verify.cost_model.{source,as_of,error_band}` is a
schema/code name mismatch, not three dead fields

The example file documents a path nothing reads. The code reads a path the
example file does not document. Both sides, named:

- **The example documents `verify.cost_model.{source,as_of,error_band}`.**
  Nothing reads that path — confirmed by grepping every production `.py` and
  the lab's `.js`/`.html` for each of the three keys and reading every hit;
  none traces back to `verify.cost_model`.
- **The code reads `verify.cost` (or a top-level `cost:` block) for the same
  three field names.** `report/__init__.py:405-406`:
  `cost_cfg = req.data.get("cost") or (req.data.get("verify") or
  {}).get("cost") or {}`, and again at `:1318`. `cost/__init__.py:224` reads
  `cfg.get("error_band", ...)` from whatever `cost_cfg` it was handed.
  `cost/__init__.py:load_prices`'s own refusal message says which path is
  real: *"point `verify.cost.prices` at a table you can read."*

So `error_band` and `source` are live, consumed field names — the mismatch
is the parent key, `cost_model` in the file the user is told is the schema
by example against `cost` in the code and in the code's own error text. I
did not chase which side should give way; that needs to know which the
users have, and this report was asked for a number, not a ruling.

## Finding B — six `kind:` labels are ornamental, consistently, by design
rather than by six separate oversights

`constraints.kind`, `corpus.sample.kind`, `corpus.declared.kind`,
`simulate.kind`, `verify.kind`, `report.kind` — one per top-level block in
`requirements.example.yaml`, each set to `declared` or `receipt`, and every
one of the six is read by nothing. Not five of six, not "mostly": all six,
with no exception anywhere in the pattern.

That consistency is the finding. A field unread in one block could be an
oversight in that block. A field unread in the same shape in every block
that carries it is a block-level annotation for the human reader — this
project's receipt/declared vocabulary, written into the file so the person
reading it knows which half of the split they are looking at, never
consumed by the code that runs on the rest of the block. Six oversights
would look different from each other; these do not.

## The other 21 of the 37

The rest of the unread set — `constraints.deployment.*`,
`constraints.updates.*`, `constraints.growth.*`, `constraints.filtering.*`,
`corpus.sample.sampling.*`, `verify.engines_pinned.*`, `verify.enabled`,
`verify.finalists`, `corpus.sample.metadata.category_field` (a property
that exists and is never called, so counted with the rest: existing
uncalled affects nothing, the same as not existing), and all of `report.*`
except `kind` — have no reader anywhere under any name. Not a mismatch, not
a design choice, not an orphaned property with a purpose: simply never
consumed, and un-grouped here because nothing measured about them
distinguishes one from another the way Findings A and B distinguish their
members.

## Not done

No repair, no recommendation on `cost_model` vs `cost`, no ruling on the
`kind` labels, no statement of the checked set — why twenty-five checks and
not some other number. That ruling is yours; this report is the number and
the two things found while producing it.
