# Task 044h — five copies of one transform, and where people look

**Written up from the developer's ruling on the 044g report.** Branch
`task-044h` from `main`.

**This is not three conversions.** Converting the three remaining copies is
the easy half and probably an afternoon. The task exists for the question
underneath, and a report that lands three conversions without answering it has
done the cheap part.

## The question

> **Five private implementations of one rule is not a series of oversights.
> It is a statement about where people look, and at least one of them was
> written deliberately.**

Counted in 044g, with dates:

| # | where | task | what it does |
|---|---|---|---|
| 1 | `proposals/propose.py:_named_file` | 014 | basename + digest; docstring says "not its path… a card is published" |
| 2 | `calibrate/history.py:_portable_source` | 018 | relpath inside the repo, **unchanged outside** |
| 3 | `models/projection.py:110` | — | `os.path.basename(path)` beside its digest |
| 4 | `corpora/export_teaser_data.py:public_price_table` | 041 | relpath inside, basename outside |
| 5 | `receipts.public_path` | 043 | the canonical one |

**Three predate the canonical one.** For most of this project's life there was
no shared function to find, and four people independently solved the same
problem in four places — which is not a discoverability failure, it is the
normal way a shared abstraction gets discovered. 043 then wrote the fifth,
declared it canonical, converted three call sites and **retired none of the
other four.**

**And copy 2 contradicts copy 5 on purpose.** `_portable_source` leaves a path
outside the repository *unchanged*, and argues for it: *"a path outside the
tree is a genuine fact about where the artifact lived and shortening it would
say something false."* `public_path` reduces it to a basename. Those are two
different answers to a real question, and the 018 author gave a reason.

So this is not four mistakes and a fix. It is **four independent solutions,
one of them a considered disagreement, and a fifth that took the name without
settling the argument.**

## Do

### 1. Settle the disagreement before converting anything

`_portable_source`'s position — an outside path is a fact worth keeping — is
not obviously wrong, and 043 never addressed it. Decide, in writing, which is
right:

- **`public_path`'s answer**: a receipt never names a filesystem, so an
  outside path becomes a basename and the digest identifies it.
- **`_portable_source`'s answer**: an outside path is genuine information
  about where an artifact lived, and dropping it says something false.

Weigh it against what 044g measured: a path outside the checkout is precisely
the case that does not resolve on another machine (7 of 32, all the pod ones),
so "where it lived" is information that is true and unusable. **If
`public_path` wins, say so and say what is lost.** If `_portable_source` wins,
`public_path` changes and 044g's conversions change with it.

**Do not convert copy 2 before this is settled.** Converting it silently would
be answering an argument by deleting one side.

### 2. Then the conversions, each with its consumer named

`_named_file`, `_portable_source`, `projection.py:110`. Each has a consumer
and a contract; 044f and 044g both found that a field which looks descriptive
turns out to be resolvable. **Check each consumer before changing each
writer**, and report the blast radius per copy rather than in aggregate.

### 3. The discoverability question, which is the point

`receipts.public_path` is in the right place — beside `write_json_stable`, in
the package named for what it serves. 044g's finding is that this does not
help, because three copies were written before it existed and the next one
will be written by someone not looking for it.

044g's answer was **the refusal's error message**: discoverability delivered
by a failing write rather than by a docstring. Test that claim rather than
repeating it:

- does the refusal actually fire for someone adding a **new** writer, or only
  for the paths 044g already knew about?
- `receipts.pathguard` reads write sites — could it name a *private
  reimplementation* rather than only an unsanitised field? A function that
  does `relpath`-or-`basename` on something bound for a receipt is a
  recognisable shape, and finding copy 6 before it is written is worth more
  than converting copies 1–3.
- **is the canonical function where someone would look _before_ they write,
  not only where they find it after?** These are different problems and the
  five copies suggest the first is what failed. Every one of those authors
  was solving a problem, not searching for a helper — you do not look for a
  function whose existence you have no reason to suspect. A function that can
  be *found* answers "where is the thing I know I want"; a function that
  *arrives* answers "you are about to need this", and nothing in this project
  does the second. The error message is the closest thing, and it arrives
  after the mistake rather than before the writing.
- so: is there anything that makes the canonical function reach the author at
  the moment they are building a receipt field — a template, a type, a single
  constructor for receipt dicts that takes paths and sanitises them, an
  example in the place people copy from? Name what that would be even if it
  is not built here.

**A convincing answer here is worth more than the three conversions**, because
the conversions fix five known copies and this fixes the sixth.

## What this may not do

- **Convert `_portable_source` before step 1 is settled.**
- **Weaken `public_path` to accommodate a caller.** If a caller needs
  something different, that is a second function with a name that says so, or
  it is the argument in step 1.
- **Delete any of the three checks.** See *THREE CHECKS, THREE SUBJECTS* in
  `oneground/receipts/__init__.py`.
- **Touch `export_teaser_data.public_price_table`**, which is copy 4 and
  belongs to the publishing-path task.

## Acceptance

- The `_portable_source` disagreement settled in writing, with what is lost
  stated, before any conversion.
- The three copies converted or deliberately kept, each with its consumer
  checked and its blast radius reported separately.
- **The discoverability question answered with something testable**, not with
  a restatement that the error message helps. If the answer is that nothing
  further can be done, say that and say why.
- Full suite green, no published value moved.
