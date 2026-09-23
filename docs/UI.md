# The interface — `oneground ui [<runs-dir>]`

*The read half: many runs, each report whole with its evidence, and the lab
reached from a run. Nothing runs from this page — no job, no written file, no
session. `docs/INTERFACE.md` is the position this implements; this document is
what was built and the rules it is held to.*

`oneground lab <workdir>` is unchanged and still opens one run's ground and
trace. `oneground ui` is the same server, the same token and the same guard,
pointed at a directory of workdirs rather than at one run.

---

## The rule this interface is organised around

> **Layout drifts; structure does not.**

Every guarantee this interface makes could have been made in the stylesheet or
in the drawing, and each one is made in the drawing. A stylesheet is edited by
whoever is making the page look better on a Tuesday; a drawing is a contract
with a test. When a rule can live in either, it lives in the structure, and
the renderer is left with nothing to get wrong by omission.

This is not a style preference. It is the same argument as the interface being
a front-end over the CLI rather than a second implementation, applied one
layer down: a property enforced in two places will eventually be enforced in
one.

Two rules below are instances of it, and a contributor who understands the
rule will not need the list to extend it.

### Instance: the three outcomes arrive as three entries

A run's outcomes reach the page as a list of `{outcome, n}` — **always all
three, always in one order, always present, with nothing in the structure
marking one as lesser.** No `primary` flag, no optional key, no omission at
zero.

The renderer loops over what it is handed. It has no branch that skips an
outcome, so it cannot drop `0 couldn't check` by accident; to give
couldn't-check a muted treatment, somebody would have to add a rule that
singles it out, which is a decision rather than a slip. In `ui.css`, `.count`
sets font size, weight, opacity and padding once for all three, and the three
`.outcome-*` rules may set a hue and nothing else.

`1 meets · 6 fails` is a different statement from `1 meets · 6 fails · 0
couldn't check`, and the second is the true one. The first invites a reader to
forget the third exists, which is the failure this whole product is built to
refuse.

### Instance: two runs are joined only when the verdict permits it

A comparison arrives as **one mark holding both runs' numbers only when the
comparability verdict is `comparable`.** Otherwise each run arrives as its own
mark and there is no row in the data that holds both.

The page cannot line up two numbers the verdict will not vouch for, because it
is never handed a row to line up. Breaking the rule would mean joining two
marks on purpose. A divider drawn in CSS would have been one refactor away
from being lost.

### Instance: a dash is not a zero, and a note is not a verdict

Two renderings of the same move — **the page does not supply what the receipt
does not record.**

**A dash where nothing was counted.** The outcome column is three boxes in
three fixed positions for every run. Where a run recorded no counts, each box
holds an em-dash and the reason goes underneath. A zero is reserved for
*checked, and did not hold*; printing three zeros for a run that never
reported would state fifteen measurements nobody made. The dash keeps the
column scannable — one shape, four cases — without borrowing a number to do
it.

**A note where no verdict was asserted.** Every claim on the report page
carries a mark: `meets`, `fails`, `couldn't check`, or `note`. The mark is
read from the claim's own recorded kind, and `note` is what a `scope`,
`qps_max` or engine-comparison claim gets, because those state no verdict.
Colouring them as one would invent a verdict the report never issued.

Both are the product's own three-outcome distinction applied to a cell, and
both are enforced where the data is built rather than where it is drawn.

### Instance: two tallies that count different things stay apart

A run's panel counts **constraints**: `0 meets · 6 fails · 2 couldn't check`.
The report page's line counts **claims**: `2 meets, 12 fails, 2 couldn't
check, 21 stating no verdict`. They differ because one constraint can be
claimed once per option, and both are labelled with the noun they count.

Adding them, reconciling them, or showing one where the other belongs would
produce a number nobody measured — which is the failure mode this interface
exists to refuse, arriving as a helpful summary.

---

## Three more rules, beneath that one

**A view may not supply what the receipt does not record, even when a layout
wants it.** The landing page for a run is specified to lead with the finding
*and the number that decided it*. When a report recommends something, its
claim cites the deciding row and the page shows it. When it recommends
nothing, the claim's source is `(rule)` and **nothing in the report records
which option came closest** — so the page says the conclusion rests on a rule
and shows the counts instead. Choosing a row would be the page ranking
options, which is a measurement, and views draw rather than measure. A layout
that wants a number the receipts do not carry is a layout that has to change.

**A partial summary is refused, not zero-filled.** A report recording two of
the three counts is one the page will not summarise: it shows a gap with its
reason. A missing count rendered as `0` is a measurement nobody made. This is
the couldn't-check rule applied to a table, and every later summary inherits
it.

**A gap left unexplained because its cause seemed obvious is how a
couldn't-check becomes a blank space.** Every absence on these pages carries a
sentence. While this slice was built, a Tier-2 run's missing deciding row was
briefly left blank because the reason felt self-evident — it is not
self-evident to a reader, and it now says *a Tier-2 run measured nothing on
this corpus, so there is no row for a conclusion to rest on, which is the
conclusion.*

---

## The command

    oneground ui                      # ./runs
    oneground ui path/to/runs         # a directory of run directories
    oneground ui --demo               # the published arxiv-150k fixture
    oneground ui --port 8741          # default: an ephemeral port

A directory is treated as a runs directory; each subdirectory holding at least
one receipt is a run. `oneground lab <workdir>` is unchanged and still exists
for one run's ground and trace.

One page is served for both commands. `boot.js` asks `/api/check` which mode
the server is in and then loads `lab.js` (one run) or `ui.js` (a directory),
rather than letting one of them fail and falling back — an absent thing is a
fact to read, not an error to recover from.

---

## The pages

### The run list

Every workdir under the directory: name, corpus size as recorded, which stages
ran, the three outcome counts, the version that produced it, and its digests.

- **Each run's receipts are verified against its own `MANIFEST.sha256` before
  it is listed.** A run whose digests fail is **listed**, with the failing file
  named, and never shown as sound. A run the reader cannot trust is the run
  they most need to see.
- **A missing manifest is couldn't-check, not a failure.** Absent is not the
  same as wrong, and the reason is on the row.
- **A run with no report shows *has not reported*, not three zeros.** Three
  zeros would say every constraint was checked and none held.
- **A declared corpus size stays a sentence.** A Tier-2 run records `n_base`
  as `couldnt_check: declared, not measured`; casting it to a number would
  turn "not measured" into a measurement.

### A run opens on its finding

The landing page for a run leads with what the report concluded. **The page
never writes that sentence**: it is the report's own `recommendation` claim
verbatim, or for a Tier-2 report its own `recommendation_reason` verbatim.

A run that has not reported leads with its furthest stage and the next
command. The command is named rather than invented — it is the stage after the
last one that ran, and there is only one.

### The report, with its evidence drawer

Every claim in `report.json`, and for each one what it cites: the file and
field the figure was read from, the value at that field, and for a
couldn't-check what would settle it.

**Every claim gets an entry, and every entry says what kind of thing it points
at.** Eight kinds; only two are navigable:

| kind | what it is | opens onto a receipt |
|---|---|---|
| `field` | a receipt field, resolved | yes |
| `within` | the source names a block; the figure is one of its members | yes |
| `rule` | `(rule)` — follows from a rule, not from a row | no |
| `requirements` | the requirements file, an input rather than a receipt | no |
| `every_option` | a wildcard: about every option, not one field of one | no |
| `not_run` | the stage that would have produced it was not run | no |
| `cost_model` | declared prices rather than a measurement | no |
| `unresolved` | the source names a file or field that is not there | no |

A reader who selects `(rule)` and gets an inert link learns that some
citations are simply broken. One who is told *this follows from a rule, not
from a row* learns what this project means by a citation. The non-field kinds
are rendered as their kind with their sentence, and none of them is an anchor.

**The drawer compares.** It carries the value the claim cites and the value at
the field the claim names, and shows both. Where they disagree it says so.
That is not decoration: building this drawer is what found two citations in
this repository naming fields that held different values, and a published
fixture carrying them.

### Two runs, side by side

Only under the comparability verdict `docs/LIBRARY.md` §2.2 defines, which
task 041 implemented at `oneground/comparability.py` because it reached it
first. It has three values, and the third is not a hedge:

- any ingredient that **differs** → `not_comparable`; knowing they differ
  beats not knowing;
- otherwise any required ingredient **unknown** → `couldnt_check`; a missing
  version is never read as a match;
- only when every required ingredient is known and equal → `comparable`.

**Today every pair answers `couldnt_check`, on the code.** No artifact records
the `oneground` version that measured it, and `environment_id` is
`local:<os>-<arch>` — a class, not an identity. Two byte-identical copies of
one run agree on libraries, settings digest, sample digest, platform and
interpreter and are still `couldnt_check`. Until a run records the version
that produced it, no two runs in this product can be compared. The page says
so rather than showing them side by side anyway.

### `--demo`

Opens the published `arxiv-150k` fixture's own run: real receipts, real
digests verifying against the fixture's `MANIFEST.sha256`, the real report with
its real couldn't-checks. Nothing is fabricated for the demonstration.

**Nothing is downloaded.** The fixture's report bundle is in the repository,
so nothing the read half needs is absent, and the page says that rather than
implying a fetch happened. A fetch that never fires is a feature that lies
about what it does.

**How far the demo reaches, and why.** The published fixture ships *receipts*
and not *simulator state*, so the demo opens the run list, the run's finding,
and the report with its evidence drawer — and cannot open the ground or the
trace, because there is no state to draw them from. It also cannot open the
side-by-side, for a different reason: that needs two runs and the demo is one.

Meet this as a fact about what a fixture is rather than as a broken link. A
fixture publishes what a reader must be able to check — the measured values,
the digests, the report judged from them. Simulator state is an intermediate
of one run on one machine, several hundred megabytes of it, and publishing it
would make the fixture something else. The demo says which pages it cannot
reach and why, on the page.

The page says whose corpus it is **in the view**, above the table, so a
screenshot carries it, and points at what a `requirements.yaml` needs for your
own vectors.

---

## What this slice does not do

Stated plainly, because the position paper's slice 2 adds all of it:

- **Nothing runs from this page.** No job, no stage, no command.
- **No file is written by it.** There is no form, and there is no write path.
- **No session is created by it.** The money boundary does not move: a pod is
  created by a typed `y` at a terminal, and the page does not offer one. The
  session card is slice 2's, because the lab's import guard lists
  `oneground.pod` as measuring and `pod plan` writes no receipt to render.
- **No measurement is computed.** A number on screen came from a file the CLI
  wrote, or it is not on screen.

### Settled before slice 2: what holds the write path

Slice 2 adds a form that writes `requirements.yaml`. **A form writing a file
is the first thing in this interface that is not a drawing**, and the
rendering contract has nothing to say about bytes leaving the page: its three
clauses describe what a view may be handed, what it may read and what it must
return, and none of them describes a write. The read half is held by a guard
rather than by convention, and the write half must be too. This is the rule it
lands on, ruled before the brief so the brief cannot fudge it.

> **The bytes must round-trip to the *same document* the form validated —
> `parse(write(D)) == D` — checked on every write, not in tests.**

**The naive form of this does not work, and the measurement is why.** "The
file must load through the CLI's parser without a refusal" is the obvious
candidate and it is necessary and nowhere near sufficient: the string
`constraints` does not appear in `oneground/intake/load()` at all. A file with
one constraint dropped, with every constraint dropped, and with the
`constraints` block removed entirely all load without a word. A form that
silently lost a constraint would produce a file that parses cleanly.

Identity is the checkable middle between *parses* and *says what the user
meant*, and it draws the line where a guard can actually reach:

- **The guard checks that nothing is lost between the form's document and the
  file.** `D` in, bytes out, `load()` back, compare. Mechanical, so it runs on
  every write — write to a temp path, read it back, compare, then move.
- **Coverage and comment fidelity are acceptance, not the guard.** Whether the
  form *offers* every field a requirements file can carry, and whether each
  field's explanation in the written file is the same string the form showed,
  are tested against a worked example. **No guard has access to intent**, so
  nothing here can check that the user meant what they typed — only that what
  they typed reached the file intact.

**Byte-identity is not a stronger version of this rule. It is a different and
incompatible one.** `write(D) == bytes` would forbid the comments the
front-door ruling requires the form to write: the identity is over the
*parsed document* precisely because comments are not data, which is the same
ruling's own statement that they are never read back as such. A reader
reaching to strengthen the rule would be trading one ruling for another
without noticing, so the incompatibility is recorded here beside the rule and
not beneath it.

**The check is load-bearing, not a sanity check.** `D` is built from form
state rather than by editing a loaded document — because upload-and-edit and
fill-from-empty must produce the same file for the same inputs, and that is
only true if both paths construct through one code path. So `D` is a **second
construction of the schema**, and this identity is the only thing standing
between that construction and drift from the one `load()` performs. A reader
who meets it as a sanity check will run it in tests only, which is exactly
where it stops being a guard.

**And it does a second job, which is the strongest argument for the shape.**
It is the executable form of *the form's refusal is the CLI's refusal
executed, not re-expressed*. If `D` round-trips through `load()`, then `D` is
in the set `load()` accepts — so **the form cannot construct a document the
CLI would refuse without the guard saying so at write time.** The ruling stops
being a convention the form is trusted to honour and becomes a property the
guard checks. A validator in two places will disagree the first time one is
fixed, and the place a user meets a refusal is the worst place to learn that.

Alongside it, a source scan: exactly one module may open a file for writing,
and everything else in the package is refused. `test_the_server_has_no_write
_path` is the read half's precedent, inverted.

### A candidate for slice 2: the crispness distribution

Task 044 made `boundary_crispness` a **named reading of a distribution**
rather than a bare count, and `characterize` now writes a `crispness_reading`
block — value, threshold, percentile, `n_above`, `resolvable`, and a 201-point
quantile grid — into a user's own workdir's `characterization.json`.

**The characterize page does not draw it, and that is not breakage.** The page
declares its fields and draws `boundary_crispness`, which is correct: the
stored reading equals it to machine precision. Nothing on screen is wrong;
there is a measure available that the page does not yet know about.

Two reasons this is design work rather than a column, and both are worth
settling before anyone starts:

- **The field is present in a user's run and absent in a published fixture's.**
  Fixtures keep deriving the distribution on demand, deliberately, so a view
  declaring `crispness_reading` must ask `has()` and gap its absence with a
  reason. That is precisely the contract's absent-field case, and
  `oneground ui --demo` hits it on the first page it opens, because the demo
  *is* a published fixture.
- **A page showing the distribution and the count must say which is a reading
  of which.** They are one measurement, not two. Drawn side by side without
  that relationship stated, a reader sees two numbers about crispness and has
  to guess whether they agree — which is the shape of the defect the evidence
  drawer exists to make impossible elsewhere.

---

## The security model, unchanged

Everything in `docs/LAB.md` §Security holds here without amendment: loopback by
default, `--i-know` with a printed warning for anything else, GET only, no
request line logged, no path from a request reaching the filesystem, no CORS,
a strict Content-Security-Policy, an expected `Host` only, and a random token
on every request compared in constant time.

Two things this slice adds to it:

- **A run is selected by name against the index, never by joining a path.**
  `?run=../../etc` is answered with *no run named '../../etc' under
  &lt;directory&gt;*, because the name is looked up in the list of runs the
  session was pointed at. A parameter cannot reach a directory this session
  never indexed.
- **The guard covers every module, and the server refuses to start if one is
  unclassified.** Every file in `oneground/lab/` is a view under the rendering
  contract, transport under the transport rules, or contract machinery — the
  third kind was always there (`contract.py`, `guard.py`) and is now named.
  `guard.unclassified_modules()` must be empty, so a module cannot arrive in
  the package without someone deciding which rules hold it.

---

## The rendering contract, extended

Task 021 gave the lab one rule — *a view takes state and returns a drawing* —
over simulator state. This slice extends it to the receipts:

> **A view reads the declared fields of one receipt and returns a drawing.**

- **One receipt per view.** "Drawn from `simulate.json`" is a claim a reader
  can check; "drawn from four files" is not. A page wanting two receipts is
  two views the server composes.
- **Declared fields are paths in the same grammar `report.json` cites with.**
  A view declares `rows[].recall_at_10`; a claim cites
  `simulate.json:rows[LABEL].recall_at_10`. One notation for provenance and
  citation, so the drawer never translates between two — and a translation is
  a place two things can disagree.
- **A declared path that is never read is refused.** A view's `reads` is the
  drawing's stated provenance, so declaring a field and not reading it
  overstates what the drawing was built from.
- **An absent field raises rather than rendering `None`.** A receipt written
  before a field existed simply lacks it, and rendering that as a value would
  state a measurement nobody made.

Three documents a view may draw are not files on disk — the run index, a
report's resolved citations, and a comparison. Each is built by one named
function, and the condition of being on that list is that **every value in it
is copied from a named receipt without being recomputed, and carries where it
came from.**

---

## Stopping

Ctrl-C stops the server, and it says so: `oneground ui: stopped. Nothing was
written.`
