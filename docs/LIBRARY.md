# oneground — the public library: the position, before the code

*19 September 2026. Written before implementation, in the order the
chunking and proposals positions were written: the exam before the code.
Its input is a review of the first two real cards, read as a stranger
would read them, by the stream that built them. Nothing here is a date.*

---

## 1. What the library is for, and the failure it must not become

A card says: on this corpus, this change was predicted to do this, and it
did or it did not. Published, a card is worth something to a stranger only
if they can answer three questions from it alone:

1. **Is this corpus anything like mine?**
2. **Was this measured well enough to believe?**
3. **What did they not tell me?**

A library that cannot answer the first is a wall of results about corpora
nobody can locate. One that cannot answer the second invites the
comparison of numbers produced by different instruments. One that cannot
answer the third is a marketing page — and that is the failure this whole
product exists to refuse, arriving through the one feature designed to be
shared.

The review of the first two cards found the third question unasked
entirely. **A card does not currently say how many proposals were run on
that corpus and not published.** Without it, a library is a selection of
the ones someone chose to show.

---

## 2. What a card must carry, and why

### 2.0 A corpus is not a workdir

The definition everything below turns on. **A corpus is identified by its
vectors' sha256**, which every card already carries, and a workdir is one
run against one. The two are not the same thing and the library must never
treat them as one: on the machine that produced the first cards, a single
vectors digest is the sample of two different workdirs, and a second corpus's
digest is the sample of two more.

It matters wherever the library says "this corpus" — most sharply in §2.4,
where a denominator counted per workdir is right about the workdir and wrong
about the corpus, and where two implementers reading "proposals run on this
corpus" without this definition would publish different numbers from the same
disk.

It is a weaker identity than it looks, and the paper would rather say so: two
corpora embedded from the same documents by different models have different
digests and are correctly different corpora; the same vectors re-saved by a
tool that rewrites the file are one corpus with two digests, and the library
will read them as two. Nothing here resolves that, and a card carries the
digest rather than a claim about what it means.

The first cards carry citations that prove internal consistency and
almost nothing a stranger can check: digests of files they cannot obtain,
a workdir name in place of a corpus description, a local Windows path.
That is the right shape for a private receipt and the wrong shape for a
public one. A published card is a different artifact and must say so.

### 2.1 The corpus, so a reader can locate it relative to their own

**Required, and the single most important addition:** the corpus's
characterization — intrinsic dimensionality, boundary crispness, skew,
ambiguous-query rate, drift. These are already measured in the workdir and
absent from the card. Without them a reader cannot tell whether a result
from a corpus at crispness 0.011 says anything about theirs at 0.036 —
which is the whole question.

**The minimum honest subset**, because a partial characterization is worse
than none:

| field | why it is in the minimum |
|---|---|
| `intrinsic_dimensionality` | one of the five |
| `boundary_crispness` | one of the five |
| `skew_top10_share` | one of the five |
| `ambiguous_query_rate` | one of the five |
| `drift_before` / `drift_after` / `cutoff` | the fifth; it is a pair, and the cutoff is what splits it |
| `definitions.crispness_ratio` | crispness means nothing without it |
| `definitions.ambiguity_ratio` | the same, for the ambiguity rate |
| `definitions.centroids` | both are computed over these regions |
| `definitions.seed` | the regions are seeded |
| `dimension` | the vectors' width |
| `n_base` / `n_queries` | what the measures were measured over |

The `definitions` block is not decoration. The measures are parameterised —
crispness at ratio 1.2 is not the same quantity as crispness at another
ratio — and the five numbers published without it **look comparable and are
not**, which is worse than omitting them. A card carrying the numbers alone
invites exactly the false comparison this section exists to make honest.

Carrying it costs a read: `propose` already refuses a workdir without a
`characterization.json`, so the file is there when the card is built.

Also required: dimensionality, above; what the documents are (domain,
language, typical length); the full corpus size against the sample size; and
the sampling rule with its seed.

**The embedding model is a publisher assertion, marked declared.** oneground
knows it only when oneground did the embedding. For a corpus supplied as
vectors — `source_kind: vectors`, which is what a user with their own
embeddings produces — `build_info.embedding_model` is `null`, and it is null
for every such run this project has made, including both public fixtures'
runs through the product path. The model is recoverable from a fixture's
spec and not from a run. A requirement that refuses most cards is a defect in
the requirement, so the field is the publisher's statement, carried as
**declared** rather than measured, and a reader can see which it is.

**Resolvability, stated either way.** A public fixture gives its id and
URL. A private corpus says *private corpus, digests only* — which is
honest, and tells the reader that the digests are internal-consistency
evidence rather than something they can verify.

### 2.2 The instrument, so two cards can be compared at all

**Required:** the oneground version or commit that measured it. The review
names this as the field that would have made two of this month's
diagnostic tasks unnecessary. Two cards from different weeks cannot safely
be compared without it.

**Required:** whether the run was deterministic; repeat count and spread,
or an explicit *measured once*; the hardware — CPU model, cores, RAM — and
the thread setting; the calibration line the verdicts were judged under,
or an explicit statement that this installation never measured its own
error, which the first cards do carry and do well.

**Required:** an explicit **comparability verdict** for the two
configurations, rather than the ingredients for one. The first cards carry a
nine-day gap between baseline and change, two different library-version
blocks, and a run-level setting given as the phrase "family default", and
leave the reader to work out whether the subtraction is valid. That is a
claim the card must make or refuse, not delegate.

**It has three values, not two: `comparable`, `not_comparable`,
`couldnt_check`** — the same three outcomes this project keeps apart
everywhere else, and for the same reason. A verdict with only two values
forces an unknown into one of them, and an unknown rounded up is the failure
the whole product exists to refuse. **Today the honest value is
`couldnt_check`, on the code**, because no artifact records the oneground
version that measured a row.

> **This verdict is written here and implemented nowhere.** The only
> `comparable()` in the tree is `oneground/calibrate/history.py`, and it
> compares `("check", "dataset", "engine", "engine_version", "config")` —
> engine identity, not the provenance this section defines. It is the right
> shape and the wrong subject.
>
> Two later positions now depend on it: the interface position gates its
> side-by-side view on this verdict, and the VectorDBBench bridge gates its
> table rule on it. Neither can assume it exists. Whichever of the three is
> built first builds this, and the other two cite it rather than
> re-deriving a second answer to the same question.

What a card **may assert**, from what a run already records:

- the two rows were measured under the **same pinned libraries** — the run
  refuses otherwise, naming both versions, so a card that exists has passed
  this;
- on the **same sample** — the corpus files' digests are checked against what
  `characterize` recorded;
- at the **same seed**;
- under the **same run-level settings**, naming them and where they came
  from;
- in the **same OS and architecture**, or on the same pod where a pod id was
  recorded.

What a card **must refuse to assert**:

- **the same code.** Nothing records the version. Task 028c settled one such
  case only by re-measuring a configuration at three revisions: today's build
  answers `recall_at_1` 0.874 deterministically where the recorded row says
  0.875, and a process that always answers 0.874 did not produce 0.875. **No
  ingredient on the card could have said that** — a card inferring
  `comparable` from matching library versions would have asserted something
  false about exactly those two rows.
- **the same machine.** The environment id is `local:<os>-<arch>` by
  construction, a class rather than an identity, so two different laptops
  share one.
- **`comparable` unqualified**, which is the conjunction of both.

So a card published today carries `couldnt_check` with the reason, and it
carries it on its face rather than in a footnote.

**The way to earn `comparable` was to record the version that measured each
row, and task 033 records it**: every declared artifact carries an
`oneground` field with the version, the commit where one is knowable, and a
stated reason where it is not, and a card carries two of them — the baseline
row's and the changed row's (`docs/VALIDATION.md`). A card whose two rows
carry the same commit can say `comparable`; one whose rows differ can say
`not_comparable` and mean it. **A card built from a workdir written before
that field existed stays `couldnt_check`**, because nothing can add a version
to an old artifact honestly, and a missing version is never read as a match.

### 2.3 The finding, so it can be read rather than decoded

**Required:** the full metric row for both configurations in the card's
text, not only in its JSON; the routing/index decomposition —
`ceiling_at_10`, `routing_loss`, `index_loss` — read by a sentence, so a
reader sees whether the change moved the architecture or the index; the
thresholds' **basis**, because an author-chosen budget with no stated
reason cannot be told from a number picked to produce a result; whether
any real engine was verified for this configuration, or the result is
simulator-only; and what the change would cost, since the project has a
cost model and the card carries none of it.

**Required:** a stable global card id, the publisher, and a licence — what
a reader may do with the numbers, and whether the corpus owner consented
to publication. A published card without a named publisher is not evidence
of anything.

### 2.4 The denominator

**Required, and new:** `proposals_run_on_this_corpus` and
`proposals_published`. A card that is one of three published from
seventeen run says so on its face. A library that cannot show its
denominator cannot be read as evidence, only as advertising.

**It is not trivially available, and pretending otherwise would put a soft
number beside hard ones.** Nothing counts proposals today: a proposal writes
into a directory under one workdir, nothing enumerates them, and publication
happens outside the tool entirely, so no artifact records that a card was
ever published.

**Where the numbers have to come from.** A **ledger**: append-only, keyed by
the corpus's vectors digest, written by `propose` on every run that produces
a card, and living **beside the corpus rather than inside a workdir**, since
it has to outlive any one of them. Publication needs a second record, written
by whatever submits a card, because only that step knows a card was
published; the natural shape is that submission returns a receipt the
publisher keeps. The card then cites the ledger rather than restating a
number out of the air.

**And the caveat, stated here rather than discovered later.** A denominator
counted from directories can be lowered by deleting one, which makes it
exactly as trustworthy as the good faith it exists to stop needing.
Append-only, digested, and cited is the difference between a denominator and
a claim about one.

**This number is weaker evidence than the rest of the card, and the library
says so where it is shown.** Every other field on a card is the presence of a
record — a measurement, a digest, a verdict computed from rows. The
denominator is an *absence* of records: it asserts that nothing else was run
and not shown. Absence is not provable from the artifact, only from the
discipline of whoever kept the ledger, and a reader is entitled to weigh it
that way.

A publisher who will not disclose the denominator may publish, with
`denominator: withheld` on every card. A reader can then weigh it
accordingly, which is the point.

---

## 3. What the library may never do

- **Rank corpora, or cards across corpora.** Two results on two corpora
  are two results. The library sorts and filters; it does not score.
- **Aggregate.** "This change held in 12 of 17 published cards" is a
  sentence about publication behaviour, not about the change. If an
  aggregate is ever shown, it is over the denominator or not at all.
- **Recommend.** A card may not, and neither may a collection of them.
- **Show a card whose corpus a reader cannot locate.** A card without a
  characterization is not published; it is rejected at submission, with
  the missing fields named.
- **Silently normalise.** Cards from different oneground versions are
  shown with their versions, never reconciled into a single table without
  one.

---

## 4. Transfer: the honest limit

The hard question underneath the library is whether a result on one corpus
is informative about another at all. The project's own evidence says: less
than one would hope. Two public corpora that look unalike agree on the
architecture question and disagree about drift. A card from a corpus at
crispness 0.011 may or may not predict one at 0.036, and **oneground has
not measured which**.

So the library's claim is bounded and stated on every page: *these are
results from other people's corpora, with the corpora described well
enough for you to judge the resemblance yourself. Whether a result
transfers is not something we have measured.*

The way to earn a stronger claim later is to measure it — run the same
proposal across corpora whose characterizations differ and publish whether
the outcome tracked the difference. That is a research task, not a
product feature, and it is not promised here.

---

## 5. Submission, and what is refused

A card is submitted by its producer, never scraped. Submission validates
against the required set above and **refuses with every missing field
named at once**, as `fixture verify` does. A refused card is not
published, not quarantined, not published-with-a-warning.

Two refusals worth naming:

- **A card whose prediction digest is not cited by the run that produced
  it.** The pre-registration is the whole claim; a card that cannot show
  the prediction preceded the measurement is not a card.
- **A card whose comparability verdict is `not_comparable`.** If the
  baseline and the change are *known* to have been measured by different
  code or in different environments, the card says so and is not published
  as a result. It may be published as an *observation*, in a separate,
  clearly labelled place.

  **`couldnt_check` is not a refusal.** It is today's honest value for every
  card, since no artifact records the version that measured a row (§2.2), and
  a rule that refused it would refuse everything — which would not be
  caution, it would be the unknown rounded down instead of up. A
  `couldnt_check` card publishes **as a result, with the verdict and its
  reason on its face**, and stops being couldn't-check on the day a run
  records what built it.

---

## 6. What this position does not settle

- The transport: whether cards are submitted to a hosted index, published
  as files in repositories and aggregated by a crawler, or exchanged
  privately between teams. The content requirements above are the same in
  all three; the trust model is not, and it is its own decision.
- Identity: how a publisher is verified, and whether anonymous
  publication is permitted. A named publisher is required; how the name is
  established is unsettled.
- Tier-2 triage — which proposals are worth a developer's hours — is
  named in the charter, unaddressed here, and depends on the library
  existing first.
- Whether a corpus owner's consent is a field the publisher asserts or
  something stronger. Asserted, for now, and stated as asserted.

---

## 7. Sequencing

Not before proposals tier 2. The first implementation is the **card
schema and its validator** — the refusals before the capability, as the
proposals position required and as 026 did. A library with nothing in it
that refuses correctly is further along than one full of cards nobody can
read.

*The exam, before the code.*
