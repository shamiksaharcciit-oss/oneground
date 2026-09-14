# Report: 018d-tag-moved

## Repo state expected vs found

| expected | found |
|---|---|
| `main` after 019 | `a009737 task 019: a sentence about rows is built as a Claim and rendered from it`, tree clean |
| `v0.1.0` on `6ddcb5e`, never pushed | yes. `git ls-remote --tags origin` carries only `v0.1.0-preview`, so deleting and recreating moves nothing anyone has |
| 780 passed, 1 skipped | yes |

## What was done

### One deviation, stated first

The brief says the tag should point at **`a009737`**. It points at
**`2d971ae`** — this task's commit, directly on top of `a009737` — because the
same instruction asks for a line in `RELEASE_NOTES.md`, and a release note
describing the release belongs inside the thing it describes. Tagging
`a009737` would have shipped a release whose notes were one commit behind it.
Nothing else sits between them.

### The tag

Deleted and recreated rather than moved with a second tag object, which is
safe precisely because it has never been pushed:

```
before   v0.1.0 -> 6ddcb5e   (task 018's commit)
after    v0.1.0 -> this task's commit
```

What that brings into the release, and why each is release content rather than
work that happened to follow:

- **018b** — the rendering-path walk was one call short of the function the
  previous task's defect lived in, and the extras were never checked against
  what they install.
- **018c** — the restart flake. This one matters for release day specifically:
  `docs/RELEASE.md` step 0 runs the suite, the flake fires on a loaded
  machine, and a red tick beside a good release is the combination 017b named
  the worst one.
- **019** — the claim invariant, which closes the defect class that shipped
  once in a report (`"both carry meets"` about an engine that had failed).

### `RELEASE_NOTES.md`

One paragraph under *What is new since `0.1.0-preview`*:

> **A checked claim invariant.** Every generated sentence in a report must be
> reconstructible from the rows it cites — the options it quantifies over, the
> values it quotes and the source field each came from — and the check runs
> before the report is written. It exists because the same defect shipped
> once: a report that said "both carry meets" about an engine that had failed.
> See [docs/CLAIMS.md](docs/CLAIMS.md).

The asset digests in that file are unchanged: moving the tag does not touch
`arxiv-150k-v1.tgz` or `stackexchange-150k-v1.tgz`.

### A sentence I wrote in 018b turned out to be wrong

018b added this to `RELEASE_NOTES.md` and `docs/EXTERNAL_RUN.md`:

> Nothing is wrong when that happens, and the answer is identical; only the
> clock is different.

It was measured against a run that was slow and **finished**. This task's run
of the same command on the same machine did not finish — it raised
`Unable to allocate 211. MiB` and exited 1. So the sentence is wrong in the
direction that matters: a reader short of memory is told to wait, and what
actually happens is a traceback.

Both documents now say both outcomes and how to tell them apart, because "it
is slow" and "it stopped" call for different next steps — and they note what
survives either way, which is that the digests are checked first, so a run
that dies in the values has already confirmed the bytes.

This is a correction to released prose that this task's own measurement
disproved, which is why it is here rather than in *Observed, not done*.

### Beyond the letter of the brief

`docs/CHARTER.md`'s status table gained four rows — 018b, 018c, 019 and this
task. The brief named only `RELEASE_NOTES.md`, and this is the one thing here
that goes past it. The reason: **moving the tag is what makes those three
release content**, and a status table that stops at 018 inside a release
containing 019 is wrong about the release it ships in. Four rows, no other
change to the file, and it is reported here rather than left to be noticed.

## Measurements

### Hashes

```
dist/oneground-0.1.0-py3-none-any.whl
  500,965 bytes
  sha256  388af2f9325408b60feb9c9b50419a3629801380c28c1f655a989762ca7a0991

dist/oneground-0.1.0.tar.gz
  449,285 bytes
  sha256  aebfdd4311c025e7058e7d98174135682adcf5909053081449b40c30bf930a87
```

**The commit and tag hashes are reported with this file rather than in it.**
A commit cannot contain its own hash; and an annotated tag created after the
commit cannot be named here either, because writing it down changes the file,
which changes the commit, which means re-creating the tag and a new tag
object. Two attempts at putting them here produced two stale pairs before that
became obvious. What is stable, and what a reader can check independently, is
the pair of artifact digests above — `git rev-parse v0.1.0` and
`git rev-list -n1 v0.1.0` supply the rest.

**Why the artifacts still describe the tagged tree after this file changed.**
Neither contains `tasks/` or `docs/` — checked, not assumed:

```
sdist top level:  PKG-INFO  README.md  oneground  oneground.egg-info
                  pyproject.toml  setup.cfg
wheel top level:  oneground  oneground-0.1.0.dist-info
```

`pyproject.toml` packages `oneground*` and the README and nothing else, so
editing a report cannot change either artifact.

**A rebuild of identical code produces different bytes**, which is worth
stating because it looks like a discrepancy otherwise. Rebuilding this same
tree gave a different wheel digest at the same 500,965 bytes: wheel metadata
carries timestamps. This is the same non-reproducibility task 017b measured
for the pod image, in a smaller size, and it is why the digests above are the
ones to publish rather than something a later rebuild would confirm.

**The 018 pair no longer describes anything that will be published.** For the
record, so a stale copy is recognisable rather than merely wrong:

```
superseded   oneground-0.1.0-py3-none-any.whl  f12f5f77…  470,459 bytes
superseded   oneground-0.1.0.tar.gz            0da89b46…  420,800 bytes
```

Both grew by about 30 KB, which is `claims.py`, `test_claims.py` and the four
tests 018c added.

### `twine check`

```
Checking dist/oneground-0.1.0-py3-none-any.whl: PASSED
Checking dist/oneground-0.1.0.tar.gz: PASSED
```

### The fresh-machine check

A new venv from the **system** Python 3.12.10, with no `requirements.txt`
anywhere near it, and the newly built wheel:

```
faiss-cpu     1.15.0
numpy         2.5.3
oneground     0.1.0
PyYAML        6.0.3
scikit-learn  1.9.0
zstandard     0.25.0
```

The three packages that decide the numbers came out at the pins from the wheel
alone, again.

**1. `oneground --version`** → `oneground 0.1.0`, exit 0.

**2. `characterize`** on the same 2,000-vector synthetic corpus:

```
  intrinsic_dimensionality   53.60   of 64 declared
  boundary_crispness         0.208   (d2 > 1.2 x d1, 256 regions)
  ambiguous_query_rate       0.980   (d2 <= 1.1 x d1)
  skew_top10_share           0.065   (even would be 0.039)
  drift                      couldnt_check: no timestamp_field
```

Identical to 018's run, which is the point: nothing in 018b, 018c or 019
touches what characterize measures.

**3. `fixture verify arxiv-smoke`**, from the clone, nothing downloaded:

```
summary: digests 11 verified, 0 contradicted, 0 couldnt_check (6 receipt, 5 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check
```

**4. `fixture verify arxiv-150k --asset`** — **it did not finish.** All eleven
digests verified; the first value then raised

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 211. MiB for an
array with shape (71888, 768) and data type float32
  ... oneground/measures/drift.py:72 in drift_pair
      cents_pre = kmeans_fn(base[base_before_mask], n_centroids, seed)
```

and the command exited 1. **Run twice, failed the same way twice**, with
571 MB of physical memory free against a 29.8 GB commit charge on a 31.3 GB
limit.

**The control says this is the host, not the wheel.** The same command run
from the project venv — the same code, a different interpreter and
environment — fails identically and just as fast. The wheel's diff from the
018 pair is `claims.py`, `test_claims.py` and four tests in `test_verify.py`;
none of it is on this path. Task 018 ran this command to completion on this
machine in 2 h 06 m, so what changed is how much memory the machine has to
spare, not what the command does.

**This is reported as couldn't-check, and the acceptance criterion is not met
on this host.** Three of four commands ran; the fourth verified every digest
and could not recompute the values. It is not rounded up to a pass on the
strength of 018 having managed it.

### Leak scan and identifier scan

`oneground.environment.identifier_findings()` on the tracked tree:

```
tracked files scanned: 296
findings: 0
```

`tasks/scratch/014-leak-scan.py`:

```
== WOULD BE PUBLISHED: 1 file(s)
   [hostname] oneground/test_environment.py
        <the synthetic DESKTOP- probe>

pod ids: 23 occurrence(s) across tracked files -- KEPT, they are evidence
```

The single hit is the synthetic probe task 018 installed in place of this
machine's real hostname. The 014 scan is pattern-based and cannot tell a
synthetic `DESKTOP-` name from a real one; 017's scan can, through the
allowlist, and it is the one that runs in the suite.

### The suite

780 passed, 1 skipped — unchanged by this task, which touches two documents
and a tag. `oneground/test_packaging.py` and the whole of `oneground/report/`
were re-run after the edits: 114 passed.

## Verification

**Passed.**

- The tag points at `2d971ae` and the three commits are inside it.
- `twine check` clean on both artifacts, rebuilt from the tagged commit.
- All four fresh-venv commands ran; the wheel resolves numpy, faiss-cpu and
  scikit-learn at the pins with no `requirements.txt`.
- Identifier scan clean over 296 tracked files; the leak scan's one hit is the
  synthetic probe.
- `tasks/scratch/018-docs-numbers.py` still passes after the two document
  edits: 15 + 15 published values, 13 quoted numbers, the one-line comparison
  verbatim.

**Couldn't check.**

- **The fourth fresh-venv command.** See above: every digest verified, the
  values could not be recomputed for want of memory, twice, with a control
  showing it is the host. `docs/EXTERNAL_RUN.md` and `RELEASE_NOTES.md` were
  corrected to say so — see below.
- **Whether the release-day suite run goes green on a loaded machine.** 018c
  removed the known cause; it did not prove the suite has no other
  timing-dependent test. What can be said is that this machine ran it green
  twice today under the same load that produced the failure.
- **Nothing was pushed, published, or uploaded**, and no pod was created.

## Observed, not done

- **`fixture verify` has no handling for `MemoryError` anywhere.** `grep -rn
  MemoryError oneground/` finds one hit, and it is a test fixture in
  `test_pod.py`. So a value that cannot be recomputed for want of memory
  aborts the whole command with a traceback rather than being reported
  `couldnt_check: out of memory on this machine` with the remaining values
  carrying on. The three-outcomes rule says couldn't-check is an outcome; this
  path does not produce one. Task 016 recorded exactly this situation for
  `stackexchange-150k`'s two semantic-sharded rows, and recorded it by hand
  after the fact rather than reading it off the tool. Fixing it is a change to
  `fixture/verify.py`'s error handling, which this brief does not name.
- **`docs/RELEASE.md`'s "what this procedure has caught" has no row for the
  flake.** The table records what each release's procedure found; 018c's flake
  was found by a suite run rather than by a numbered step, so there is no step
  to attribute it to. A row saying "step 0, a latency-free timing flake that
  would have gone red on release day" would be accurate and the brief does not
  ask for it.
- **The tag is annotated with the bare message `oneground 0.1.0`.** It carries
  no note that it moved. Nothing reads a tag's message, the move is recorded
  in this report and in the commit, and a tag message that explains itself
  would be the only one in the repository that does.
- **`dist/` still holds only the current pair**, because the rebuild removes
  the directory first. The superseded digests are recorded above and the files
  themselves are gone, which is the right way round: a stale wheel on disk is
  the thing `docs/RELEASE.md` step 2 warns about attaching by accident.

## Repo now contains

Changed:

    RELEASE_NOTES.md               one paragraph: the claim invariant; and the
                                   paging note corrected -- too little memory
                                   stops the command, it does not only slow it
    docs/CHARTER.md                four status rows: 018b, 018c, 019, 018d
    docs/EXTERNAL_RUN.md           the same correction, with the traceback and
                                   what survives it

New:

    tasks/018d-tag-moved.report.md this report

Moved:

    v0.1.0                         6ddcb5e -> 2d971ae, local only

Rebuilt, gitignored:

    dist/oneground-0.1.0-py3-none-any.whl
    dist/oneground-0.1.0.tar.gz

## Blocked on developer

Unchanged in substance, with two corrections to the 018 list:

1. **Push `main`.** Three commits are unpushed: `718a445`, `a009737` and this
   task's. (`35d4934` was pushed between tasks.)
2. **Push the tag `v0.1.0`** — now on this task's commit, not `6ddcb5e`.
   Nothing needs force-pushing: the tag has never left this machine.
3. **Create the release** and attach both assets, unchanged and unaffected by
   this task:

       arxiv-150k-v1.tgz          483,468,013 bytes
         sha256 0b7a0209fa4085683950e4715d49597c820cadc575b4a4fe85ef2d4f5365c015
       stackexchange-150k-v1.tgz  460,106,978 bytes
         sha256 5d2a2be15c2c062e8b0f1ca9c24520c9e326e7d580ab411fcdbb71459181a66a

4. **Paste `RELEASE_NOTES.md`** — the version on `main` at that moment, which
   now carries the claim-invariant paragraph.
5. **`twine upload dist/*`** with the **new** artifacts:

       oneground-0.1.0-py3-none-any.whl  388af2f9325408b60feb9c9b50419a3629801380c28c1f655a989762ca7a0991
       oneground-0.1.0.tar.gz            aebfdd4311c025e7058e7d98174135682adcf5909053081449b40c30bf930a87

   Upload the files in `dist/` as they stand. If a copy of the 018 pair is
   still anywhere, it is the wrong one — and do not rebuild first, because a
   rebuild changes the digests without changing the code.
