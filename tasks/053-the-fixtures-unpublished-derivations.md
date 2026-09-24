# Task 053 — The fixture's own derivation gap, and built vs verified

## Setup
New branch from `main`: `git checkout -b task-053 main`. Commit `053:` and
push after every commit. Pod time only if closing the chunk-count gap
requires re-running the builder to persist them (check first — the report
says the rate is independently recomputable from the shipped sample, so a
local recomputation from artifacts already on disk may be enough; do not
assume a pod session is needed without checking).

## Why

**The built→verified rule already exists. It lives in code, not in
writing, and the question is not what the rule should be — it is whether
the rule the code already applies is the one anyone actually intended.**

`oneground/fixture/verify.py` prints it, unnamed, in its own summary
logic: when every published value is recomputed and every one reproduces
— `len(v_ver) == n and not uncovered` — it says *"This fixture's status
may be set to `verified`."* `arxiv-150k` carries `status: verified` today.
That is not a hypothetical condition someone might someday check against
a real promotion; `arxiv-150k` **is** a real promotion, already made, and
whether the code's condition is what actually produced it is checkable,
not something to assume.

**Three things follow from that, and the task keeps them in this order:**

1. **If the code's condition and `arxiv-150k`'s actual promotion agree** —
   write the condition down in prose, where a reader of a fixture spec
   meets the word `verified`, not only where `verify.py` happens to apply
   it internally.
2. **If they disagree** — the promotion itself is the finding, and it
   outranks anything this task does next: `arxiv-150k`'s `status:
   verified` would be a claim nobody can currently reproduce from the rule
   the code actually enforces. Say so, plainly, before recommending
   anything about `sec-filings-10k` or about the vocabulary. A status
   field whose one existing example cannot be reproduced is worse than an
   undefined one, because it looks settled and is not.
3. **If the condition is one nobody would have chosen, examined cold** —
   removing `verified` from the vocabulary is a live option and stays
   open through the whole task, not foreclosed by having found a
   candidate rule to write down. A two-valued status field governed by an
   accident of how a summary function happens to phrase itself is worse
   than no field.

**This is the fourth rule found this week living in code and nowhere in
writing, and the first of the four that governs a word this project
publishes about a corpus other people are told to check.** Say that in
the report — it is the argument for why this task exists rather than a
smaller one that just closes the three gaps below.

Those three gaps are what makes the question answerable at all for
`sec-filings-10k` specifically, and they are the same defect three times:

> A published thing whose derivation is not in the published record.

- `chunks_total`, `chunks_per_document` and `chunks_crossing_a_boundary`
  go into a `receipt` dict nothing writes out — the full-corpus figures
  exist **only in the build log**, not in `section_statistics.json`.
- The **21,287-accession list** that defines the fixture's source is not
  shipped as a declared artifact. A moved EDGAR selection correctly
  refuses a rebuild today, which is right — but leaves a rebuilder with no
  way to reconstruct what was originally selected.
- `fixture verify` **does not recompute four of its own published values**
  — `semantic_sharded.routing_ceiling`, `.p50_copies`, `.p95_copies`,
  `.p99_copies_per_vector`. It says so honestly in its own output, which
  is the right behaviour for a couldn't-check — but it means the command
  this project tells outsiders to run to check a fixture leaves four of
  that fixture's own published claims unchecked by it.

**The third is the sharpest of the three, and it is the one the built→
verified question turns on**: closing it is what `sec-filings-10k` would
need before the code's condition could even consider it, whichever way
item 1 above resolves.

## Do

1. **Persist the chunking counts.** `chunks_total`, `chunks_per_document`,
   `chunks_crossing_a_boundary` into `section_statistics.json`, sourced
   from wherever they are actually available without re-measuring —
   check whether the build log or an existing artifact already carries
   what is needed before deciding a pod session is required, and say
   which you used.
2. **Ship the accession list.** A declared artifact (~100 KB compressed,
   per 030's own estimate) recording the 21,287 accessions the fixture
   was built from, referenced from the spec the way other declared inputs
   are, so a rebuilder can reconstruct the original selection even after
   EDGAR's indexes move.
3. **Close the `fixture verify` coverage gap, or say precisely why not.**
   For each of the four unrecomputed values (`routing_ceiling`,
   `p50_copies`, `p95_copies`, `p99_copies_per_vector`): either make
   `fixture verify` recompute it from the published artifacts the way the
   other eight values are recomputed, or state the specific, named reason
   it cannot be — not "it would be expensive" as a blanket cover, the
   actual reason, the way `verify.py`'s own docstring already reasons
   about scope elsewhere (release-asset-only, couldn't-check on an absent
   artifact). A value left uncovered on purpose is declared as such in the
   spec or the verifier's own output, not merely absent from both.
4. **Answer the built→verified question, in the order set out in Why.**
   Determine what actually produced `arxiv-150k`'s `status: verified` —
   its own task report, its commit history, whatever states the reason —
   and compare it against `verify.py`'s `len(v_ver) == n and not
   uncovered` condition. Then:
   - **Agree:** state the rule in prose (`docs/VALIDATION.md`, beside
     `status: verified`'s existing explanation) and say what it would now
     take for `sec-filings-10k` to cross it, given item 3's work above.
   - **Disagree:** report the disagreement as the finding, first — what
     actually justified `arxiv-150k`'s promotion, and why the code's
     condition is not it. Only after that is stated plainly, say what (if
     anything) should change: the code's message, the written rule, or
     `arxiv-150k`'s own status.
   - **Defensible but nobody would have chosen it:** say so, and recommend
     removing `verified` from the status vocabulary rather than writing
     down a rule that happens to be true of one fixture by accident.
   Whichever branch applies, do not present it as though the other two
   were never live possibilities.

## Acceptance

- `section_statistics.json` (or its equivalent) carries the three chunk
  counts, sourced and said from where.
- A declared accession-list artifact exists, referenced from the spec.
- Each of the four unrecomputed values is either recomputed by `fixture
  verify` now, or is named in the spec/verifier output with its own
  specific reason for staying uncovered — no value left silently absent.
- The report states, explicitly and first among its findings, whether
  `verify.py`'s condition matches how `arxiv-150k` was actually promoted
  — with evidence, not an assumption that agreement is the default.
- Depending on that finding: either `docs/VALIDATION.md` states the
  built→verified rule in prose where a fixture-spec reader meets the
  word, or the report states the disagreement and its consequence for
  `arxiv-150k`'s current status, or the report recommends removing
  `verified` from the vocabulary — and says which of the three, plainly.
- The report names this as the fourth rule this week found living in code
  and not in writing, and the first governing a published status word.
- Full suite green, guard clean, identifier scan runs rather than skips,
  `fixture verify sec-filings-10k` re-run and its output pasted into the
  report showing the coverage change.

## Do not

- Promote `sec-filings-10k` to `status: verified` yourself. That is the
  developer's call once the rule is written down and the gap is
  (or is not) closed — state what the fixture's status would honestly be
  under the stated rule, and let the developer set the field.
- Change `arxiv-150k`'s `status:` field, whichever way the comparison
  comes out. Its status is evidence for this task, not something this
  task corrects.
- Widen a tolerance or change a published value to make `fixture verify`
  pass on the four previously-uncovered ones. If recomputing one reveals
  a real disagreement, that is a finding — report it, do not absorb it.
- Treat "the condition and the promotion agree" as the default outcome
  going in. Check it; do not assume it because assuming it is the
  question this task exists to not assume.
