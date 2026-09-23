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

**Its first evidence arrived within hours of the page existing**, and it is
worth stating plainly because it is the whole claim being made for writing
these down. The day §2's warnings moved here, a test in
`oneground/test_comparability.py` broke on `main` for exactly the reason
warning 7 describes, and had stayed green in CI for exactly the reason warning
6 describes.

**Neither warning prevented it.** Both were written before this page existed
and neither was in front of the person who wrote the test. What the page
bought was the *diagnosis*: the failure was named, placed against two rules
and ruled on in one pass, instead of being repaired as the one-line assertion
change it superficially looked like — which would have left the coupling in
place to break again on the next legitimate change. A catalogue of ways to be
wrong does not stop you being wrong. It shortens the distance between the
symptom and the decision.

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

### 1.2 Claim less rather than schedule a correction

**The rule.** If you can see, as you write a sentence, that it will need
editing in two commits' time, it is **already stale** — write the weaker
sentence that will still be true, and stop. The weaker claim almost always
costs nothing.

**Why this is not §1 restated**, which is worth stating because they are one
paragraph apart. §1 is about a sentence that goes stale *silently*, after the
fact, with nothing to report it; the repair is an audit somebody has to
remember to do. This is the same decay caught at a different moment — **while
you are writing it, when you already know** — and the repair is a word. Same
subject, different moment, different detection, and a fix two orders of
magnitude cheaper. It sits under §1 because a reader looking for either
should find both.

**The instance.** The `oneground ui` page carried the line *"served from this
machine · read-only · nothing runs from this page."* Task 046's step 1 gave it
a write half, so **read-only** became false the hour the form landed.

The obvious repair was to change `read-only` and leave the rest. But *nothing
runs from this page* is step 3 of the same brief — jobs — so that clause was
scheduled to become false too, in a commit already specified and already
agreed. Rewriting it now and again in a fortnight is two edits and one window
where the page misdescribes itself.

So the line says what is true and stops: *"served from this machine · reads
runs, writes requirements files."* No claim about what does or does not run,
because that claim is in motion.

> The tell: **you are about to write a sentence and you already know which
> commit falsifies it.** Almost every time, the claim is not load-bearing and
> the weaker one reads no worse. When it *is* load-bearing — when the reader
> genuinely needs to know that nothing runs from this page — the answer is not
> a hedge but a mechanism, something that fails when the claim does, which is
> §1's "state-bearing section that admits to being one" one level further in.

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

**A second instance, and it is a test rather than a module** — which is the
half of this rule that is easy to miss, because a test does not look like an
implementation of anything. It looks like a check *on* one.

Task 046 gave the lab a write path, so `guard.py` gained
`WRITING_MODES = ("w", "a", "x", "+")` and a parsed scan that reads it. The
read half's `test_the_server_has_no_write_path` had carried its own scan since
041: a search for a quoted `"w"` anywhere in a served module's source. It
failed the same hour — on `guard.py`, **on the constant that spells out the
rule it was enforcing**.

It had also been weaker than it looked for as long as it had existed, and
nothing had said so. `os.replace` moves a file into place and carries no
quoted mode at all, so a served module that renamed its way to a write would
have passed a test whose name says no served module writes.

> The tell: **a rule gaining a declaration breaks its own restatement.** The
> check and the rule had drifted apart long before anything went red, and
> nothing could report the drift while the rule existed only inside the check.
> The day it was written down as data, the restatement failed on the
> declaration itself.
>
> That is the cheapest notice this class of defect ever gives, and it arrives
> only if the declaration lands somewhere the restatement can see. So when you
> replace a convention with a declaration, **run the old checks before
> deleting anything**: the ones that break on your new constant are the ones
> that were restating you.

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

**A third instance, the day this moved onto the page**, and it is the
permitted kind of skip rather than a violation, which is what makes it worth
recording. Task 043 fixed `facts_of` to read the measuring machine; that made
`machine` answerable and broke a test in `oneground/test_comparability.py`
that had asserted otherwise — and the break **landed on `main` green**, because
that test skips wherever `runs/` is absent, which is CI. The skip names what
is missing and the workdirs are a local run, so the rule above allows it.

> So the residue is the point: **even a permitted skip means the break lands
> green, and the cost moves to whoever holds the data.** What the rule buys
> there is not prevention but knowing where to look — when the suite is green
> and a machine with the artifacts is red, **the difference is the skips**, and
> that is the first place to look rather than the last.

The shape warnings 3, 5 and 6 share: **a green result is a claim about the
world, and the three ways to make one without evidence are to pass for the
wrong reason, to check a copy of the rule, and to not run at all.**

**7. A test pinned to a current state breaks when a later task legitimately
changes that state.** It has two halves — the setup and the assertion — and
the second was found the day this moved onto the page, so the warning names
both.

**The setup half: a test that demonstrates a fix by building the defective
case is coupled to that case remaining buildable.** Task 042c fixed `fanout`
so that it
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

**8. Two checks that see different things are not redundant, and dropping
either leaves a gap neither reports.** A scan over source and a check over a
running process look like two ways of asking one question. They are two
questions.

- **A source scan cannot see a transitive import.** It reads the lines a
  module wrote and nothing about what those lines drag in.
- **A runtime check cannot say which line did it.** It reads the loaded
  modules and has no idea which import, in which package, three hops away,
  is responsible.

The instance. The lab's guard refuses `oneground.models` to every served
module, and `oneground/intake/fields.py` declares intake's fields with
`models/base.py:Param`. The **static** scan passed: no module in the lab named
a measuring package, and the import sat one package away in `intake`. The
**runtime** check failed, because `oneground.models.__init__` registers all
three families, so reaching a dataclass had loaded every family, every index
type and numpy into a process whose whole rule is that it cannot measure.

Each check was right and neither was sufficient. The scan could not have seen
it; the runtime check said *ten measuring modules are loaded* and could not
say which line to change.

> The rule: **when a rule has a static half and a runtime half, keep both and
> say what each cannot see.** The temptation, once one of them is written
> well, is to treat the other as belt and braces and let it rot. The half you
> drop is the half that catches the next defect, because the defects that are
> easy to catch statically have already been caught statically.

> And the repair was **a leaf module, not an exemption.** `Param` moved to
> `oneground/param.py`, which imports only the standard library; `base.py`
> re-exports it and no existing importer changed. An exemption would have
> silenced the check and left the server loading three families. **A guard
> that is hard to satisfy is sometimes describing a dependency that should
> not exist** — see §5.

**9. A wait condition satisfied before the code under test has run.** Three
instances in one slice, which is why it is here rather than in a task report.
A browser check does something, waits for a condition, then reads the page.
Every one of these waited for something **the static HTML already provided**:

| waited for | why it was already true |
|---|---|
| `.tabs a` | `index.html` ships three tabs of its own |
| the eyebrow having changed | `boot()` sets it *before* it awaits `route()` |
| `.field` | `index.html` ships static lab panels that match |

Each probe then read a page that had not finished loading and reported on it
with complete confidence. The first said *no link to #/new* — and would have
said that on a correct build. The second screenshotted an empty run list under
a header saying "9 run(s)". The third reported the lab's own controls as the
form's.

> The rule: **a wait condition must name something the code under test
> produces.** Not something the page has, not something that appears at about
> the right time — something that exists *because* the thing you are testing
> ran. `window.onegroundCompose` and `#compose-file` are created by
> `compose.js` and by nothing else, and either is a condition that can fail.

The general form, and it is the reason this sits beside warnings 3 and 7:
**the probe's answer was independent of its subject.** It would have reported
success on a correct build and failure on a broken one for reasons unrelated
to either. That is the same defect as warning 1's — a check that could not
reach its own motivating case and reported the gap as the subject's — and the
same as the patch in warning 7 that landed on a name nothing looks at,
arriving here in a third tool. Whenever a check's result does not depend on
the thing it is about, it is not weak evidence. **It is not evidence.**

> The cheapest test of a wait condition: **would it still be true if the code
> under test were deleted?** All three of these would.

**The assertion half: a test that asserts a whole collection breaks when any
member of it legitimately changes.**
`test_two_copies_of_the_same_run_are_still_only_couldnt_check` asserted
`set(unknown) == {"code", "machine"}`. Task 043 made the measuring machine
answerable, `machine` left the set, and the test failed — although the
property it is named for, that two copies of one run are still
couldn't-check, held exactly as it had before, with the verdict and the
`differing` list unchanged.

Nothing was standing on a boundary here; the setup was and remained legal.
**The coupling was in the assertion: it pinned the whole of a set when it
cared about two of its members**, so a legitimate change to a third broke it
for a non-reason.

**And a third shape, which is the setup half again and easy to miss because
nothing about it looks like a setup.** Task 046 moved `producing_version` to a
leaf module and left a re-export behind, so every caller was unaffected. Four
tests in `test_provenance.py` went red: they patch `_build_stamp` and
`_run_git` on the module they import from, and the function reads those names
from the module that **defines** it. The patch now landed on a name nothing
looks at.

They were right to go red — the assertions still held and the setup had
stopped reaching the code under test — and the repair was the patch target,
not the assertion. But the interesting half is what the failure would have
looked like if the move had gone the other way, and the function had started
reading the patched name by accident:

> **A patch applied to a name nothing looks at is a test that passes for a
> reason unrelated to its subject.** It is warning 3 wearing a setup's
> clothes: the test runs, the assertion is true, and the thing it believes it
> is controlling is untouched. The same shape as a wait condition that is
> already satisfied before the code under test has run — in both cases the
> check's answer is **independent of its subject**, which is the property that
> makes a green result worthless rather than merely weak.
>
> The tell: **after a move or a rename, run the tests that patch the thing
> that moved before you trust any of them.** A re-export keeps callers
> working and silently breaks patchers, and those are the same import line.

> The rule: **assert the facts the test is about, not the collection they
> happen to sit in**, and say in the docstring which facts and why. A set
> equality over a result is a tally, and a tally is a current state — §1 of
> this page, arriving inside an assertion. The repair here was two membership
> assertions, `code` in and `machine` out, each carrying the reason it is
> there, so that the next person to move an ingredient can tell in one reading
> whether they have broken a property or a count.

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

---

## 4. A key whose meaning differs by file

**The rule.** Before adding a field to a receipt, look at what that name
already means in every other artifact that carries it — not at whether the
name is free here.

The check people actually perform is *does this key already exist in this
file?*, and it is the wrong question. It passes **exactly when the defect is
about to be written**: the name being free here is what makes it available,
and the name being taken elsewhere is what makes it wrong.

The failure is invisible at the point of writing and invisible afterwards. The
field is present, well-formed and plausible. Nothing is missing, so no absence
check fires; the value has the right type and shape, so no schema check fires.
It surfaces only when a reader that knows the *other* meaning reaches the new
block, and then it surfaces as **a wrong value rather than as an error** —
which is the worst way for anything here to surface, because a wrong value is
evidence.

**The instance.** `report.json` carries two environment blocks, deliberately:

```
environment       the machine that MEASURED
run_environment   the machine that WROTE THE REPORT
```

For a pod run those are different machines, and telling them apart is the
whole point of having both.

Task 043 needed `characterize` to record where a run happened, believed the
block was missing from `build_info.json`, and added `run_environment` to it.
Two things were true and neither was visible from the edit:

- `build_info.json` **already carried `environment`**, holding the same stamp,
  **three lines below** where the new key went.
- `build_info.json` has no separate reporting machine, so `run_environment`
  there would mean *the measuring machine* — the opposite of what the same key
  means in `report.json`.

A second block reading as a different fact, in the function whose defect is
that names mean different things in different files, in the task that existed
to eliminate that defect.

**What caught it, and what did not.** Not review. Not the suite — the writer
change was correct in isolation and every test passed. Not the exhaustive
reader test written in the same task, because that test finds **absences** and
this was a **wrong value**: on its first run it found a third absence nobody
was investigating, and it was structurally unable to find this one. What caught
it was an instruction to look at the *blocks* rather than the fields, which
meant reading `report.json`'s two environment blocks side by side — which is
when a duplicate three lines away became visible.

> **The tell: a fix to the writer changes nothing.** If you have just made a
> producer record something and the consumer still reports it missing or
> wrong, the problem is not in the producer. Either the reader consults the
> wrong source, or you have written the right value under a name that means
> something else.

**The remedy is the one §2 warning 2 reaches for, one level down.** Warning 2
says a second implementation of a rule is a second place for it to be wrong.
This is a second *name* for a fact, which is worse, because an implementation
can be diffed and a meaning cannot. `oneground/comparability.py` now declares
`FACT_CARRIERS` — fact name to an ordered list of (file, key path), the order
being the precedence rule — and the reader iterates the declaration rather
than naming files itself. **A declaration is where a collision becomes visible
at the moment the name is chosen**, which is the only moment it is cheap.

**The strongest instance, and the file is a table rather than a document.**
Task 046 built a declaration of intake's fields, reusing `Param` from the
family tables. `Param.default is NO_DEFAULT` means *the family has no default
for this key, so a configuration must name it*. The form read it as **the user
must supply this**. Same words, different fact — most intake fields have no
default and are entirely optional.

So every optional field was labelled **required**, and `ids_path` carried the
badge directly above its own explanation, which begins *"Optional."* The
document contradicted itself in adjacent lines and nothing fired, because —
exactly as this section says — the value was **present, well-formed and
plausible**. It took a browser and a person reading the page to see it.

The repair was a separate declaration, `fields.REQUIRED`, rather than a second
meaning for `default`. **A key that nearly fits is the dangerous kind**: the
name is right, the type is right, the values line up in most rows, and the one
row where the two meanings diverge is the row nobody checks.

### A claim with four homes is corrected three times and still wrong

The same defect in a sentence rather than a key, and it is the half worth
taking away, because the first three repairs each looked like the end of it.

`oneground ui` claimed *"read-only · nothing runs from this page"* in **four
places**: the page's eyebrow, the CLI's startup line, the `writes` field of
`/api/check`, and a module docstring. Task 046 gave the page a write half, and
`read-only` became false in all four at the same instant.

It was then corrected three times, days apart, each time by someone looking at
exactly one copy — and **each correction was itself correct and complete for
the copy in front of it**. The claim was still wrong after all three, and the
fourth was found only because a developer read a raw `/api/check` response
while diagnosing something else.

> The rule: **the defect is not that a claim went stale, it is that the claim
> had four homes.** Staleness is §1 and is caught by looking; this is not
> caught by looking, because every place you look has just been fixed.
>
> And so **the repair is one derivation, not four edits.** `/api/check` now
> answers `writes` and `runs` *from what the session is* — a `lab` session
> writes nothing and says so, a `ui` session says what it writes. A fourth
> edit would have restored the count to four correct copies, and the fifth
> change would have broken it again. Deriving it leaves one place that can be
> wrong, and it is the place a reader asks.

The tell is the same as this section's: **before you fix the copy in front of
you, search for the others.** Grep the distinctive phrase, not the file.

> *A second footnote, one layer inside the fix for this very section.* The
> form's selects rendered blank, so each gained an unselected option naming
> itself. An `<option>` with no explicit `value` **answers to its own label**
> — so the new option's value became the string "— not set —",
> `select.value = ''` matched nothing, `selectedIndex` went to `-1`, and the
> control rendered blank again. One name, two meanings depending on whether
> an attribute is present: this section's defect in HTML rather than in a
> receipt, committed inside the repair for it. The value is set explicitly
> now.

> *A footnote, because ten minutes is still an instance.* While fixing the
> above, `compose.js` grew a second copy of its condition evaluator —
> `shown()` and `conditionHolds()` asking one question two ways — in a file
> whose own header cites §2 warning 2. It lived about ten minutes. Duplication
> does not arrive announced; it arrives as the shortest way to finish the
> thing you are already doing.

**What it cost.** The fifth instance of this defect, written by the person
eliminating the first four, in the task doing the eliminating, after three had
already been diagnosed. One reverted commit, and it would have shipped had the
ruling arrived an hour later. Full account:
`tasks/043-provenance-foundation.report.md`, leading section. The audit that
found the first four, and argued for the declaration before it existed, is
`tasks/finding-comparability-carriers.md`.

---

## 5. What a guard is telling you when it refuses you

Every guard in this project eventually refuses something reasonable. The
question at that moment is not *how do I get past this* but *what is it
saying*, and there are two answers, which want opposite repairs. Getting the
pair the wrong way round is how a guard turns into a formality.

> **A guard firing on a name is a false positive, to be named and exempted.**
> **A guard firing on a thing is usually telling you where the thing belongs.**

The two are worth holding together, because either alone reads as a
preference. Both happened in one afternoon of task 046, and the contrast is
what makes it a rule rather than a judgement call.

**A name, exempted.** The lab's guard refuses a served module that mentions
`vectors` or `queries`, because a view that names a vector column is usually
about to compute with one. `oneground/intake/__init__.py` mentions both: they
are the names of two keys in a requirements file, `corpus.sample.vectors.path`
and `corpus.sample.queries.path`, and they hold **file paths**. Intake never
opens either — it validates the document and hands the paths on.

The rule is a name rule and here the name is not the thing. So it took an
entry in `TRANSPORT_ALLOWLIST`, which is per file and per rule and carries its
reason in the table — the same shape as the two entries already there, one of
which exists because `contract.py` has to name `partition.centroids` in order
to refuse it to every view.

**A thing, relocated.** The same guard refuses `oneground.models` to every
served module. The new intake field table needed `Param`, which lives in
`models/base.py`. An exemption was available and would have taken one line.

Taking it would have put a field's **explanation** in one package and the
**refusal** it must never diverge from in another — and the whole reason that
table exists is that those two strings cannot be allowed to drift. The guard
was not being obstructive about a name; it was objecting to a dependency, and
the dependency was the design problem. `Param` moved to a leaf module, the
table went to `intake` beside the refusals, and the served package stopped
loading a simulator.

**And a second relocation, in the same slice, which is what turns one
decision into a rule.** The server had to be able to say which build it was
serving. `producing_version` already existed in `oneground.receipts`, which
imports torch; `checkout_root` already existed in `oneground.environment`,
which imports faiss and sklearn. Both are refused to every served module.

Two exemptions were available and either would have taken one line. The
alternative to taking them was a second implementation of *what commit is
this*, which is the outcome §2 warning 2 exists to prevent — so on the face of
it the exemption was the lesser evil.

It was not, and the pair with `Param` is why. Both times the guard was not
objecting to a **name** the module happened to use; it was objecting to a
**dependency the module would acquire**, and in both cases that dependency was
real: the served package would have loaded a simulator, or torch, to reach a
dataclass and a git call. The third option was the right one both times, and
it is the one an exemption hides: **move the thing being reached for**.
`oneground/param.py` and `oneground/provenance.py` are leaves, both old homes
re-export, every importer is unaffected, and there is still exactly one of
each.

> So the rule, now that it has happened twice: **a guard refusing a served
> module an import is usually a statement about where the thing belongs, not
> a statement about the guard.** The question it is really asking is *why does
> this small thing live behind that large thing?* — and when the answer is
> "no reason, it was declared next to its first caller", the repair is a leaf
> module and not a line in an allowlist.
>
> Two data points are not a law, and the exemption above is the case where
> this does not apply: a name rule firing on a name. But note which way the
> two cases split. **The exemptions that were right were about names. The
> exemptions that were wrong were about imports.**

**A third, at a third level, which is where this stops being a
rationalisation of two cases.** Task 046 needed a job record. The lab permits
exactly one served module to open a file for writing, so a job list the
server could write would have been a second write path inside the served
package — and again an exemption was one line away.

The three are worth listing together because they are the same argument at
three sizes:

| what was refused | the exemption on offer | where it actually belonged |
|---|---|---|
| a **dataclass** (`Param`) from `oneground.models` | allowlist the import | `oneground/param.py`, a leaf |
| a **function** (`producing_version`) from `oneground.receipts` | allowlist the import | `oneground/provenance.py`, a leaf |
| a **module** (the job record) from the served package | allow a second writer | outside it: the server reads jobs, the supervisor writes them |

A dataclass, a function, a whole module. Each time the guard was describing
the architecture rather than obstructing it, and each time the exemption
would have been the cheapest possible way to not hear it.

> The test, when you cannot tell which case you are in: **would the exemption
> still be right if the guard did not exist?** Intake would still name those
> two keys, so the exemption describes something true. The lab would still
> have no business importing a simulator, so the exemption would have
> described only my convenience.

**The cost of getting it backwards is asymmetric**, which is why the default
should be suspicion. A wrongly-refused exemption costs a few minutes of
rearranging. A wrongly-granted one costs the guard: it now has an entry saying
this rule does not apply here, nobody re-reads it, and the next module to want
the same exemption has a precedent. Every entry in an allowlist is a small
permanent hole, so each one earns its place by being *true about the world*
rather than *true about today's diff*.

---

## 6. A server that cannot say which build it serves

> **A server that cannot say which build it serves is a URL nobody should be
> handed.**

**The instance, and it is the most expensive thing on this page.** A `oneground
ui` session was started and handed to the developer to look at. It answered
200, listed nine runs, rendered cleanly — and served a page with no write
half, because the console script `oneground.exe` resolves the package by
**install location**, and on that machine the install pointed at a third
checkout that predated the work by weeks. The suite had passed against a
different directory minutes earlier.

Nothing was broken. Not the code, not the tests, not the server, not the
browser. **The build being served was simply not the build anyone had in
mind**, and no part of the system could notice, because no part of it had ever
been asked to say which build it was.

**What it cost is the part that matters.** Not the hour of diagnosis — a week
of browser observations whose subject nobody could now name. Every visual
finding made against that URL had to be treated as being about an unknown
build. The developer's response was the right one: *I would rather wait than
repeat an observation whose subject I cannot name.*

**Why the gate did not catch it.** The gate proved the worktree; the URL
proved nothing, and nothing connected the two. This is §2 warning 8 at the
level of a whole workflow: a test run and a running server are two checks that
see different things, and the assumption that they saw the same code was never
written down anywhere it could be checked.

> The rule: **anything you hand someone to look at states what it is, before
> it is looked at.** Three parts, and the first is the one that discriminates:
>
> - **the package directory**, because in this incident the version and the
>   commit were the same on both sides and only the path differed;
> - the commit and whether the tree was dirty, or a stated reason they cannot
>   be known;
> - a **refusal**, not a warning, when the build is ambiguous — here, when the
>   working directory holds a checkout of this project whose package is not
>   the one that was imported. A warning at startup is a line in a scrollback
>   nobody reads; the whole failure mode is that everything looked fine.

`oneground/provenance.py` is the mechanism: `identity()` is printed at startup
and answered on `/api/check`, and `conflicting_checkout()` refuses the bind.
The refusal is watched firing on a constructed clash rather than observed not
firing on a clean tree (§2 warning 3).

**One note on where it had to live.** `producing_version` already existed — in
`oneground.receipts`, which imports torch, behind a guard that refuses every
served module. The choice was a second implementation of *what commit is this*
or one more leaf module. It moved, and both old homes re-export it. That is
the second time in one slice that a guard's refusal pointed at a dependency
rather than a name, and the answer was the same both times: see §5.

---

## 7. Exemptions

Every check worth having eventually needs one. A rule with no exceptions is
usually a rule that has not met the world yet, and the exceptions are not the
problem — an exemption nobody can see is. Three rules, in the order they bite.

### 7.1 An exemption carries a reason, or it has nowhere to go

**The mechanism.** Declare exemptions as a **mapping from the thing exempted
to the reason it is exempt**, never as a list of names. Then an entry that
cannot be justified in a sentence has no shape to be written in, and the cost
of adding one is paid at the moment somebody wants it rather than at review.

A pinning test — one that asserts the exact contents — is worth having
alongside, but be clear about which is doing the work. **The reason is the
mechanism; the pinning test is only the alarm.** A list of bare names with a
pinning test can still grow: somebody edits both in one commit and nobody
reading the diff can tell whether the new entry was justified, because there
was never anywhere to say.

Two instances, and the second is the older one.
`oneground/replay.py:MAY_DIFFER` maps each field two runs of one command may
differ in to why it may — `oneground.dirty` because an editor saving a
docstring flips it while `oneground.commit` beside it does not move. And
`guard.TRANSPORT_ALLOWLIST` has carried a reason per entry since 041, per
file and per rule, which is why §5 could weigh its two cases against each
other at all: the reasons were there to read.

### 7.2 An exemption that is not reported has only moved the silence

**A test that names its exemptions and then does not report them has only
moved the silence somewhere quieter.** Declaring what you set aside, and then
discarding it at the point of comparison, buys the appearance of rigour and
none of it: the reader of the result still cannot see what was skipped on
*this* run, which is the thing they would have wanted to know.

So the implementation is that the comparison **returns what it set aside**.
`replay.compare()` answers with an `exempt` list beside `differing` — which
file, which field — so a person reading a green replay can see that three
fields were exempted and which three, rather than inferring from a
declaration somewhere else that they probably were.

This generalises past tests. A guard that permits something, a report that
drops a row, a verdict that sets a case aside: if the output does not say so,
the exemption is invisible at exactly the moment it matters, and the
declaration has become documentation rather than evidence.

### 7.3 An exemption applied to a container is a hole the size of the container

**The instance, and it is why this has its own rule.** Two runs of one command
differ in `run_at` and `elapsed_seconds`, and `MANIFEST.sha256` covers the
files holding them — so the manifest differs too, and the obvious exemption
is *skip the manifest*.

That would have been an exemption for two timestamps that stopped checking
**every file in the workdir**. The manifest is the thing that says what the
artifacts are; setting it aside sets aside the whole comparison, and the test
would have gone on passing while reporting nothing.

So the manifest is compared line by line, and only the lines for files whose
bytes may legitimately differ are set aside. Every other line still has to
match exactly.

> The rule: **exempt the entries, not the container.** When the thing you want
> to skip is an aggregate — a manifest, a digest, a summary count, a whole
> file — the exemption has to reach inside it and name the parts, or it
> silently covers everything the aggregate covers.
>
> **And the mutant is what proves the difference**, because the two versions
> are indistinguishable from a green run. A test corrupts one manifest entry
> for a non-exempt file and asserts it is caught. Without it, *skip the
> manifest* and *skip two lines of the manifest* look identical from the
> outside, which is warning 3: a passing check must be able to fail, and here
> the two designs differ only in whether it can.

### 7.4 A distinction that goes into a message is available to a human and to nobody else

**The rule**, and it sits above the two instances below because both are
cases of it.

When you know something a caller would need — which of two things happened,
what to do about it, which field is at fault — and you put it in the
*message*, you have given it to a person reading a screen and to nothing
else. Every programmatic caller downstream must either re-derive it, parse
your prose for it, or do without.

**The instance that names itself.** `embed.registry.ModelUnresolved`:

> *"Names what was tried and what the failure was, because the two common
> causes — a typo and no network — need different actions from the reader
> and the underlying exception distinguishes them badly."*

Read what that docstring knows. The information **existed a layer down**. It
was **known to be poor there** — *distinguishes them badly*. It was
**correctly re-expressed** for a reader, with both causes in order. And it
was then **lost for every caller**, because it went into prose rather than
into the type. A typo is a refusal; an unreachable hub is a failure; one
class, so one answer, wrong for one of them whichever way it is given.

**It is the same shape as the action sitting in `reason` rather than
`remedy`** — task 045's finding, where a couldn't-check verdict said *"To
decide X: this configuration was not the one verified"*, a sentence with a
remedy's grammar and an obstacle's content. There too the tool knew what
would settle it, and there too the knowledge went into a string a person
reads instead of a field a caller can branch on.

Naming the pair is what makes it a rule rather than two anecdotes:

> **If a caller would branch on it, it belongs in the type, the field or the
> verdict — not in the sentence.** Put it in the sentence *as well*, always;
> a person still has to read it. But a distinction that exists only there has
> been recorded rather than made available, and the difference is invisible
> until something downstream has to ask.

The tell: **you are writing "because" into a message.** *…because the two
causes need different actions.* If they need different actions, something
will have to choose between them, and prose is not a thing a chooser can
read.

**And the rule for doing the split, which is not *always distinguish*.** It
is: **distinguish where the information exists, and refuse to guess where it
does not.**

`ModelUnresolved` split into three outcomes, not two. Two sites knew which
they were — *listed twice* is decided from the request alone, and *loaded but
reports no dimension* means the name was right — and they took the refusal
and the failure. The third is the load attempt, where a typo and an
unreachable hub produce much the same exception, and **it kept the ambiguous
base.**

That third site is the rule honouring itself rather than an exception to it.
A split that forced every site onto one side would have moved the guess from
the classifier into the raise, where it is harder to see and no better
informed — and the base's own docstring already said the underlying exception
distinguishes them badly, so the guess would have been made *against* recorded
knowledge.

> **A type that cannot answer is the honest type to raise.** Keeping one
> ambiguous case is not the split failing; it is the split declining to
> invent the one thing it does not have. The classifier then excludes that
> type, which is a statement about the site, and the asymmetry decides what
> happens downstream.

### 7.4.1 A refusal is produced where it is raised, once

Not strictly an exemption, and here because it is the same failure seen from
the other side: a rule that exists, is written down, and is implemented in
the wrong place, so that everyone downstream reimplements it or does without.

**The instance.** `intake.RequirementsError` is the project's own refusal
type. Its module header states the two rules that shape all twenty-five of
its messages -- *name the field*, and *refuse rather than guess* -- and every
message obeys them. `cli.main` caught none of them, so the commonest refusal
in the product reached every command-line user as an unhandled Python
traceback with the carefully written sentence on the last line.

**It looked fine from the interface**, which is the part worth sitting with.
`lab/compose.py` catches `RequirementsError` from `intake.load()` directly
and never goes through the CLI, so the form showed clean refusals throughout.
The slice's acceptance -- *a refused job shows the CLI's refusal verbatim* --
would have been met by a path that was shielded by accident rather than by
one that was fixed. **A slice whose acceptance is satisfied by a shielded
path is passing for the wrong reason** (§2, warning 3, at the level of a
whole deliverable).

> The rule: **produce a refusal where it is raised, once, and let every
> caller read it.** If two callers each have to recognise it, one of them
> will do it differently and the other will do it later.

**And the direction refused, recorded because it was the tempting one.** The
supervisor could have parsed the traceback -- match the exception name off
the last line, classify from that. It would have worked. It would also have
been a second implementation of the CLI's own error formatting in the one
place the design says not to have one (§2 warning 2), and it would have left
the command line's own users exactly where they were. **A fix that only
repairs the new caller is not a fix, it is a workaround with a test.**

The tell: *the thing that needs to recognise this is not the thing that
raised it, and there is already one that does.*

### 7.5 To prove a classifier reads an input, vary only that input

**The form.** A classifier that takes several inputs and returns a verdict
can pass every test it has while ignoring one of them entirely. The only
thing that proves it reads input *N* is a pair of cases **identical in
everything but N**, with different verdicts.

Not a test per input. A *pair* per input, with everything else held.

**The instance.** `jobs.classify(stage, exit_code, workdir)` decides whether
exit 1 means *the run happened and dropped some configurations* or *the run
crashed*, and the workdir is the only thing that separates them:
`simulate.json` exists in the first case and not in the second. That is the
whole of *the truth is the workdir* made operational.

Ten tests covered it — five stages with the receipt written, five without —
and **every one of them would have passed against a classifier that never
looked at the workdir at all**, because each also varied the stage. So the
row got an eleventh: same stage, same exit code, and the receipt appearing
between the two calls.

```python
before, _ = jobs.classify("simulate", 1, d)     # failed
open(os.path.join(d, "simulate.json"), "w").write("{}")
after,  _ = jobs.classify("simulate", 1, d)     # done
assert (before, after) == ("failed", "done")
```

> The rule: **hold every input fixed but one.** A suite that varies two
> things at once measures the pair, and a classifier can satisfy it by
> reading either. The mutant is what turns *the truth is the workdir* from a
> slogan into a fact about this function.

This is warning 3 with the subject narrowed. *A passing check must be able to
fail* asks whether the check can go red at all; this asks whether it can go
red **for the reason it claims**. A classifier is exactly where those two come
apart, because its verdict is right for many wrong reasons.

### What to do when an exemption is demanded

This is the sentence a future author should meet, because the pressure is
real and arrives at a bad moment — a replay differs, the difference looks
legitimate, and adding a name to a list is thirty seconds' work.

> **The question is not whether the field differs. It is whether a receipt
> that cannot reproduce it is recording the right thing.**
>
> A receipt that cannot be reproduced is telling you something: that it
> records a fact it should not, or fails to record one it should. **That is a
> finding about the receipt, not a reason to widen the list.** Write it up,
> and leave the list where it is until it has been.

The list is small because it has been defended, not because nothing has ever
wanted in.
