# Report: review of the public-library position

A reading task on `task-032`, against
`oneground-library-position.md` as drafted 19 September 2026. **The paper was
not changed.** Findings only, in the three categories asked for, then the
three questions asked in particular.

Everything below is checked against what ships on `task-032` at `744ecb2`,
and the evidence is named each time.

## Impossible against what ships

1. **§2.1's embedding model, for the corpora this project actually runs on.**
   `build_info.embedding_model` is `null` in **six of the seven workdirs on
   this machine** — every one whose `source_kind` is `vectors`, which is what
   a user supplying their own embeddings produces. It is populated only when
   oneground did the embedding (`support-tickets-2026q3`,
   `BAAI/bge-base-en-v1.5`). Both public fixtures' product-path runs are in
   the null six. The model *is* in each fixture's spec
   (`fixtures/arxiv-150k.fixture.yaml`: `embedding.model`), so it is knowable
   for a fixture-based corpus and unknowable for a private one. As written,
   the requirement would either carry a false `null` or refuse most cards.
   **It has to be a publisher assertion, marked declared rather than
   measured** — the vocabulary already exists for exactly this.

2. **§2.2's oneground version.** Nothing records it. `simulate_info.json`
   carries `library_versions`, `python_version` and `platform` and no version
   of this project; `card.json` carries the four pinned libraries. The paper
   is right that this is the field that would have saved two diagnostic tasks
   — it is 028's *Observed, not done* item 3, and 028b and 028c each had to
   reconstruct it from commit dates and re-measurement. **Until `simulate`
   records what built a row, no card can carry it**, and the library cannot
   require it of cards produced today.

3. **§2.2's hardware — CPU model, cores, RAM — and the thread setting.**
   Nothing collects any of it. The environment stamp is deliberately thin
   (task 014: no hostname, no absolute paths), `simulate_info.platform` is a
   string like `Windows-11-10.0.26200-SP0`, and the only CPU description this
   project has ever captured was written by hand into `host.txt` by a pod
   runner script. Not impossible in principle — a CPU model is a class, not an
   identity — but **nothing produces it today, and whether it is compatible
   with 014's rule is a decision the paper assumes rather than makes.**

4. **§2.2's "same environment", as a verdict.** `environment_id` is
   `local:<os>-<arch>` by construction, so two different Windows laptops are
   `local:windows-amd64` and indistinguishable. A card **cannot** assert that
   two rows were measured in the same environment; it can assert the same OS
   and architecture, or the same *pod* when `ONEGROUND_ENVIRONMENT_ID` is set,
   which names a rented machine. The paper's requirement is stronger than the
   identifier the project deliberately kept weak.

5. **§2.4's `proposals_published`.** The tool has no idea. Publication happens
   outside it and nothing records that it happened. This is not a gap in a
   count; there is no count. See the third question below.

## Already carried, under another name

1. **§2.1's sampling rule and seed.** `sample.seed` is on the card already;
   the rule is in the requirements file (`sampling.method: stratified`,
   `stratify_by`, `full_corpus_size: 2100000`) and in the run's inputs, one
   step from the card rather than absent.
2. **§2.1's "private corpus, digests only".** The declared/receipt split is
   this distinction, and `card.json` already carries a `kind` map that speaks
   it.
3. **§2.2's calibration line.** On the card today, including the absence
   case, which the paper notices and credits.
4. **§2.2's "whether the run was deterministic".** `simulate_info` carries a
   per-configuration `deterministic` map and, since task 029, a
   `deterministic_note` saying what the flag now guarantees; the built state
   records it per row. Not on the card, but measured and recorded.
5. **§2.3's routing/index decomposition.** `ceiling_at_10`, `routing_loss`
   and `index_loss` are already in `card.json:measured` for both rows. The
   requirement is that a *sentence* read them — which is 028's own *Observed,
   not done* item 8, in the same words.
6. **§2.3's "was a real engine verified".** `verify.json` and
   `verify_info.json` sit in the workdir when a verify was run; nothing links
   them to a card. The fact exists; the citation does not.
7. **§2.3's cost.** `oneground/cost/` with `prices.example.yaml` is a
   shipped cost model. Nothing wires it to a card.
8. **§5's "refuses with every missing field named at once".** That is the 022
   precondition rule, implemented twice already — `fixture verify`'s three
   preconditions and `propose`'s `ProposeError`, which collects every problem
   before raising. A submission validator is a third instance of a pattern
   this project has written down, not a new idea.

## Underspecified — two implementers would build different things

1. **§2.4's `proposals_run_on_this_corpus`: what is "this corpus"?** Today a
   proposal is written under a *workdir*, and a corpus can have several. On
   this machine one vectors digest (`141a9220703a…`) spans
   `arxiv-150k-via-characterize` and `032b-state-local`; another spans two
   stackexchange workdirs. One implementer counts directories under one
   workdir; another counts across workdirs keyed by the vectors sha256. They
   publish different denominators from the same disk. Also undecided: whether
   a `--dry-run` counts (it writes nothing), whether a couldn't-check card
   counts (it is a card, so presumably yes), whether re-running a proposal
   counts once or twice (the prediction is reused, so once), and what happens
   when a directory is deleted.
2. **§2.2's comparability verdict needs three values, and the paper gives it
   two.** §5 refuses "a card whose comparability verdict is negative", which
   leaves *couldn't check* to be rounded into one of the other two — the one
   thing this project refuses to do anywhere else. Which ingredients are
   blocking and which advisory is also unstated.
3. **§2.1's characterization, without its definitions.** The five measures are
   parameterised: `crispness_ratio: 1.2`, `ambiguity_ratio: 1.1`,
   `centroids: 256`, and the seed, all recorded in `characterization.json`'s
   own `definitions` block. A crispness of 0.036 at ratio 1.2 is not
   comparable with one measured at another ratio. An implementer publishing
   the five numbers alone produces a card that invites exactly the false
   comparison §2.1 exists to enable honestly.
4. **§2.3's "stable global card id".** No scheme is given. Today's id is a
   directory slug (`semantic_sharded_probe-1-to-2`) unique only within one
   workdir.
5. **§2.3's "thresholds' basis".** Free text, an enumeration (a constraint
   file, an author's judgement, a prior card), or a citation? Each gives a
   different validator.
6. **§3's "shown with their versions, never reconciled into a single table
   without one".** Operationally unclear: a version column, a table per
   version, or a refusal to sort across versions.
7. **§5's "published as an observation, in a separate, clearly labelled
   place".** The observation channel has no schema, no submission path and no
   statement of whether it is searchable.
8. **§2.1's "typical length" of documents.** oneground measures vectors, not
   text; nothing computes it. Who asserts it, in what unit, and is it
   declared?

## The three questions, answered

### §2.1 — can a card carry the characterization without the workdir, and what is the minimum honest subset?

**Yes, and it costs a read.** `propose` already requires
`characterization.json` to be in the workdir — it is in `REQUIRED`, and a
workdir without one is refused before anything runs — so the file is
guaranteed present at the moment the card is built. Nothing new has to be
computed, transported or cached. "Without the workdir" only bites for a card
built somewhere other than where the run happened, which no path does today.

**The minimum honest subset is the five measures plus what they are
parameterised by.** From the arxiv corpus's own file:

| field | value | why it is in the minimum |
|---|---|---|
| `intrinsic_dimensionality` | 32.553257 | one of the five |
| `boundary_crispness` | 0.036247 | one of the five |
| `skew_top10_share` | 0.0754 | one of the five |
| `ambiguous_query_rate` | 0.8915 | one of the five |
| `drift_before` / `drift_after` | 0.523212 / 0.551401 | the fifth, and it is a pair |
| `definitions.crispness_ratio` | 1.2 | crispness means nothing without it |
| `definitions.ambiguity_ratio` | 1.1 | same, for the ambiguity rate |
| `definitions.centroids` | 256 | both are computed over these regions |
| `definitions.seed` | 20260908 | the regions are seeded |
| `dimension` | 768 | §2.1 requires it and this is where it is |
| `n_base` / `n_queries` | 150000 / 2000 | what the measures were measured over |

Two things I would not put in the minimum, and one caution:
`drift.cutoff` (`2019-01-01`) and `drift_n_before`/`drift_n_after` (965 /
1035) are the drift split's inputs rather than the measure; they are useful
and harmless, but the cutoff is a fact about the corpus's time range and a
publisher should know it is on the card before it is. **The caution:** the
measures without the definitions block are worse than absent, because they
look comparable and are not.

### §2.2 — what can a card assert about comparability, and what must it refuse to?

**It can assert, from what it already holds:**

* the two rows were measured under the **same pinned libraries** — `propose`
  refuses the run otherwise, naming both versions, so a card that exists has
  already passed this;
* on the **same sample** — the corpus files' digests are checked against what
  `characterize` recorded, and the card carries them;
* at the **same seed**;
* under the **same run-level settings** — `shard_depth` and where it came
  from, which is on the card in words;
* in the same **OS and architecture**, or on the same **pod** when a pod id
  was set.

**It must refuse to assert:**

* **same code.** Nothing records the version. 028c settled the arxiv
  workdir's case only by measuring at three revisions and finding that
  today's build answers `recall_at_1` 0.874 deterministically where the
  recorded row says 0.875 — a process that always answers 0.874 did not
  produce 0.875. **No ingredient on the card could have said that**, and a
  card that inferred "comparable" from matching library versions would have
  asserted something false about those two rows.
* **same machine.** `local:windows-amd64` is a class. Two laptops share it.
* therefore **"comparable" unqualified.**

**So the verdict is three-valued, and today's honest value for the two
published cards is *couldn't check*, on the code.** That is not a defect in
the cards; it is the correct reading of what the project records. The paper
should say so, and §5's refusal should distinguish a negative verdict
(measured to differ — publishable as an observation) from a couldn't-check
(unknowable today — which, if it blocks publication, blocks every card until
`simulate` records its version).

### §2.4 — can the tool know the two numbers today, and where would they have to be recorded?

**`proposals_run_on_this_corpus`: approximately, per workdir, and nothing
computes it.** `PROPOSALS_DIR` appears once in the source, to build an output
path; nothing enumerates it. Counting `<workdir>/proposals/*` would give two
for the arxiv workdir, which is right for that workdir and wrong for that
corpus — the same vectors are also the sample of `032b-state-local`. **A
corpus is not a workdir**, and the card already carries the natural key: the
vectors sha256.

**`proposals_published`: no, not in any form.** Publication is outside the
tool and nothing records that it happened.

**Where they would have to be recorded.** An append-only ledger per corpus,
keyed by the vectors digest, written by `propose` on every run that produces
a card — the smaller piece, and it belongs beside the corpus rather than
inside one workdir, since it must outlive any of them. Publication needs a
second record, written by whatever submits a card, because only that step
knows; the natural shape is that submission returns a receipt the publisher
keeps, and the card cites the ledger rather than restating a number.

**And the integrity caveat the paper should state:** a denominator counted
from directories can be lowered by deleting a directory, which makes it
exactly as trustworthy as the publisher's good faith — the thing the
denominator exists to stop needing. Append-only, digested, and cited by the
card is the difference between a denominator and a claim about one.
`denominator: withheld` is the right escape hatch and is honest as it stands.

## Smaller findings

1. **§1's three questions are the right ones and the paper answers them in a
   different order than a reader meets them.** "What did they not tell me?"
   is answered in §2.4, after two sections of requirements; it is the
   question that justifies the rest.
2. **§4 is the strongest section and it undercuts §2.1 slightly.** If
   transfer is unmeasured, then the characterization's job on a card is to
   let a reader judge resemblance *without* the tool implying that resemblance
   predicts anything. The paper says this in §4 and does not say it in §2.1,
   where a reader learns what the numbers are for.
3. **§7 sequences the validator first, which matches 026** — the refusals
   before the capability. Worth noting that the validator can be written and
   tested against the two real cards that exist today, and that both would
   fail it on at least four required fields, which is a useful first test
   rather than an embarrassment.

## What I did not check

* Whether any of this is implementable at the transport layer — §6 leaves the
  transport open and I read it as out of scope for a content review.
* The paper's claims about the first two cards, beyond the ones I could check
  against the cards themselves; they match what task 028's report records.
* Anything about tier-2 triage, which §6 defers.
