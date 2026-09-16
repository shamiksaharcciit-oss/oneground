# oneground — proposals: the position, before the code

*17 September 2026. Written before implementation, in the order the
chunking position was written: the exam before the code. This is what the
proposal loop will be built against, and what it will be forbidden from
claiming. Nothing here is a date.*

---

## 1. What a proposal is

A person who is not a retrieval engineer describes a change in plain
words — *"store the recent documents separately"*, *"probe three regions
instead of two for the ambiguous queries"*, *"split the biggest shard"* —
and the system turns that into something testable on their own corpus,
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
  every response received is written to the run's workdir as a receipt.
  A user can read exactly what was transmitted. This is not optional and
  there is no quiet mode.
- **Nothing about the corpus contents is sent.** The model sees the
  characterization (five numbers), the current configuration, the
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
  changes:
    - param: probe                  # a named parameter of that family
      from: 2
      to: 3
      scope: queries_where_ambiguous # a named, shipped predicate
  rationale: "…"                    # the model's words, quoted, never executed
```

The rules:

- **Every field is from a shipped enumeration.** Families, parameters and
  scopes are those oneground implements. A policy naming anything else is
  rejected with what was named and what exists.
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

**Answer: a signed statement, written before the run, of what would count
as the proposal working — precise enough to be wrong.**

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

- **It is written and hashed before the run.** The card cites both
  hashes; a prediction edited after a result is a different prediction
  and the hash says so.
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
hold**, **couldn't check** — computed by the same verdict rules the report
uses, under the same claim invariant.

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
- No prediction without a metric, a direction and a threshold.
- No card without a hash of the prediction that preceded the run.
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

## 6. Sequencing

Not before the lab ships. Not on a deadline. The first implementation is
the schema, the validator and the prediction file — the parts with no
model in them — so that the loop's refusals exist before its capabilities
do. The model comes last, which is the opposite of how it would be built
if the goal were a demonstration.

*The exam, before the code.*
