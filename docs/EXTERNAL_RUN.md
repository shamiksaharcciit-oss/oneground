# Verifying oneground independently

This is the whole instruction. It is written to be forwarded as-is to someone
who has never seen this project and has no reason to trust it.

---

## The instruction

On any machine with Python 3.12 or newer and about 1 GB of free disk, make a
fresh virtual environment and `pip install oneground` — the wheel pins the
versions that decide the numbers, so nothing further is needed to make the
check meaningful; download
`arxiv-150k-v1.tgz` from the release page and extract it anywhere with
`tar -xzf arxiv-150k-v1.tgz`, which creates `fixtures/arxiv-150k/` containing
three files; clone the repository with
`git clone https://github.com/oneproof/oneground`, which supplies the fixture's
published values and its manifest but not the 483 MB of vectors; then from
inside the clone run
`oneground fixture verify arxiv-150k --asset <path to the extracted fixtures/arxiv-150k>`.
It prints one line per artifact and one line per published value, each
**verified**, **contradicted**, or **couldn't-check**. The digests finish in
seconds; the values take about ten minutes, because it recomputes the
characterization, the drift pair and both reference architectures over 150,000
vectors and compares each against the tolerance the fixture itself publishes.
Nothing is sent anywhere, no account is needed, and the command works offline
once the two downloads are done.

**That ten minutes assumes the machine is not paging.** The recomputation
loads the fixture's 460 MB of vectors and builds indexes over them, so it wants
a few spare gigabytes; on a laptop already short of RAM the same work can take
well over an hour of wall clock for the same few minutes of CPU -- the run that
cut `0.1.0` took 2 h 06 m for 588 seconds of CPU, about 95% of it waiting on
page faults, with 225 MB of physical memory free. Nothing is wrong when that
happens and the result is identical; close some things or let it run.

(The peak memory the command actually needs has not been measured. On the run
above the working set was being trimmed continuously, so what it reported was
how little the machine would let it keep, not how much it wanted.)

---

## What a successful run prints

```
summary: digests 11 verified, 0 contradicted, 0 couldnt_check
         values   8 verified, 0 contradicted, 0 couldnt_check
```

## What the three outcomes mean

**verified** — recomputed here, matches what was published, inside the
tolerance the fixture declares.

**contradicted** — recomputed here and it does **not** match. This is the
interesting result. If you get one under the pinned versions, it is a real
finding about this project and we want the report: the full command output,
your platform, and `pip freeze`.

**couldn't-check** — there was nothing to compare, or no way to compare it.
Never rounded up to verified and never rounded down to contradicted. Two
things cause it, and the output names which:

- the asset is not where `--asset` points, so there are no bytes to read;
- your `numpy`, `faiss-cpu` or `scikit-learn` differ from the versions the
  fixture was built under. Every value then reports couldn't-check **with its
  numbers still shown**, so you can see the agreement and see that it does not
  count. A value recomputed under different libraries has not been reproduced
  under the pins the fixture claims.

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
