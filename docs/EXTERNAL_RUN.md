# Verifying oneground independently

This is the whole instruction. It is written to be forwarded as-is to someone
who has never seen this project and has no reason to trust it.

---

## The instruction

On any machine with Python 3.12 or newer and about 1 GB of free disk, make a
fresh virtual environment and `pip install oneground` — the wheel pins the
versions that decide the numbers, and it carries the fixture's spec, manifest
and ground truth, so there is nothing to clone; download
`arxiv-150k-v1.tgz` from the release page and extract it anywhere with
`tar -xzf arxiv-150k-v1.tgz`, which creates `fixtures/arxiv-150k/` containing
three files; then, from any directory, run
`oneground fixture verify arxiv-150k --asset <path to the extracted fixtures/arxiv-150k>`.
It first prints three preconditions — the fixture, the pinned environment and
the release asset — each found or missing, and for anything missing, how to
supply it. Then one line per artifact and one line per value, each
**verified**, **contradicted**, or **couldn't-check**. The digests finish in
seconds; the values take about ten minutes, because it recomputes the
characterization, the drift pair and both reference architectures over 150,000
vectors and compares each against the tolerance the fixture itself publishes.
Nothing is sent anywhere, no account is needed, and the command works offline
once the two downloads are done.

**The virtual environment is a requirement, not a suggestion.** The wheel pins
numpy, faiss-cpu and scikit-learn exactly, so installing it into the system
Python replaces the versions of whichever of those, and of their dependencies,
that Python already has. The command's preconditions say which kind of
interpreter it is running under. One command per line:

```bash
# macOS or Linux
python3 -m venv .venv
. .venv/bin/activate
pip install oneground
tar -xzf arxiv-150k-v1.tgz
oneground fixture verify arxiv-150k --asset fixtures/arxiv-150k
```

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install oneground
tar -xzf arxiv-150k-v1.tgz
.venv\Scripts\oneground.exe fixture verify arxiv-150k --asset fixtures\arxiv-150k
```

**A wrong `--asset` stops the run.** The tarball extracts to
`fixtures/arxiv-150k/`; a path that holds none of its three files exits 2,
saying what it looked for, what the folder holds, and the right folder when it
is one level down. A tarball extracted where the fixture is looked for is
named as that, not mistaken for the fixture.

**Run it without `--asset` first if you like.** It checks the digests it can,
prints the asset's name, its size and the release page it is on, recomputes no
value, and exits 2. One run tells you everything that is missing, not the
first thing.

**That ten minutes assumes the machine is not paging.** The recomputation
loads the fixture's 460 MB of vectors and builds indexes over them, so it wants
a few spare gigabytes; on a laptop already short of RAM the same work can take
well over an hour of wall clock for the same few minutes of CPU -- the run that
cut `0.1.0` took 2 h 06 m for 588 seconds of CPU, about 95% of it waiting on
page faults, with 225 MB of physical memory free. The result is identical when
it finishes; close some things or let it run.

**With too little memory some values cannot be recomputed.** On a later run
on the same machine every digest verified and a value then raised

    numpy ... Unable to allocate 211. MiB for an array with
    shape (71888, 768) and data type float32

Up to `0.1.0` that stopped the command with no value reported at all. It no
longer does: a value this machine cannot recompute is reported
**couldn't-check**, with the allocation that failed as its reason, the other
values carry on, and the command exits 0 if nothing is contradicted. The
summary says how many values could not be recomputed on this host, and that the
digests -- checked before any value -- still confirm the bytes. Slow and short
of memory are different outcomes: the first wants patience, the second wants
memory, and a re-run with more of it decides the rows that could not be
checked.

(The peak memory the command actually needs has not been measured. On the slow
run the working set was being trimmed continuously, so what it reported was
how little the machine would let it keep, not how much it wanted; the 211 MiB
above is one allocation that failed, not the total.)

---

## What a successful run prints

From a bare install with the asset, on a machine with the memory for every
value:

```
summary: digests 7 verified, 0 contradicted, 10 couldnt_check (6 receipt, 11 declared)
         values  8 verified, 0 contradicted, 0 couldnt_check
```

The ten digests that come back couldn't-check are files neither the package nor
the asset carries: the three ground-view tables and the six files of the
published report, which are in the repository, and `projection.npy`, which is
not published anywhere. The output says which is which. From a clone of the
repository the tables and the report verify too. The values need only what the
package and the asset carry.

Eight values verified is every value this command recomputes. The fixture
publishes four more -- the semantic-sharded routing ceiling and its copy
percentiles -- that it does not recompute, and the summary names them rather
than calling eight "every published value".

**The number of verified digests depends on where you run it, and that is
expected.** The repository carries files the wheel does not. For
`oneground fixture verify arxiv-smoke`, a clone verifies eight of the eleven
listed files and a bare wheel install verifies four: `queries.npy` and the
three ground-view tables are in the repository and not in the package. So an
instruction printed from a clone says `digests 8 verified` where your install
says `digests 4 verified`. Neither is a failure: nothing is contradicted, both
exit 0, and each couldn't-check line gives the reason that file is absent.

## What the three outcomes mean

**verified** — recomputed here, matches what was published, inside the
tolerance the fixture declares.

**contradicted** — recomputed here and it does **not** match. This is the
interesting result. If you get one under the pinned versions, it is a real
finding about this project and we want the report: the full command output,
your platform, and `pip freeze`.

**couldn't-check** — there was nothing to compare, or no way to compare it.
Never rounded up to verified and never rounded down to contradicted. The
output names the cause of each one, and the summary gives each cause its own
sentence:

- the asset is not where `--asset` points, so there are no bytes to read. No
  value is recomputed, the preconditions say where the asset was looked for
  and where to get it, and the command exits 2;
- your `numpy`, `faiss-cpu` or `scikit-learn` differ from the pinned versions.
  The preconditions name which, no value is recomputed, and the command exits
  2. With `--allow-unpinned` the values are recomputed anyway and each reports
  couldn't-check **with its numbers still shown**, so you can see the
  agreement and see that it does not count. A value recomputed under different
  libraries has not been reproduced under the pins the fixture claims;
- this machine could not recompute a value -- out of memory, say. That value
  alone is couldn't-check, with the reason, and the rest carry on.

**On a clean `pip install oneground` you should get `verified`, not
couldn't-check.** The wheel pins those three exactly, so a fresh virtual
environment gets the versions the fixture was built under without you doing
anything. If you see couldn't-check on a pin, something in your environment
overrode them — the output says which package and which two versions, and
that is worth telling us about.

## Why this is worth ten minutes

The claim being checked is not "these numbers are correct". It is **"this
installation, on your hardware, computes the same numbers we published"** —
which is the only version of the claim you can test without trusting us.

The fixture reached `status: verified` because that check passed on a second
machine and a second operating system: built on Linux with a CUDA GPU,
reproduced on Windows on a laptop, under the same pinned versions, with all
eight values landing between one and three orders of magnitude inside their
tolerances. It sat at `status: built` for four development tasks because one
value — the drift pair — was not reachable by the verifier, and it was not
marked verified until it was.

## The second fixture, and why its claim is weaker

`0.1.0` also ships `stackexchange-150k-v1.tgz`: 150,000 Stack Overflow
questions, built to the same rules so the two read line for line. The same
instruction works on it, with the id and the asset path changed:

```
oneground fixture verify stackexchange-150k --asset <path to the extracted folder>
```

It carries `status: built`, not `verified`, and the difference is the point.
Its digests check and its values are measured, but two —
`semantic_sharded.recall_at_10` and `.storage_amplification` — come back
**couldn't-check** on the machine that published it, which runs out of memory
recomputing the 256-shard reference over 150,000 vectors. That is recorded
with its reason rather than dropped, and the fixture is not called `verified`
until someone reproduces those two as well. If your machine has the memory,
you will get a stronger result than the publisher did, and we would like to
hear about it.

The two fixtures are compared measure by measure in
[FIXTURES.md](FIXTURES.md). They are reference points, not a leaderboard: every
recommendation oneground makes is measured on your own corpus.

## If something goes wrong

The output names the file and field behind every line, so a disagreement can
be traced without reading the source. Please open an issue with the full
output including the interpreter line at the top, your platform, and
`pip freeze`. A digest contradiction and a value contradiction are different
problems and the report distinguishes them.
