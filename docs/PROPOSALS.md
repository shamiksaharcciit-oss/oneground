# oneground — proposals: the position, before the code

*17 September 2026. Written before implementation, in the order the
chunking position was written: the exam before the code. This is what the
proposal loop will be built against, and what it will be forbidden from
claiming. Nothing here is a date.*

---

## 1. What a proposal is

A person who is not a retrieval engineer describes a change in plain
words — *"store the recent documents separately"*, *"probe three regions
instead of two"*, *"split the biggest shard"* — and the system turns that
into something testable on their own corpus, or says which family it would
need,
predicts what it will do **before** running it, runs it, and publishes a
card saying whether the prediction held.

The value is not the idea. Ideas are cheap and most are wrong. The value
is that a wrong idea costs ten minutes and produces a receipt, instead of
costing a quarter and producing an argument.

---

## 2. The four questions, answered

### 2.1 Which model, and where does it run

**Answer: there are two paths to a policy, both first class, and they are
told apart everywhere the result is seen.** *(Ruled 19 September 2026,
replacing this section's earlier answer.)*

A proposal reaches the simulator as a **policy** — a small structured
document naming a shipped family and a change to one of its declared
parameters (§2.2). There are two ways to produce one.

**Path 1 — write the policy.**

    oneground propose <workdir> --policy policy.yaml --prediction pred.yaml

No model is involved, no network is touched, and nothing about the corpus
leaves the machine. This is what tier 1 built and what runs today. The card
records `authored_by: user`.

**Path 2 — describe it.** Two phases, and the translation is written down
between them:

    oneground propose translate <workdir> \
        --describe "probe a second region for the ambiguous queries" \
        --model <provider:name>            # writes policy.yaml, and stops

    oneground propose <workdir> --policy policy.yaml --prediction pred.yaml

A model translates the sentence into a policy. The command **refuses
without an explicit `--model`**: no model is bundled, none is default, and
a local endpoint (`ollama:<name>`, or any OpenAI-compatible URL) is as
first class as a hosted one. A user who has not chosen gets a refusal,
never a surprise.

**The user approves the policy, not the sentence.** `translate` writes the
policy to a file and stops; the second phase runs a policy the user has
read. Approval is that act — reading what was written and choosing to run
it — not a prompt to click through, and a translation the user would not
have approved cannot run because the sentence sounded reasonable.

**After translation, path 2 *is* path 1.** The second phase is the command
tier 1 built: it takes a policy file and a prediction file, and contains no
model, no network and no sentence. The model's involvement is recorded in
the artifact, not carried in the mechanism — which is why the disclosure
below travels on the card rather than being inferable from how the run was
invoked.

**`--dry-run` is not the approval step.** It keeps the meaning it has:
validate everything, print what would run, write nothing. A step that
writes nothing cannot be the one that persists a translation for a user to
approve, and a flag is not an approval in any case.

#### What path 2 must disclose, and where

The disclosure travels with the artifact, not with the documentation. A
card that leaves this machine carries, on its face:

- `authored_by: model`, with the provider, the model name and version, and
  the sampling parameters used;
- the sentence as typed;
- the policy as produced, verbatim;
- the prompt sent and the response received, recorded as **declared**
  receipts in the proposal's directory — a model's output is not
  re-derivable, so it is declared, not a receipt;
- the fact that the user approved this policy before it ran.

**An unreported version is `null` with a stated reason, not a refusal.**
Providers report versions inconsistently and a local endpoint may report
none at all. The couldn't-check habit applies to provenance exactly as it
applies to a measurement: the card says the version was not reported and
by whom, rather than refusing a run over it or printing something that
looks like a version and is not.

**The sampling parameters are a closed list**: temperature, top-p, seed,
max tokens, and a digest of the system prompt. Each is recorded, `null`
where the provider has no such control, and adding to the list is a
deliberate change to this document — not whatever an implementation
happens to have logged. The point of the list is that two cards from the
same model are comparable, which an open-ended bag of provider fields
would not give.

A reader must never have to wonder how a policy came to exist. This is the
same rule as the lab's projection caption: the disclosure is part of the
artifact, because a screenshot separates a claim from its footnote and a
forwarded card separates it from its documentation.

**What the model is shown, and nothing else:** the corpus's
characterization (five measures, six numbers — drift is a pair), the
current configuration, the constraint set, and the user's sentence. Not
vectors, not text, not ids, not filenames. That boundary is tested, and a
card records that it held.

#### What path 2 must refuse

- **To invent a family or a parameter.** The output is validated against
  each family's declared parameter table before the user sees it; an
  unknown name is refused with the declared list, not repaired.
- **To express what the simulator cannot represent.** Most genuinely new
  ideas come back as *this requires a family that does not exist* — the
  honest answer, and the common one. A plausible-looking policy for an idea
  the simulator cannot represent is the failure mode to refuse, not to
  accommodate.
- **To run without approval.** There is no `--yes`, and there is no
  non-interactive translation path. The money-boundary rule from the pod
  helper applies here for the same reason: the step that commits you to a
  result is the step a human takes.
- **To be trusted about its reasons.** The rationale is quoted on the card
  as the model's stated reason, marked as such, and is never an input to a
  verdict.

#### Why both paths, rather than one

Path 1 alone makes the product honest and small: no model, no network, no
question about what was sent where. It also asks a user to learn a YAML
schema and a family's parameter names before they can ask a question, which
is the barrier the feature exists to remove.

Path 2 alone makes the product useful and unfalsifiable: every result
carries a translation step nobody can audit, and the tool's central claim —
that you can check it — weakens at exactly the point a user is least able
to.

Both, told apart on every artifact, keeps each claim intact. A card from
path 1 is as checkable as anything else the tool produces. A card from path
2 is checkable too, with one more declared step in its provenance that the
reader can see and weigh.

### 2.2 What the policy language may express

**Answer: a closed set of parameter changes over the existing families,
and nothing else. It is not a programming language and it never becomes
one.**

The model's output is not code and is not executed. It is a small
structured document — a *policy* — validated against a schema before
anything happens with it:

```yaml
policy:
  family: semantic_sharded          # one of the shipped families
  configuration: {centroids: 256, epsilon: 0.2, probe: 2, M: 32, efSearch: 96}
  changes:
    - param: probe                  # a named parameter of that family
      from: 2
      to: 3
  rationale: "…"                    # the model's words, quoted, never executed
```

The rules:

- **A policy is a parameter change over a whole configuration, full
  stop.** It names the configuration it changes, every parameter of it,
  and has no scope. A change to a subset of queries or vectors is *this
  proposal requires a family that does not exist*.
- **Every field is from a shipped enumeration.** Families and parameters
  are those oneground implements: every family declares its parameter
  table, and only keys whose role is *parameter* — the architecture, not a
  constant the family fixes, a run-level setting or a build switch — may
  change. A policy naming anything else is rejected with what was named
  and what exists.
- **No new code paths.** A policy selects among behaviours that already
  exist and are already tested. It cannot introduce a routing rule the
  simulator has not implemented — if the idea needs one, the answer is
  *this proposal requires a model family that does not exist*, which is a
  useful answer and an honest one.
- **The policy is shown to the user before it runs**, in full, with a
  plain-English rendering beside it. The user approves the policy, not
  the sentence. A translation the user would not have approved must not
  run because the sentence sounded reasonable.
- **The rationale is quoted, never trusted.** It appears in the card as
  the model's stated reason and is marked as such. It is never an input
  to a verdict.

Why so narrow: the moment a policy can express something the simulator
does not already measure, the loop can produce a result no rule can
check. The whole product is built on refusing that.

### 2.3 What a pre-registered prediction is

**Answer: a hashed statement, written before the run and cited by the
run's inputs, of what would count as the proposal working — precise enough
to be wrong.**

Before anything executes, the system writes to the workdir:

- the policy, hashed;
- the metrics the proposal is expected to move, each with a direction and
  a threshold (*recall@10 rises by at least 0.01*; *storage amplification
  does not rise above 2.0×*);
- the metrics that must **not** move beyond a stated bound — the
  side-effect budget, which is where most well-meaning changes die;
- the corpus, the sample, the seed and the configuration it will run
  against.

Three rules that make it a prediction rather than a description:

- **It is written before the run, and the run cites it.** The run records
  the prediction's sha256 in its own inputs as it starts. A prediction
  written or edited afterwards does not match that citation and is not
  judged. The hash says what the prediction is; the run's inputs citing it
  are what say it came first — a hash on its own shows a change, not an
  order.
- **A predicted change smaller than the calibration tolerance is rejected
  before the run, with the tolerance named.** A smaller difference cannot
  be told from noise, so the prediction could never be checked.
- **The model proposes the thresholds; the user approves them.** A model
  that sets its own bar after seeing the corpus would set it low.
- **"It will be better" is rejected.** A prediction with no metric, no
  direction or no threshold does not run — with a message naming what is
  missing. Unfalsifiable is not a kind of prediction.

### 2.4 What a card claims, and what it may not

**Answer: a card reports one run of one policy on one sample, and says so
in its own text.**

A card carries: the plain sentence, the policy, the prediction with its
hash, the measured result per predicted metric, the side-effect budget
against its bounds, and one of three outcomes — **held**, **did not
hold**, **couldn't check** — computed by a two-run verdict rule of its own,
under the same claim invariant.

**And how the policy came to exist** (ruled 19 September 2026, with §2.1's
two paths). Every card carries `authored_by`: `user` for a policy its user
wrote, `model` for one a model translated.

**It is a checked claim, not a field beside the claims.** A card's
sentences are `Claim`s rendered from what they cite and checked against it
before the card is written (`docs/CLAIMS.md`), and provenance is a sentence
like any other: a `proposal_provenance` claim, citing the run's own
`propose_info` record — the model named, the version or its absence, the
sampling parameters, the approval. The invariant asks that a sentence be
reconstructible from what it cites, not that what it cites be a
measurement, so a record of how the policy was produced is a legitimate
source for one. Metadata sitting beside the prose would be exactly what a
screenshot drops, which is the failure §2.1's disclosure rule exists to
prevent. A model-authored card carries,
on its face, the provider, the model name and version, the sampling
parameters used, the sentence as typed, the policy as produced verbatim,
and the fact that the user approved that policy before it ran; the prompt
sent and the response received are **declared** records in the proposal's
directory, digested in its manifest, because a model's output cannot be
re-derived from seeds and rules. A reader must never have to wonder how a
policy came to exist, and the disclosure travels on the artifact rather
than in this document — a forwarded card separates a claim from its
footnote. A prediction is about a difference between
two configurations measured in the same run, so the report's absolute
thresholds do not apply to it: a delta within the calibration tolerance of
the predicted threshold is *couldn't check*, as two recalls that close are
indistinguishable in the report.

What a card may never say:

- that the change is good, or recommended, or should be deployed;
- anything about a corpus other than the one it ran on;
- that a held prediction on a 20,000-vector sample will hold at full
  scale — the sample caveat is on the card, not in a footnote;
- anything at all when the run could not be completed: that is
  *couldn't check* with the reason, and a card is still published.

**Failures are published.** A library of proposals that only shows the
ones that worked is a marketing page. The failed cards are the more
valuable half: they are the record of what has already been tried on
corpora like yours.

---

## 3. What this design refuses, collected

- No model is default; none is bundled; nothing runs without an explicit
  choice.
- No corpus content is sent to any model, ever.
- The model's output is never executed. It selects among shipped
  behaviours or it is rejected.
- No translation runs without the user approving the **policy** it
  produced: `translate` writes it and stops, no `--yes`, no
  non-interactive translation path, and `--dry-run` is not the approval
  step (§2.1).
- No card without `authored_by` as a checked claim, and none from a model
  without the provider, the model and version (or a stated reason there is
  none), the five sampling parameters, the sentence, the policy verbatim,
  and the prompt and response as declared records.
- No scopes: a policy changes a whole configuration.
- No prediction without a metric, a direction and a threshold, and none
  below the calibration tolerance.
- No card without the prediction's hash, cited by the run's inputs.
- No claim beyond the sample, the corpus and the single run.
- No suppression of failed cards.

---

## 4. The honest limits, stated before anyone asks

- **A translation would be a model's guess.** Path 2 is not built, so
  nothing translates anything today; the limit is stated because it is the
  one the design is arranged around. A sentence can be turned into a policy
  the user did not mean, which is why §2.1 has the user approve the
  *policy* rather than the sentence, why the translation is written to a
  file and read before it runs, and why the policy appears on the card
  verbatim. How often a translation would be wrong is unmeasured — §5.
- **A held prediction is not a good decision.** It says one change moved
  one metric as predicted on one sample. Whether to deploy is still a
  judgement, and oneground does not make it.
- **The space of proposals is the space of shipped parameters.** Most
  genuinely new ideas will come back as *requires a family that does not
  exist*. That is the correct answer and it will be the common one.
- **A model reviewing a model's policy** — adversarial review, if it is
  built — inherits both models' blind spots, and any such row is
  advisory, coloured separately, and never a verdict. This is the D-row
  rule from the chunking position, applied here.

---

## 5. What is not settled here

- Whether adversarial review is worth building at all, given 4's last
  point. §2.1's ruling does not decide it either: if built, it inherits
  both models' blind spots and is advisory, coloured separately, never a
  verdict.
- **Whether a model's translation is good enough to be useful at all.**
  That is measurable — the same sentence, several models, the policies
  compared — and it has not been measured. Until it is, path 2 ships with
  no claim about translation quality.
- The public library: how a card from someone else's corpus is useful to
  you, and what it must carry to be comparable. That is its own position
  paper. It includes whether a card whose policy was model-written should
  be marked differently there: §2.1 requires the provenance on every card,
  and whether readers may filter on it is the library's decision.
- Tier-2 triage: which proposals are worth a developer's five hours.
  Unchanged from the original concept and unaddressed here.

---

## 5a. Tier 1: writing a policy yourself

*Built in task 028. Tier 1 is **path 1** of §2.1: you write the policy.
**Path 2 — the model-written one — is not built.** There is no `--model`
flag, no `--describe`, nothing sends anything anywhere, and §2.1's second
path is a ruling about what it must do if it is built, not a command that
exists. A card from tier 1 records `authored_by: user`.*

Tier 1 is this loop with the model removed: you write the policy, you write
the prediction, and the machinery does the rest. It exists so that the
receipts — the pre-registered prediction, the baseline citation, the two-run
verdict, the card — are proved before a model is anywhere near them.

    oneground propose <workdir> --policy <file> --prediction <file>
                                [--name <dir>] [--requirements <file>]
                                [--dry-run]

`<workdir>` is a run that `characterize` and `simulate` have both written.
The proposal measures **only the changed configuration**, on that workdir's
sample, seed and cached ground truth, and compares it against the baseline row
`simulate` already wrote.

### The two files

**The policy** — which family, which configuration, which parameter changes.
Validated against the family's own parameter table (§2.2):

```yaml
policy:
  family: semantic_sharded
  configuration: {centroids: 256, epsilon: 0.2, probe: 1, M: 32, efSearch: 96}
  changes:
    - param: probe
      from: 1
      to: 2
  rationale: "One probed region reaches one region's neighbours. Probe a second."
```

| field | means |
|---|---|
| `family` | one of the shipped families |
| `configuration` | the whole configuration being changed, every parameter named. It is what makes `from` checkable, and it has to be a configuration the workdir already has a measured row for |
| `changes` | one or more `{param, from, to}`. Only keys whose role is *parameter* may change — not a constant the family fixes, not the run-level `shard_depth`, not the build's `deterministic` |
| `rationale` | your words. Quoted in the card, never an input to a verdict |

**The prediction** — what the change must do, and what it must not do:

```yaml
expects:
  - metric: recall_at_10
    direction: rises              # rises | falls
    by_at_least: 0.05
side_effects:
  - metric: storage_amplification
    stays_at_or_below: 4.0        # or stays_at_or_above
```

`expects` is what would count as the proposal working. `side_effects` is the
budget — the metrics that must not move beyond a stated bound. The measurable
metrics are `recall_at_10`, `ceiling_at_10`, `storage_amplification` and
`fanout`.

The prediction is written to `<workdir>/proposals/<name>/prediction.json`
before anything is measured, and the run records its sha256 as one of its own
inputs. That is what says it came first.

### The refusals

Every problem is named in one run, not one per run:

* a policy naming a family, a parameter or a value that does not ship, or a
  `scope` anywhere — *this requires a family that does not exist*;
* a prediction with no metric, no direction or no threshold; a threshold below
  the calibration tolerance, with the tolerance named; a metric this does not
  measure;
* a workdir with no `simulate.json`, naming the command to run;
* **no baseline row** for the policy's `configuration`, naming the rows that
  are there and how to measure the one that is not;
* a **baseline row that moved** since the prediction was written — the row's
  own digest is in `prediction.json`, and a row that changed is not the row
  the prediction was made against;
* a corpus file that no longer hashes to what `characterize` recorded;
* a pinned library at a different version from the one the baseline row was
  measured under;
* a proposal directory that already holds a *different* prediction. An
  identical one is reused, never rewritten: that is how a run that could not
  complete is run again without losing the pre-registration.

`--dry-run` runs every one of these checks, prints what would be measured and
what would be written, and writes nothing.

### The card

`card.json` and `card.html`, in the proposal's directory. Both are written
whatever the outcome — a prediction that did not hold produces a card with the
same completeness as one that did, and a run that could not complete produces
a **couldn't-check** card naming why and what would settle it. There is no
path that produces nothing.

A card carries the policy in full, the prediction with its digest, both
configurations, the measured result per predicted metric, the side-effect
budget against its bounds, the environment, the calibration line the verdicts
were judged under, and one outcome: **held**, **did not hold**, or
**couldn't check** (§2.4's two-run rule). Every sentence is built as a
`Claim` and checked against the rows it cites — the same invariant the report
runs under, `docs/CLAIMS.md`.

**A breached budget is `did not hold`, and the card says so first.** A
proposal whose predicted metric moved exactly as promised and whose budget was
broken has not worked, and the breach is the headline rather than a footnote.

What a card may never say is a list in the code, scanned on every card: that
the change is good, recommended or should be deployed; anything about another
corpus; that the result would hold at full scale. The one sentence allowed to
use those words is the card's own limits sentence, which says them as denials.

### Worked example

From the run in `runs/arxiv-150k-via-characterize`, whose `simulate.json`
already holds `semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1]`:

    oneground propose runs/arxiv-150k-via-characterize \
        --policy proposal-a-policy.yaml \
        --prediction proposal-a-prediction.yaml

with the two files above. It measures the one changed configuration
(`probe=2`), judges `recall_at_10` against the predicted rise and
`storage_amplification` against its bound, and writes the card to
`runs/arxiv-150k-via-characterize/proposals/semantic_sharded_probe-1-to-2/`.
Task 028's report has that card, and a second one that the side-effect budget
stopped, in full.

---

## 6. Sequencing

Not before the lab ships. Not on a deadline. The first implementation is
the schema, the validator and the prediction file — the parts with no
model in them — so that the loop's refusals exist before its capabilities
do. The model comes last, which is the opposite of how it would be built
if the goal were a demonstration.

*The exam, before the code.*
