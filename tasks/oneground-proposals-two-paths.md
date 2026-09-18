# oneground — proposals: the two paths

*19 September 2026. A revision to `docs/PROPOSALS.md`, settling the
question §2.1 left open: which model, and where it runs. The answer is
that the user chooses, and the choice is visible on everything that
results. To be merged into the position paper as a replacement for §2.1
and an addition to §2.4.*

---

## The ruling

A proposal reaches the simulator as a **policy** — a small structured
document naming a shipped family and a change to one of its declared
parameters. There are two ways to produce one, both first class, and they
are told apart everywhere the result is seen.

### Path 1 — write the policy

    oneground propose <workdir> --policy policy.yaml --prediction pred.yaml

No model is involved, no network is touched, and nothing about the corpus
leaves the machine. This is what tier 1 built and what runs today. The
card records `authored_by: user`.

### Path 2 — describe it

    oneground propose <workdir> --describe "probe a second region for the
      ambiguous queries" --model <provider:name> --prediction pred.yaml

A model translates the sentence into a policy. The command **refuses
without an explicit `--model`**: there is no default, none is bundled, and
a local endpoint (`ollama:<name>`, or any OpenAI-compatible URL) is as
first class as a hosted one. A user who has not chosen gets a refusal,
never a surprise.

The user approves the **policy**, not the sentence. The translation is
shown in full, beside a plain-English rendering of what it will do, and
nothing runs until it is approved. A translation the user would not have
approved must not run because the sentence sounded reasonable.

---

## What path 2 must disclose, and where

The disclosure travels with the artifact, not with the documentation. A
card that leaves this machine carries, on its face:

- `authored_by: model`, with the provider, the model name and version,
  and the sampling parameters used;
- the sentence as typed;
- the policy as produced, verbatim;
- the prompt sent and the response received, recorded as **declared**
  receipts in the proposal's directory — a model's output is not
  re-derivable, so it is declared, not a receipt;
- the fact that the user approved this policy before it ran.

A reader must never have to wonder how a policy came to exist. This is the
same rule as the lab's projection caption: the disclosure is part of the
artifact, because a screenshot separates a claim from its footnote and a
forwarded card separates it from its documentation.

**What the model is shown, and nothing else:** the corpus's
characterization (five measures), the current configuration, the
constraint set, and the user's sentence. Not vectors, not text, not ids,
not filenames. That boundary is tested, and a card records that it held.

---

## What path 2 must refuse

- **To invent a family or a parameter.** The output is validated against
  each family's declared parameter table before the user sees it; an
  unknown name is refused with the declared list, not repaired.
- **To express what the simulator cannot represent.** Most genuinely new
  ideas come back as *this requires a family that does not exist* — which
  is the honest answer and will be the common one. A plausible-looking
  policy for an idea the simulator cannot represent is the failure mode
  to refuse, not to accommodate.
- **To run without approval.** There is no `--yes`, and there is no
  non-interactive translation path. The money-boundary rule from the pod
  helper applies here for the same reason: the step that commits you to a
  result is the step a human takes.
- **To be trusted about its reasons.** The rationale is quoted on the
  card as the model's stated reason, marked as such, and is never an
  input to a verdict.

---

## Why both paths, rather than one

Path 1 alone makes the product honest and small: no model, no network, no
question about what was sent where. It also asks a user to learn a YAML
schema and a family's parameter names before they can ask a question,
which is the barrier the feature exists to remove.

Path 2 alone makes the product useful and unfalsifiable: every result
carries a translation step nobody can audit, and the tool's central claim
— that you can check it — weakens at exactly the point a user is least
able to.

Both, told apart on every artifact, keeps each claim intact. A card from
path 1 is as checkable as anything else the tool produces. A card from
path 2 is checkable too, with one more declared step in its provenance
that the reader can see and weigh.

---

## What this does not settle

- Whether a model's translation is good enough to be useful at all. That
  is measurable — the same sentence, several models, the policies
  compared — and it has not been measured. Until it is, path 2 ships with
  no claim about translation quality.
- Adversarial review, which the position paper leaves undecided and which
  this revision does not decide either. If built, it inherits both
  models' blind spots and is advisory, coloured separately, never a
  verdict.
- Whether a card whose policy was model-written should be marked
  differently in the public library. The library position requires the
  provenance; whether readers should be able to filter on it is a library
  decision, not this one.
