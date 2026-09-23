# How this project works on itself

The rest of `docs/` specifies what oneground measures. This page is the other
thing: how the project works on itself — how it writes its own briefs, its own
checks, and its own record of what it found.

**The constraint on this page, which is the reason it can be trusted.** Every
rule here was paid for, and every rule carries the instance that produced it.
Nothing goes in that has not cost something.

It is not a style guide. There are no preferences here, no formatting
conventions, and nothing imported from elsewhere because it sounded right. A
rule that cannot name the day it was learned and what it cost is a rule nobody
has tested, and it will be followed exactly as far as it is convenient. If you
want to add one, bring the instance.

---

## 1. A section that states a current state goes stale silently

**The rule.** Nothing fails when the world moves and the sentence does not.

A section stating a **rule** is either wrong the moment it is written or not
wrong at all. A section stating a **current state** — what is blocked, what
the count is, which branch demonstrates the fix, who is waiting on whom — is
correct when written and decays afterwards without anything going red. No test
covers prose. No reviewer re-reads a paragraph they approved last month. The
decay is silent by construction, which is what separates this from an ordinary
mistake: a wrong rule gets argued with, and a stale state gets believed.

So a state-bearing section is a **liability the document carries**, and
somebody pays it down by hand or nobody does. Write fewer of them. Where one
is necessary, make the document say that it is one.

**The instance.** `tasks/README.md` carried a section headed *Currently
blocked*. It said task 041 could not start until `task-039` merged. Both had
merged and 041 had shipped. The section had been false for months — in the
file a build agent reads first to learn how tasks work — and nothing had
reported it, because there is nothing that could have.

**The repair, which is the part worth copying: empty it, do not delete it.**
The heading was doing a real job; it was the contents that had gone stale.
Deleting it removes the place the next blocked task has to say so, and the
next blocked task then says so somewhere worse, or not at all. It now reads
*Nothing*, followed by a line naming what kind of section it is and why it is
empty. **A state-bearing section that admits to being one** is the cheapest
version of this to keep honest, because the admission is itself a rule and
rules do not go stale.

### 1.1 Correct the checklist in the same pass as the argument

**The rule.** When you correct a document, correct its checklist in the same
pass — **the acceptance is where an implementer looks last and trusts most**,
so a stale line there outranks a corrected paragraph three sections above it.
This is §1 at its sharpest: an acceptance criterion is a state-bearing
sentence wearing the clothes of a rule.

A brief is also corrected **in place** rather than superseded by a second
file. Two documents sharing a number is how one gets built and the other
forgotten. Fold and delete, and say in the commit what was kept.

**The instance.** `tasks/045-report-code-findings.md` was corrected twice, and
both times the correction landed in the body and left the acceptance behind.

- The acceptance asserted a rule over *"all 29"* couldn't-check constructs in
  `verdict.py`. 29 was a `grep -c COULDNT_CHECK` over a file that also defines
  the constant, lists it in `OUTCOMES`, defaults a field to it and compares
  against it four times. Parsed, the file constructs **20**. An implementer
  building to that line would have gone looking for nine verdicts that do not
  exist.
- The acceptance asked for a tracked case exercising the
  `not_verifiable_here` path — wording that predated the correction which
  established that this kind *already* routes and *already* carries a remedy.
  A case built on it **passes the day it is written**, and proves only that a
  different branch was taken. The brief's own body warned against exactly this
  three paragraphs above the line asking for it.

Both survived a document that was otherwise right, because a correction is
read as an argument and an acceptance is read as a list.

---

## 2. Checks that do not check

These were `docs/FAMILIES.md` §4.1 until this page existed. They are a general
taxonomy of ways to build a check that reports something other than what it
appears to report, and only the first two are about the conformance suite that
produced them. **The numbers are preserved** — task reports cite *§4.1 warning
5* by number, and those citations resolve here.

**The conformance suite was wrong three times before it was right, and four
more mistakes have been recorded since.** Not about the families — about
itself. The first three each produced a confident, specific, false result on a
shipped family. Warnings 4 and 5 were made while adding the tenth check, by an
author who had read the first three. Warnings 6 and 7 come from other packages
entirely.

They are recorded because the next person to add a check will make the same
kind of mistake in a new place, and because **knowing the list is not the same
as not making them** — warnings 4 and 5 are the proof of that.

**1. It reported a knob that does nothing, and the knob works.** It said
`candidates` was declared and never read, in all three families. `candidates`
is read only when `rerank` is `exact`, and the suite's grid never set that. A
check that asks *"was this key read?"* without first asking *"could it have
been?"* reports its own coverage gap as the family's defect.

> The rule: before asserting a key is unread, satisfy its `belongs_to`. If you
> cannot, the outcome is **couldn't-check**, not **fails**.

**2. It reported `M` and `efSearch` unreachable in every family, because it
reimplemented a rule that already existed.** It tested belonging with
`config.params.get("index") in ("hnsw",)`. But `index` **elides at its
default** — that is deliberate, so that adding the key rewrote no published
label — so `params` has no `index` key at all in an HNSW configuration and the
test was false everywhere. The validator's own `_belonging_problem` resolves
the default and gets it right.

> The rule: **call the function the tool already uses.** A second
> implementation of a rule is a second place for it to be wrong, and this one
> disagreed with the first in the most common case there is.

**3. A check passed for the wrong reason, which is worse than one that
fails.** *Refusals, not crashes* fed `nlist=1501` to `single_node_hnsw` and
saw a `ParameterError`, so it passed. The refusal was about **belonging** —
`nlist` is an IVF setting and the configuration was HNSW — and said nothing
whatever about size. The family had not been tested and the suite reported
green.

> The rule: **a passing check must be able to fail.** Before trusting one,
> break the thing it tests and watch it go red. That is what the mutants in
> `oneground/models/test_family_conformance.py` are: seven families that each
> violate one requirement, asserting the suite names *that* check and not
> another. Add a mutant with every check.

The shape all three share: **the suite was measuring itself and reporting the
family.** A green result and a red result are both claims, and a check you
have not watched fail is not evidence of either.

**4. A held measurement was downgraded to couldn't-check because a stronger
claim was unproven.** `fanout matches the build` asserts that a family's
fan-out is within its shard count. It held on every configuration of every
family. The first version reported **couldn't-check** anyway, reasoning that a
family reporting the requested count and one reporting the built count would
look identical wherever the two agree — so the result did not prove the family
reads the build.

That reasoning is true and it is about a different claim. The check asserts a
bound; the bound was measured and it held. Reporting couldn't-check said no
measurement was available when one was.

> The rule: **couldn't-check is for what was not measured, not for what was
> measured weakly.** This is the hedge form of the error the three outcomes
> exist to prevent, and it is the exact inverse of rounding an unknown up to a
> verdict — equally wrong, and more tempting, because it feels careful. If a
> check's evidence is weaker than a reader might assume, **say how strong it
> is** in `meaning`, and let the outcome report what was actually found. A
> check that answers couldn't-check on a healthy tree teaches its readers to
> ignore it.

**5. A mutant that does not run the rule's own code proves only that the
defect is reproducible.** Warning 3 already says to add a mutant with every
check. The first mutant here restated the rule — it asserted `fanout >
shards` for a deliberately broken family — and passed. It would have gone on
passing if the check itself had been deleted, because it never called it.

> The rule: **a mutant runs the check, not a copy of it.** Break the family,
> hand it to `run_conformance`, and assert the suite names *that* check with
> `FAILS`. Assert too that the unbroken family passes the same check on the
> same corpus, so a failure is the mutation and not the fixture. A rule and a
> mutant that share no code drift apart, and the day they do, the mutant is
> still green and proving nothing.

**6. A check that skips where it would fail.** Neither instance is in the
conformance suite. Both were found in one week, in different packages, and
they are the same mistake.

Task 041 tracked a regression fixture and added a presence check for it. The
presence check failed correctly when the file was removed — and the
*regression test itself* still skipped, because the helper it shared with
every other test in the module skipped on any missing path. The check that
proved the feature worked would still have gone silent, now with a second test
failing beside it saying something else.

Task 045 then found the general form. A test asserting that every
couldn't-check claim carries a remedy reads a local workdir. In CI there is
none, so it **skips**, and the suite is green. It is red only on a machine
that happens to hold that workdir.

> **A check that passes everywhere it runs, and only runs where nobody looks,
> reported nothing for as long as it existed.**

> The rule: **a skip is a claim, and it needs the same scrutiny as a pass.**
> Decide per input: something that may honestly be absent elsewhere — a local
> run, an optional binary — may skip, and the skip must name what was missing.
> Anything tracked, or anything the check exists to protect, **fails**. And
> test the skip the way warning 3 says to test the pass: remove the input and
> watch which of the two you get. Reading the code will not tell you; the
> helper that decides is usually three functions away and shared with tests
> that have every right to skip.

The shape warnings 3, 5 and 6 share: **a green result is a claim about the
world, and the three ways to make one without evidence are to pass for the
wrong reason, to check a copy of the rule, and to not run at all.**

**7. A test that demonstrates a fix by building the defective case is coupled
to that case remaining buildable.** Task 042c fixed `fanout` so that it
reports the shards that were built rather than the ones requested, and proved
it with a configuration asking for `len(x) + 1` shards over `len(x)` vectors.
Task 042d then made that configuration a refusal — a partition cannot have
more shards than there are vectors — and 042c's test broke.

**The fix was not broken. The test's setup had become illegal.** Those are
different failures and they look identical from the failure message: an
exception from the code under test, raised during setup, in a test that passed
yesterday.

> The rule: **when a test breaks because a refusal closed the boundary it was
> standing on, change its input, never its assertion.** 042c's property — the
> fan-out follows the artifact — is still true and still needs testing; a hash
> partition leaves shards empty by collision well before it runs out of
> vectors, so `len(x)` shards exercises it legally. Weakening the assertion,
> or the new refusal, would discard a fix to keep a test.
>
> The tell, before it happens: **the test's setup is the thing a refusal would
> forbid.** A test constructing an impossible configuration on purpose is
> sitting on a boundary somebody will eventually close, and the two tasks are
> usually weeks apart and written by different people.

**This will recur.** The conformance suite exists to find configurations that
should be refused, so every refusal it produces is a new boundary, and any
test standing on one breaks when it lands. That is the suite working, and the
repair is the input.

---

## 3. A gated commit runs in the foreground

**The rule.** A command that runs the suite and commits if it passes is run in
the foreground, and the next one does not start until it has reported.

**The instance.** Two such commands were backgrounded at once, in task 041.
The first had not reported when the second started, so its files were still
staged; the second's `git add -A` swept them up, and its commit message —
which described only the comparability work — would have landed on a commit
containing three steps' worth of changes.

**The gate held.** Nothing was half-committed, because the commit could not
run until pytest passed, and stopping both left the tree exactly as it was.
What failed was not the gate but the sequencing around it, which no gate
covers.

**The second instance, which is why the rule says *gated* and not just
*foreground*.** Writing this page, the author ran
`pytest -q 2>&1 | tail -5 && git commit`. In a pipeline the exit status is the
*last* command's, so the gate's condition was `tail` succeeding, which it
always does. The suite had in fact failed collection on 18 modules — the wrong
interpreter, no `yaml` — and the commit ran on a red tree, with a message
saying it was gated.

> The rule: **check that the gate is load-bearing before trusting it.** A
> pipe, a `; ` where `&&` was meant, a `tee`, a wrapper script that swallows a
> status — each turns a gate into a decoration, and every one of them still
> prints the failure to the screen, which is what makes it survivable and what
> makes it easy to miss. This is warning 3 one level up: **a gate that cannot
> block must be watched blocking**, exactly as a passing check must be watched
> failing.

The reason it matters more here than in most repositories: **a commit message
that misdescribes its own diff is a receipt that lies.** It is the same class
of defect as a citation naming the wrong field — which is the thing task 041
existed to have found — and it is worse in one respect, because a citation can
be re-derived from the artifact and a commit message cannot be re-derived from
anything.
