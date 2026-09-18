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

**Answer: the translation runs wherever the user says, and the default is
nowhere.**

oneground is local-first, and a proposal loop that silently sends a
description of the user's corpus to a hosted model breaks that in the one
place a user would least expect it. So:

- **No model is bundled and none is default.** The command refuses
  without an explicit `--model` naming a provider and a model, or a local
  endpoint. A user who has not chosen gets a refusal, not a surprise.
- **A local endpoint is a first-class option**, not a fallback:
  `--model ollama:<name>` or any OpenAI-compatible URL. The quality will
  be worse and the report says which model was used, so the difference is
  visible rather than hidden.
- **What leaves the machine is recorded verbatim.** Every prompt sent and
  every response received is written to the run's workdir as a *declared*
  record, digested in its manifest. Declared, not a receipt: a model's
  response cannot be re-derived from seeds and rules, so its bytes are
  frozen and hashed rather than reproduced. A user can read exactly what
  was transmitted. This is not optional and there is no quiet mode.
- **Nothing about the corpus contents is sent.** The model sees the
  characterization (five measures, six numbers — drift is a pair), the
  current configuration, the
  constraint set, and the user's sentence. Not vectors, not text, not
  ids. That is a hard boundary, tested.

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
under the same claim invariant. A prediction is about a difference between
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
- No scopes: a policy changes a whole configuration.
- No prediction without a metric, a direction and a threshold, and none
  below the calibration tolerance.
- No card without the prediction's hash, cited by the run's inputs.
- No claim beyond the sample, the corpus and the single run.
- No suppression of failed cards.

---

## 4. The honest limits, stated before anyone asks

- **The translation is a model's guess.** A sentence can be translated
  into a policy the user did not mean. That is why the policy is approved
  rather than the sentence, and why the policy appears in the card.
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
  point.
- The public library: how a card from someone else's corpus is useful to
  you, and what it must carry to be comparable. That is its own position
  paper.
- Tier-2 triage: which proposals are worth a developer's five hours.
  Unchanged from the original concept and unaddressed here.

---

## 5a. Tier 1: writing a policy yourself

*Built in task 028. **The model-written tier is not built.** There is no
`--model` flag, nothing sends anything anywhere, and §2.1 describes a design,
not a command that exists.*

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
