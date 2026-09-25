# oneground — tier-2 triage: the position, before the code

*25 September 2026. Written before implementation, in the order the six
earlier positions were written: the exam before the code. Three scoping
decisions in it were written as defaults, not rulings; the developer
ruled all three on 25 September 2026, for the reasons given at each —
his reasons, kept as written rather than replaced by this paper's own.
Everything else stated here is a finding, checked against the source, or
a design decision this paper is entitled to make on its own.*

## 0. The finding that shapes everything below

**There is no queue to triage today, because a refusal is not recorded
anywhere.** Checked directly, not assumed: `oneground propose` validates
a policy in `oneground/proposals/policy.py::validate_policy`, and a
policy naming a family or parameter the simulator does not have —
*"this requires a family that does not exist"* — raises `PolicyError`,
collected into `oneground/proposals/propose.py::ProposeError`. The CLI
(`oneground/cli.py::_cmd_propose`) catches it, **prints the message to
stdout, and returns exit code 2**. Nothing is written to disk. No file
records that the refusal happened, what was described, or when. The
same is true of a refusal path 2's `translate` (`docs/PROPOSALS.md`
§2.1) would produce upstream of `propose` — `translate` does not
validate a family name at all (`oneground/proposals/translate.py`'s own
docstring: that is `validate_policy`'s job, not run a second time), so a
model-produced policy naming an invalid family reaches exactly the same
unrecorded refusal, one step later.

Checked further: `oneground/supervisor.py`'s durable job record
(`jobs.json`, per-job logs) — the mechanism that *would* capture a
refused `propose` invocation run through the interface's write half — is
also absent everywhere in this checkout (`tasks/060-state-of-the-
product.report.md`'s own finding, re-confirmed here rather than assumed
from that report). Whatever a developer or a user has watched refuse in
a terminal or a browser has left no trace either way.

**This is the paper's first finding, not a footnote to it.** A triage
design that assumes a queue already exists and specifies only how to
rank it would be building the ranking before the thing it ranks can be
observed. §7 below sequences the durable record ahead of any ranking
logic for exactly this reason.

## 1. The question

`docs/CHARTER.md` Phase 5 names it once, in one line: *"Tier-2
(structural) triage queue, maintainer-reviewed."* `docs/PROPOSALS.md`
§5 and §6 both call it unaddressed. `docs/LIBRARY.md` §6 names it too,
and adds a dependency this paper checks in §7. Nowhere is it said what a
structural proposal *is*, whose review it queues for, or what a triage
verdict may honestly say. Those are the three defaults below. The
question underneath all three: **when the tool cannot build what an
idea asks for, is there anything honest to say about which unbuildable
ideas are worth a person's attention** — and if so, said how, without
the tool claiming to know something it cannot measure.

**A note on `docs/CHARTER.md`'s own looseness, worth stating before
using the document further.** Phase 5's bullet list calls the whole
translate→review→predict→run→card loop *"Tier-1 (parametric),"*
without distinguishing path 1 from path 2 the way `docs/PROPOSALS.md`
§2.1/§5a precisely does (`docs/PRACTICE.md`'s own recorded instance of
this exact conflation, found while answering a question about this same
pair of documents days before this paper). This paper uses `docs/
PROPOSALS.md`'s precise terminology — tier 1 is path 1 or path 2,
either way a proposal the simulator *could* represent — and treats
`CHARTER.md`'s "tier-1 (parametric)" as the informal name for that same
thing, not a third category.

## 2. What makes this honest, and it is not obvious

The obvious failure, named in the brief that commissioned this paper:
**a ranking of other people's ideas, produced by a tool that cannot
measure what makes an idea worth doing.** oneground measures recall,
latency, cost, storage — quantities a simulation or a real engine
produces. It has never measured, and this paper's §5 rules it may never
estimate, *implementation effort*, *strategic value*, or *how good an
idea is*. A triage design that outputs anything shaped like those
things would be the first place this product manufactured a number it
has no basis for.

What triage *can* honestly say is narrower and comes entirely from two
places already in the tree: **what the tool measured about the
refusal event itself** (how many times, on what corpora, naming what
missing family or parameter), and **what the proposer declared** (the
sentence or policy that was refused, verbatim, the same way a card
carries a rationale — `docs/PROPOSALS.md` §2.2: *"quoted in the card,
never an input to a verdict."*). Neither is a judgement about the idea.
Both are facts about what already happened.

## 3. Three scoping decisions, ruled 25 September 2026

### 3.1 What is triaged

**Ruled: proposals `propose` refused — specifically the refusals
`validate_policy` raises for a family or parameter that does not exist
— not cards tier 1 produced.** *The developer's own reason: triaging
cards would collide with `docs/LIBRARY.md` §3's refusal to score them,
and a refused proposal has no result to rank by, so this ruling avoids
that collision by construction.*

`plan_proposal` (`oneground/proposals/propose.py`) refuses for several
reasons, and they are not one kind of thing. Checked directly: a missing
`simulate.json`, no baseline row for the named configuration, a baseline
row that moved since the prediction was written, a pinned library that
differs from what measured the baseline, a corpus file that no longer
hashes to what `characterize` recorded, a directory already holding a
different prediction — every one of these is **procedural**: something
about *how* the run was set up, saying nothing about whether the idea
behind it is worth pursuing. Only `validate_policy`'s refusals —
`NO_SCOPE` (a policy naming a `scope`, which no family has) and *"no
model family named %r"* (a family or parameter this codebase has not
built) — are refusals **about the idea itself**: the simulator
genuinely cannot represent what was asked for. Those, and only those,
are this paper's candidate pool. A card tier 1 *did* produce is not a
triage candidate — it already ran, already has a `held`/`did_not_hold`/
`couldnt_check` verdict, and is a `docs/LIBRARY.md` question, not a
`docs/CHARTER.md` Phase 5 one.

*What the rejected alternative would have cost, kept for record.*
Triaging cards would have meant triaging *results* — a card carries a
predicted delta, a measured one, a budget verdict — which is closer to a
leaderboard `docs/LIBRARY.md` §3 already refuses outright (*"Rank
corpora, or cards across corpora... The library sorts and filters; it
does not score"*). Refused proposals have no result to collide with that
refusal over.

### 3.2 Whose hours

**Ruled: the developer's own review queue for structural proposals, per
Phase 5's own wording — "maintainer-reviewed" — not a user-facing
feature.** *The developer's own reason: a stranger shown a sorted list
of ideas the tool cannot build reads it as a roadmap the tool is
proposing.*

Nothing in `CHARTER.md` says a user ever sees this queue; "maintainer-
reviewed" names one reader. A maintainer reading their own refusal log
already knows it is not a verdict, the same way `docs/INTERFACE.md`'s
write half is legible to a maintainer who knows what a supervisor is and
would not be to a stranger handed the same page cold.

*What the rejected alternative would have cost, kept for record.* A
user-facing feature would need the same disclosure discipline `docs/
PROPOSALS.md` §2.1 gives a model-translated policy — who is being shown
this, on whose authority, with what statement of what it is not — before
it could ship at all.

### 3.3 What it may use

**Ruled: only what the tool already measured, plus what the proposer
declared. Never an estimate of implementation effort.** *The developer's
own reason: an invented effort figure would be the first unfounded
number in this product, and refusing to be where that number first
appears is the correct instinct.*

The tool has no way to see effort — it is not a fact about a corpus, a
configuration, or a measurement, it is a fact about a codebase and the
people who would change it, neither of which oneground has ever
modelled. Every other quantity in every other position paper is
measured, declared, or explicitly `couldnt_check`.

*What the rejected alternative would have cost, kept for record.* An
estimate of effort would need its own position paper before this one
could cite it, on the same "exam before the code" convention every other
measured quantity in this product was given — not written speculatively
here on the chance a future ruling asks for it.

## 4. What is measured, what is declared

Per refusal event, once a durable record exists (§7):

| field | kind | source |
|---|---|---|
| the family or parameter named as missing | measured | parsed from the `PolicyError` message, the same string a terminal sees today |
| how many times this same missing family/parameter has been named | measured | a count over the durable record, real arithmetic over real rows |
| which corpus characterization(s) the refusals cluster around | measured | the five measures already computed by `characterize`, read from each refusing run's own workdir |
| the sentence or policy that was refused | declared | the proposer's own words, quoted verbatim, `docs/PROPOSALS.md` §2.2's rule for a rationale applied here |
| whether the refusal came from path 1 or path 2 | declared | `authored_by` on the attempted policy, the same field §2.1's disclosure already defines |
| when | measured | a timestamp on the durable record |

**Never present**: an effort estimate (§3.3), a value or priority score,
a single merged ranking across different missing families (§5).

## 5. What the design refuses

**Never a single ranked list presented as a verdict.** The brief that
commissioned this paper states the expectation and this paper agrees
with the reasoning under it, stated precisely: the only honest signal
available is *frequency of a specific named gap* and *which corpus
shapes it clusters around* — real counts, real measurements. A single
ranked list forces those into one total order, which manufactures a
claim neither signal supports on its own: three refusals naming
`filtered_search` and one naming `streaming_index` is not evidence that
filtered search is worth three times the attention, only that it was
asked for three times. Collapsing frequency into rank is the same move
`docs/LIBRARY.md` §3 refuses for cards — *"This change held in 12 of 17
published cards" is a sentence about publication behaviour, not about
the change* — one level up: a count of refusals is a sentence about what
was asked for, not about what is worth building.

**What triage may output instead, following from §4 directly: refusals
grouped by the specific family or parameter they named, each group
carrying its own count and its own list of the individual declared
refusals inside it — unordered across groups, or ordered only by the one
measured quantity a group actually has, its count, stated as a count and
not disguised as a rank.** A maintainer reading five groups, sized 9, 4,
3, 2, 1, has been shown real arithmetic; a maintainer reading five
gaps in a numbered list from 1 to 5 has been shown this paper's own
prohibited shape wearing different words. The distinction is not
cosmetic: a count can be recomputed and checked against the record it
came from; a rank cannot be, because "worth" was never in the record.

**Two things tier 1's own discipline settles here, answered from the
material rather than assumed.**

*Does triage inherit the calibration-tolerance refusal to rank two
options that measure too close to call?* Not the same mechanism,
because it does not apply — `docs/PROPOSALS.md` §2.4's two-run rule
(`|delta - threshold| < tolerance` → `couldnt_check`) compares a
**measured** delta against a **predicted** threshold, and a refused
proposal was never run: there is no delta to be within tolerance of, on
either side. What does carry over is the discipline the tolerance rule
is *for* — never assert an ordering finer than the signal supports.
Triage's version of it is §5's own refusal above: count, don't rank,
because a count is the only quantity here with anything to be close to
the truth of.

*Does a triage record ever get promoted into something like a card?*
Not by this paper. A refusal group reaching a count that makes it worth
a family being built is a `docs/FAMILIES.md` decision — building a new
family is a contribution, not a proposal — and this paper's own §3.3
default already refuses to be the place that decision gets made
automatically. Triage surfaces the count; a person reads it and decides
whether it is a family worth building, the same separation `docs/
PROPOSALS.md` §2.1 draws between a model producing a policy and a human
approving it.

## 6. What this position does not settle

- Whether a refusal's declared sentence, once recorded, is shown to
  anyone besides the maintainer default of §3.2 — a retention/privacy
  question this paper's scope does not reach.
- Whether the durable refusal record (§7) is the same `jobs.json`
  mechanism `docs/INTERFACE.md`'s write half already has, extended, or a
  separate ledger purpose-built for this — an implementation choice for
  whoever builds §7's first item, not ruled here.
- How long a refusal stays in the queue, or whether it is ever removed —
  `docs/LIBRARY.md` §2.4 faced the equivalent question for a denominator
  and answered it with an append-only ledger; whether the same answer
  is right here is not decided by citing that it worked there.
- Whether `docs/LIBRARY.md`'s own dependency claim — *"depends on the
  library existing first"* (§6) — still holds now that the library's
  card schema and validator are built (task 058) but no card has ever
  been submitted through them. This paper does not resolve that
  dependency; it notes that the premise it rested on (nothing of the
  library built yet) is no longer entirely true, and leaves the
  question open rather than assuming either answer.

## 7. Sequencing

**Not before a refusal is durably recorded**, per §0 — a ranking
paper's design is premature ahead of the record it would read, and this
paper's own §4/§5 already assume that record's shape without building
it. The first implementation is the smallest thing `validate_policy`'s
refusal can be turned into: a receipt, written where the refusal
happens, carrying exactly `docs/PROPOSALS.md` §2.2's own two provenance
lists (what was measured about the corpus, what did the measuring) plus
the family/parameter named and the sentence or policy declared. No
grouping, no counting, no output shape from §4/§5 — those read the
record once one exists to read.

§3's three defaults are ruled (25 September 2026), so the record's shape
follows the rulings above directly rather than waiting further —
§3.1 in particular decides what a "refusal" is to record, and it is
decided.

*The exam, before the code.*
