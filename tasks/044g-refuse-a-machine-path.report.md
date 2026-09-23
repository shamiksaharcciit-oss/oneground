# Report: 044g-refuse-a-machine-path

## The refusal found a fifth private copy of the transform on its first run

**Leading, because it is the ruling vindicated by the thing the ruling
predicted.**

The argument for putting the check at serialisation was that **at
serialisation an opaque value is a value**. Neither static check can see
inside a function call: `receipts.pathguard` reads the write site's source and
sees `_portable_source(plan.requirements_path)`, a call into another module;
the tracked-tree scan never sees `propose_info.json` at all, because it lands
under `runs/`.

The refusal saw it immediately. On its first run against the suite it rejected
`proposals/.../propose_info.json` with two fields:

    workdir                   C:/Users/<HOME>/.../propose0/out
    requirements_file.path    C:/Users/<HOME>/.../propose0/requirements.yaml

`workdir` was recorded raw. `requirements_file.path` went through
`calibrate.history._portable_source` — **a private reimplementation of
`receipts.public_path`**, in a file that tasks 044f and 044g had both already
been through, reading the source, looking for exactly this.

A check that sees payloads found what a check reading source could not, in a
file two tasks had already searched. That is the whole argument, demonstrated
rather than asserted, and it took one run.

## Five private copies of one transform, and what that actually says

Counted and named, because five is not a series of oversights:

| # | where | task | what it does |
|---|---|---|---|
| 1 | `proposals/propose.py:_named_file` | 014 | basename + digest, "not its path… a card is published" |
| 2 | `calibrate/history.py:_portable_source` | 018 | relpath to the repo root, else unchanged |
| 3 | `models/projection.py:110` | — | `os.path.basename(path)` beside its digest |
| 4 | `corpora/export_teaser_data.py:public_price_table` | 041 | relpath inside the repo, basename outside |
| 5 | `receipts.public_path` | **043** | the canonical one |

**The dates are the finding.** Copies 1, 2 and 4 all *predate* the canonical
one. Nobody failed to find a shared function — for most of this project's life
there was no shared function to find, and four people independently solved the
same problem in four places. 043 then wrote the fifth, declared it canonical,
converted three call sites, and **did not retire the other four.** That is the
defect: not the copies, the un-retirement.

Each also disagrees with the others in a way that matters. `_named_file` keeps
only the basename and loses which file inside the checkout it was.
`_portable_source` deliberately leaves an outside path **unchanged**, which is
the opposite of what `public_path` does, and its docstring argues for it —
*"shortening it would say something false"*. So the five do not merely
duplicate; two of them would refuse each other's output.

### Is `receipts.public_path` where someone would look?

**Yes, and it does not matter, which is the more useful answer.**

The home is right: it is in `oneground/receipts/`, the package named for the
artifacts it serves, beside `write_json_stable`, which anybody writing a
receipt must already import. Someone reading that module finds it.

But three of the five copies were written by people who *could not* have found
it, and discoverability cannot fix a function that does not exist yet. The
next copy will be written by someone who does not think to look, and better
naming will not reach them either.

> **The durable fix is not documentation. It is the refusal, whose error
> message names the function at the moment of the mistake.**

`write_json_stable` now says, in the failure itself:

    If you are writing a receipt: pass the value through
    receipts.public_path() at the point you build the field.

That reaches someone who never read the module, was not looking for a shared
helper, and did not know the rule existed. It is discoverability delivered by
a failing write rather than by a docstring nobody opens.

**Not done:** retiring copies 1–3. Each has a consumer and a slightly
different contract, and converting them is a behaviour change on three more
write paths. Named here as the remaining work rather than folded in.

## Three checks, three subjects — recorded where it will be read

The developer's instruction: put this somewhere durable, because the next
person will read three overlapping checks as redundancy and delete one.

It is now in **`oneground/receipts/__init__.py`**, under *THREE CHECKS, THREE
SUBJECTS*, opening with *"If you are here to delete one of these as redundant:
they are not."* Each entry names its subject, what it is blind to, and the
real defect that blindness let through. Both other checks point at it —
`receipts/pathguard.py`'s module docstring and
`test_no_tracked_file_carries_a_machine_identifier`'s own docstring — so it is
met from whichever one someone opens first.

| check | subject | blind to | the defect that proved it |
|---|---|---|---|
| tracked-tree scan (017) | what git tracks | `runs/`, which a publisher reads | four writers, a home directory in every local `build_info.json` |
| `receipts.pathguard` (044f) | a write site's source | a path inside an opaque call | `price_table.path` via `prices.as_dict()` |
| `write_json_stable` (044g) | the payload at serialisation | bare relative paths; a username with no path; anything not written through it | `_portable_source`, through two tasks of review |

**Source, then output, then value.** A defect invisible to one is routinely
visible to the next, and the overlap is small.

## What was built, in three commits

**1 — resolution.** `receipts.resolve_recorded_path` and `checkout_of`. The
recorded path is searched across an ordered list of bases and **confirmed
against the `sha256` the receipt already records**, so a candidate is
identified rather than guessed at. The four `requirements_file.path` writers
moved to `public_path`; `propose` resolves instead of opening. Suite green at
1523 passed.

**2 — `inputs.*.path`.** Converted. Both consumers were already defensive —
`propose._named_file` reduces to a basename *because* the writer was absolute
— so nothing downstream changed. Verified by exercising the real writer rather
than by reasoning: a full `characterize` on the smoke requirements into a
temporary workdir now writes **zero** offending fields across
`build_info.json`, `characterization.json`, `sample_ids.json` and
`queries_ids.json`.

**3 — the refusal.** `write_json_stable` raises `ReceiptRefused`, naming every
offending key path and its value, with the user's remedy and the writer's, and
an explicit line that the non-repair is deliberate.

## Measurements

| | |
|---|---|
| recorded paths in `runs/` that did not resolve as absolute | **7 of 32**, two of them `/workspace/…` from pod sessions |
| offending fields written by today's `characterize`, after | **0** |
| field families converted | 3 — `requirements_file.path`, `inputs.*.path`, `propose_info`'s `workdir` and `requirements_file.path` |
| private copies of `public_path` found | **5**, three predating the canonical one |
| blast radius of the refusal, whole suite | **12 tests, all one cause**, all in `propose_info.json`; zero elsewhere |
| suite with the refusal enabled | 1523 passed, 40 skipped, 1 failed (known stale artifact) |

The blast radius is the number worth keeping: the refusal was predicted to be
disruptive and **was not**, because two commits of conversion preceded it.
Enabling it first would have broken `characterize` on every run.

## What a user with pre-043 receipts sees

They exist — six info files in this checkout, and every workdir fetched from a
pod. The remedy has to be a sentence they read.

**Reading a pre-043 receipt** — `oneground propose` on a workdir whose
`simulate_info.json` records an absolute path that is not on this machine:

```
proposal refused:
  - the requirements file the baseline run recorded could not be found:
    requirements.yaml (sha256 e884bd33eb7f). Looked in:
          requirements.yaml  (as recorded)
          <checkout>/requirements.yaml  (this checkout)
          <workdir>/requirements.yaml  (beside the workdir)
          <workdir>/requirements.yaml  (beside the workdir, by name)
        Pass --requirements <requirements.yaml>, or re-run `oneground
        simulate` in this checkout so the receipt records a path that
        resolves here.
```

It names every base it tried, so the next step is a reading rather than a
guess, and it gives two remedies — one immediate, one permanent.

**In practice most pre-043 receipts will not reach that message at all**,
because resolution now finds the file: the recorded absolute path fails, the
checkout base succeeds, and the digest confirms it. That is the pod case
working where it used to fail.

**Writing, if a field still slips through:**

```
refusing to write <path>: 2 field(s) name a filesystem, and a receipt records
what a file is rather than where one machine keeps it.
    workdir
        C:/Users/<HOME>/.../out
    requirements_file.path
        C:/Users/<HOME>/.../requirements.yaml

  Not repaired on purpose: a receipt quietly corrected on the way out leaves
  the writer wrong and tells nobody.
  If you are running oneground: re-run this command in a checkout, which
  records repo-relative paths.
  If you are writing a receipt: pass the value through
  receipts.public_path() at the point you build the field.
```

Reading it back, the one thing not obvious is which of the two audiences a
given reader is — so both are addressed by name rather than left to inference.

## `KNOWN_OPEN` deleted itself, which is the opposite of the stale-state defect

044f left four sites unfixed and listed them in
`receipts/test_pathguard.py:KNOWN_OPEN`, asserted **two-sidedly**: a fifth
instance failed the guard, and closing one of the four without deleting its
entry failed the second assertion. 044g closed all four, that second assertion
fired, and the set was removed in the same commit.

> **A marker that cannot outlive the thing it marks.** `docs/PRACTICE.md`
> opens with the opposite — a section stating a current state, decaying
> silently because nothing fails when the world moves. This is the same kind
> of sentence with a test attached, so the world moving is exactly what fails.

The file keeps a comment where the set was, recording that it existed, what it
held and why it is gone.

## Verification

| check | result |
|---|---|
| The refusal rejects a payload naming a filesystem | **PASS** — caught `propose_info.json` on its first run |
| It names the key path and the fragment | **PASS** — both, with the value |
| It does not repair | **PASS** — raises; nothing is rewritten |
| Both remedies in the message | **PASS** — quoted above |
| Blast radius measured before the behaviour changed | **PASS** — 66 files / 137 fields on disk, then narrowed to live writers by exercising them |
| `requirements_file.path` settled | **PASS** — option 1, on the measurement |
| The moved-workdir case measured | **PASS** — 7 of 32, pod sessions counted as the case they are |
| `KNOWN_OPEN` emptied in the same commit | **PASS** — by its own assertion failing |
| All three checks present and passing | **PASS** — none deleted, none folded in |
| Three-subjects statement recorded durably | **PASS** — `receipts/__init__.py`, referenced by both others |
| No published value moved | **PASS** — no fixture, spec or MANIFEST touched |
| Full suite | 1523 passed, 40 skipped, 1 failed — the known stale artifact |

## Observed, not done

1. **Three private copies of `public_path` remain** — `_named_file`,
   `_portable_source`, `projection.py:110`. Each has a consumer and a
   different contract; `_portable_source` deliberately leaves outside paths
   unchanged, which contradicts `public_path`. Retiring them is three more
   write-path changes.
2. **`export_teaser_data.public_price_table` still exists**, measured in 044e
   as a no-op on the published fixture. Ruled to go, with the exporter
   refusing instead; its own task on the publishing path.
3. **Seven `tasks/scratch/` findings** from `pathguard`, unchanged from 044f.
4. **`site/teaser/data/values.json` carries a redacted path** —
   `tasks/note-values-json-redacted-path.md`, to be routed with 044e's
   `measured.k_sweep` export, which touches that file anyway.

## Repo now contains

| path | what |
|---|---|
| `oneground/receipts/__init__.py` | `resolve_recorded_path`, `checkout_of`, `MACHINE_PATH`, `ReceiptRefused`, `machine_paths_in`, the refusal in `write_json_stable`, and *THREE CHECKS, THREE SUBJECTS* |
| `oneground/receipts/test_resolve_recorded_path.py` | 8 tests, including the pod case |
| `oneground/receipts/test_pathguard.py` | `KNOWN_OPEN` removed, with the record of why |
| `oneground/receipts/pathguard.py`, `oneground/test_environment.py` | both point at the three-subjects statement |
| `oneground/characterize.py`, `simulate/__init__.py`, `verify/__init__.py` | `requirements_file.path` and `inputs.*.path` through `public_path` |
| `oneground/proposals/propose.py` | resolves rather than opens; `propose_info` fields through `public_path` |
| `tasks/044g-refuse-a-machine-path.report.md` | this report |
| `tasks/note-values-json-redacted-path.md` | for core, with 044e |

## Blocked on developer

Nothing. 044e is next and still holds the teaser sweep export.
