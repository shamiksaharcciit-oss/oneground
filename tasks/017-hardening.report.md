# Report: 017-hardening

## Repo state expected vs found

| The brief assumed | Found |
|---|---|
| branch `task-017` from main at or after `65fc33f` | yes — branched from `c0e0ae0` (`brief: 017 hardening`), which is `origin/main` |
| `docker/pod/Dockerfile`, `.github/workflows/pod-image.yml`, `docker/pod/IMAGE.lock` | absent, as the brief implies — all three are new here |
| `oneground/embed/` to add truncation counting to | present, 56 lines, two functions and no tests |
| `corpora/run_verify_pod.sh`, `corpora/run_fixture_build.sh` | present |
| `docs/INTAKE.md`, `docs/VERIFY.md`, `oneground/environment.py`, `.github/scripts/` | present |
| the `scope` decision-log count "verify it's fixed" | **already fixed**, and now checked against the artifact rather than the code — see item 6 |
| the `runs/` test name and skip reason "done in 015b — confirm" | confirmed, both halves |
| the price table `as_of` assertion | **did not exist**; built here |

One thing the brief did not anticipate, found immediately by the guard it
commissioned: `tasks/016-decision-log.txt` is on `origin/main` carrying two
absolute developer paths. Details under item 4.

## What was done

All six items. They are reported in the order they were built, which is
smallest-blast-radius first, not the brief's numbering.

### 4. The tracked-tree identifier scan

This is the guard 015 found missing, and it found a live leak on its first
run.

014 redacted the developer's hostname and home directory out of the tree and
added guards so they could not return. Every one of those guards asserts on
what is about to be **written**: `stamp()`, the calibration history id, and an
AST check that no module reaches for `platform.node()`. Nothing read what was
already committed. 015 discovered that by grepping after a rebase rather than
by a test failing.

`oneground/environment.py` gains `machine_identifiers()`, `scan_text()`,
`tracked_files()` and `identifier_findings()`. Three rules: a home directory
carrying a real account name, a `DESKTOP-` hostname, and this machine's own
identifiers.

**What the rules deliberately do not flag matters as much as what they do.**

- Placeholders are invisible to the path rule *by construction* rather than by
  exception: the captured account name excludes `<`, `%`, `$`, `~`, a backtick
  and a dot-only run, so `C:\Users\<developer>`, `%USERNAME%`, `$HOME` and
  `C:/Users/...` never match. A guard that flagged the redacted form would be
  telling people to stop redacting.
- Generic account names are dropped from the identifier set. `runner` is every
  GitHub Actions job's username **and** an ordinary English word; scanning the
  tree for it would fail CI on prose and train everyone to ignore the scan.

One false positive appeared and was fixed rather than allowlisted
(`tasks/002-canonical-build.report.md`, a `C:/Users/...` ellipsis). The
allowlist is four files, each with a reason, and none of them is a file that
leaks — they are the ones that quote the trap by name.

A second test pins the floor: `identifier_findings()` returning `[]` only means
something if the walk looked at something, so it asserts the tracked-file count
is over 100 (it is 270) and that a known path is among them.

### 6. The three carried items

**The `scope` count is fixed, and now checked against the artifact.** 011's bug
was that `_constraint_names` was a hand-maintained chain of `if` branches and
`qps_target` was never added to it, so the scope line said "4 constraint(s)"
while every option carried a `qps` verdict. `_judged_constraint_names` reads
off the verdicts instead. On the real arXiv `report.json` the distinct judged
constraints across 31 verdicts are `recall_at_k`, `storage_amplification`,
`latency_p95`, `qps`, `monthly_budget` — five — and the scope line says five
and names `qps`.

**The `runs/` test name and skip reason** are present from 015b, both halves:
the name ends `_needs_local_run`, and the skip names the missing files and the
command that produces them.

**The price table `as_of` check did not exist**, so it is built. A table dated
after the run it prices is quoting prices that did not exist when the numbers
were taken, and it happens the ordinary way — refresh `prices.yaml`, re-run
`report` over an older `verify.json`, and the arithmetic is unchanged while the
output looks current. Compared against `verify_info.run_at`, because that is
when the measurements being priced were made.

Reported, not raised — which is the idiom already sitting next to it for a
price table that fails to load. The costs and the `monthly_budget` verdict are
dropped rather than quoted out of their period, and `report.price_table_rejected`
says why, so a reader who finds no costs is not left guessing whether none were
configured or one was refused. An unparseable or absent date is couldn't-check:
`load_prices` defaults `as_of` to the string `"unknown"`, and that is a reason
to say nothing rather than to drop the costs.

### 2. `runs: N` — the spread, and the three-way verdict

`verify.runs: N` (default 1) repeats the load phase against the same engine,
namespace and sample, **restarting the engine between runs**. The restart is
the point: run 2 against a process that has served run 1 for five minutes has
a warm page cache and a settled allocator, which is a continuation of run 1
rather than a second sample of it.

A restart that does not happen is recorded as one that did not. `verify.json`
carries `load_restarts`, one sentence per gap, and a run that could not be
restarted says `not restarted: …`. A spread measured across runs that quietly
shared a warm process is a different quantity from the one the report would
otherwise call it.

Every run is kept in `load_runs`. The under-load row gains `p95_across_runs`
with `min`/`median`/`max`/`spread` and the per-run list, so the aggregate can be
recomputed from the runs rather than taken on trust. `p95_ms` stays a float so
existing readers keep working, and becomes the **median** — the honest single
number when there are several. Nothing decides a verdict from it.

**The verdict rule:**

| | when |
|---|---|
| `meets` | the **worst** run meets |
| `fails` | the **best** run fails |
| `couldnt_check` | otherwise — `meets in k of N runs, spread X ms` |

The third row is the one that matters. 015 measured this configuration at
38.22 ms and 42.82 ms against a 40 ms cap and stated `meets` once and `fails`
once, with nothing about the architecture changing between them. Given exactly
that evidence the rule now returns
`couldnt_check: meets in 1 of 2 runs, spread 4.60 ms`, and carries **no
`value`** — a couldn't-check with a number attached invites the reading it
exists to prevent.

`docs/VERIFY.md` gains the section directly after the 38.22/42.82 note, which
had named this as task 017 work.

### 5. `qps_max`

`qps_max` was deliberately unimplemented from 009 through 016, and the reason
is worth restating: the cheap way to produce one is to read the achieved rate
off a throttled run, and **a throttled run cannot exceed what it was offered**,
so that number is the offer wearing the ceiling's name.

`ramp_to_ceiling()` measures it the only way it can be measured — remove the
throttle, raise concurrency, stop on degradation. Two stopping conditions, both
degradation rather than a target: error rate over 0.5%, or p99 over 5× the
first step's. The baseline is the first step's p99 and not the RTT baseline,
because the question is when the *engine's* latency runs away and the round
trip is common to every step.

Reported as its own decision-log row carrying its own caveat, opt-in per
session (`measure_ceiling: true`), and never read by the `qps` sustain verdict
— with a test that asserts a 9999 qps ceiling cannot reach a sustain verdict
that failed at 112 qps.

### 3. Truncation accounting

Truncation is the one intake fault that leaves no trace. A wrong dimension
raises, a missing file raises, a bad metric shows up as terrible recall. A
record longer than `max_seq_length` is cut to the limit and comes back as a
well-formed vector; ground truth is computed from those same truncated vectors,
so recall against it is high and self-consistent — and every number in the
report describes a corpus that is not the one on disk.

`embed/` gains `count_truncated()`, which tokenizes with the model's own
tokenizer, the one `encode` is about to use, so the count is what will actually
happen rather than an estimate from characters or whitespace. `characterize`
counts **before** embedding, so a run that dies in the encoder has already said
what it was about to discard, and writes `truncated_count`, `max_seq_length`
and the whole `truncation` block to `build_info.json` as declared facts.

**`0` and `null` are different values on purpose.** `0` means it was counted and
nothing was cut; `null` means it could not be counted — no tokenizer, or no
text path. The reassuring answer must never be what you get when nothing
looked, which is the failure mode the whole item exists to close.

`docs/INTAKE.md` gains the rule under Tier 1, where someone bringing text is
reading: one record is one vector, so bring chunks.

### 1. The pre-baked pod image

The durable fix for six environment faults across five billed sessions in 015,
every one of them setup rather than work.

- **`docker/pod/Dockerfile`** from the same base
  (`runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404`): the pinned deps in an
  isolated venv at `/opt/oneground-venv`, the Qdrant 1.19.1 release binary,
  PostgreSQL 16.15 + pgvector 0.8.6 from PGDG at the same pins
  `run_verify_pod.sh` uses, the postgres data and log directories pre-created
  and owned under `/var/lib/postgresql`, `git`, `runpodctl`, and a marker at
  `/opt/oneground-image/BAKED`. **No repo** — the bundle still syncs, because a
  session exists to run the commit under test.

  The two directory faults are fixed *in the image*, with the reasons in
  comments: `PGDATA` is not under `/root` (which is `drwx------`, so postgres
  cannot traverse it, and chowning the leaf does not help), and the log is not
  under `/workspace` (the network volume, which is not writable by postgres and
  not chownable either — three distinct properties that produced three separate
  failures).

  The build ends with assertions rather than hope: the qdrant binary is
  executable, the venv's python imports numpy/faiss/torch, `PGDATA` exists,
  `postgres --version` and `initdb --version` answer, and the `vector` extension
  control file is present. A build that cannot answer those is not a usable
  image, and finding that out in CI is the whole point.

- **The marker carries the versions**, not just its own existence, so a session
  that finds it records *which* image it ran on — engine versions read from the
  image rather than from apt at run time, which is what the brief asks for.

- **`.github/workflows/pod-image.yml`** builds on changes to `docker/pod/**`,
  `requirements.txt` or the workflow itself. Tagged with the short SHA **and
  nothing else** — no `latest`, no branch name: a floating tag sitting in the
  registry is an invitation to reference it, which is the thing this is trying
  to make impossible. Pull requests build without pushing, so a broken
  Dockerfile fails in CI and not on a billed pod.

- **`docker/pod/IMAGE.lock`** holds the digest, and
  **`oneground/pod/image.py`** reads it. The rule worth stating on its own: **a
  missing digest is never a reason to fall back to a tag.** `reference()`
  raises. A session that silently ran different bytes than it recorded is worse
  than a session that did not start, and it is invisible in exactly the way the
  lock exists to prevent. A test asserts that the error message does not even
  mention the tag that is sitting right there in the file.

  The lock is filled by a human, and the workflow fails on the next push if the
  committed lock and the built image disagree. An automation that pushed to the
  branch it builds from could move the pin it exists to hold still.

- **Both scripts detect the marker.** `run_verify_pod.sh` skips the PGDG install
  and the qdrant download and takes the pinned versions from the marker;
  `_setup_script` symlinks `/opt/oneground-venv` instead of building a venv and
  running `pip install` — the step that cost about five minutes of billed time
  per session. `run_fixture_build.sh` installs nothing itself but now says which
  venv it got, because "three minutes faster" is only a measurement if the log
  says which path produced it.

- **Sessions reference the image by digest.** `verify` prefers the locked digest,
  lets an explicit `verify.image` win, and otherwise names the documented
  fallback **and logs that it is doing so**.

## Measurements

### Items 2 and 5, locally on arxiv-smoke against Qdrant 1.19.1

`tasks/scratch/017-ceiling-and-spread.yaml`, `runs: 3`, concurrency 8, 50 qps
offered, 30 s per run.

| run | p95 under load | achieved qps |
|---|---|---|
| 1 | 123.68 ms | 49.99 |
| 2 | 94.70 ms | 50.00 |
| 3 | 88.87 ms | 51.03 |

`min 88.87 · median 94.70 · max 123.68 · spread 34.81 ms` — a **39% spread** on
an idle laptop, which is a larger relative spread than the 12% that prompted the
rule. Restarts took 0.7 s and 0.8 s to reachable again, both recorded in
`load_restarts`.

Note the shape: run 1 is the slowest and the two runs *after* a restart are
faster. The restart did not make later runs cold — ingest and index build had
just finished before run 1, and that is what run 1 was still paying for. This is
the reason the rule reads the whole set rather than the first run.

**The ceiling ladder:**

| concurrency | achieved qps | p99 |
|---|---|---|
| 1 | 87.10 | 34.8 ms |
| 2 | 107.44 | 86.0 ms |
| 4 | **124.28** | 126.6 ms |
| 8 | 135.98 | 313.3 ms ← degraded |

`qps_max 124.28 at concurrency 4`, stopped because `p99 313.3 ms exceeded 5x the
first step's 34.8 ms at concurrency 8`. Note that concurrency 8 achieved *more*
qps (135.98) and is correctly **not** the ceiling: it bought that throughput
with a p99 nine times the baseline, which is the degradation the limit exists to
catch.

**Latency itself is `couldnt_check` on this machine** — the baseline RTT p95 is
138% of the query p95, over the 20% limit. That is the noise guard working, and
it is why this run proves the mechanism rather than measuring anything. A real
spread number waits for the matched pod session.

### Item 3, with the real tokenizer

`tasks/scratch/017-truncation-end-to-end.py`, BAAI/bge-base-en-v1.5 — the model
the fixtures were built with — 55 synthetic records, 15 of them deliberately
over a 128-token limit:

```
truncated_count      15
n_records            55
truncated_fraction   0.2727
longest_tokens       402
max_seq_length       128
```

and the warning fired:

```
WARNING: 15 of 55 records (27.3%) are longer than max_seq_length 128 tokens and
will be TRUNCATED; the longest is 402 tokens. if these are documents rather than
chunks, chunk them first -- everything past the limit was discarded before a
single number was computed, and no measurement downstream can tell you it
happened
```

### Item 4, the scan against this tree

270 tracked files scanned. Identifiers on this machine: `desktop-hagopqc`,
`polo2`.

| | |
|---|---|
| findings before the redaction | 2, both in `tasks/016-decision-log.txt` |
| findings after | 0 |
| false positives, first pass | 1 (fixed in the rule, not allowlisted) |
| allowlist size | 4 files, each with a stated reason |

### The suite

| after item | passed | skipped |
|---|---|---|
| 4 | 618 | 1 |
| 6 | 618 | 1 |
| 2 and 5 | 627 | 1 |
| 3 | 638 | 1 |
| 1 | 646 | 1 |

The one skip is `test_pod.py`'s live RunPod test: `RUNPOD_API_KEY not set`.

## Verification

**Passed.**

- The identifier scan passes on the current tree and fails on an injected path
  — both acceptance halves, the second asserted against six injected forms
  (Windows, Windows-with-posix-slashes, Linux, macOS, a `DESKTOP-` hostname, a
  bare identifier) and nine redacted forms that must stay clean.
- `runs: 3` produces the spread and the three-way rule. The three verdict
  branches are tested against synthetic runs straddling the threshold,
  including the case that matters most: three runs whose **median is under the
  cap and max is over it**, where reporting the median would silently turn a
  straddle into a pass.
- The truncation count appears in `build_info.json` and the warning fires, both
  with a stub tokenizer (the counting rule, including that special tokens count
  toward the limit, that exactly-at-limit is not truncated, and that batching
  the walk neither drops nor double-counts) and with the real model.
- `qps_max` exists as its own row on smoke, separate from `qps`, and is proved
  unreachable from the sustain verdict.
- 646 passed, 1 skipped.

**Couldn't check.**

- **The image has never been built in CI, and no digest exists.** The workflow
  builds on push; this branch has not been pushed, and the brief says not to.
  So `IMAGE.lock` records `digest=` empty and the state `NOT YET BUILT` in
  words, `oneground/pod/image.py` raises rather than substituting the tag, and
  a test asserts that the committed lock is self-consistent in exactly that
  state. This is couldn't-check and is not rounded up.
- **The before/after setup-time measurement has not been taken.** It cannot be:
  the "after" half needs the image on GHCR, which needs the workflow to have
  run, which needs the push. See *Blocked on developer* — this is the one item
  whose ordering the brief's step numbering does not imply.
- **The full image build did not complete locally.** The base image is tens of
  gigabytes of CUDA and torch; the build was still pulling it after 20 minutes
  and is not something this machine finishes usefully. What *was* verified
  locally is below, and it is the half that has actually broken.
- **Engine versions as engine facts "from the image, not from apt"** is wired
  (the marker carries them and `run_verify_pod.sh` sources it) but has never
  executed, because that path only runs on a pod carrying the baked image.

**Verified locally instead, and why it is the right half.** All six faults in
015 were in the layers below CUDA: the PGDG install, where `PGDATA` lives,
where postgres can write its log, the qdrant fetch. Those are built and
asserted on a stripped `ubuntu:24.04` — the same noble the base image is built
on — in `tasks/scratch/017-image-mechanism.Dockerfile`, with the same pins and
the same closing assertions minus the venv. This is the same move that fixed
015: reproduce the mechanism in a stripped container rather than on a billed
pod.

That build **passed**, exit 0 in 19m26s (most of it the pgvector layer and the
export), and its closing assertions answered:

```
postgres (PostgreSQL) 16.15 (Ubuntu 16.15-1.pgdg24.04+2)
initdb   (PostgreSQL) 16.15 (Ubuntu 16.15-1.pgdg24.04+2)
/usr/share/postgresql/16/extension/vector.control
```

Then the image was **run**, because a build asserting that a directory exists
is not the same as a process being able to use it — and "exists but the
process cannot traverse it" is precisely what faults 4 and 5 were:

| | |
|---|---|
| marker | `qdrant_version=v1.19.1`, `pg_version=16.15-1.pgdg24.04+2`, `pgvector_version=0.8.6-1.pgdg24.04+1` |
| `qdrant --version` | **qdrant 1.19.1** |
| `initdb` as the **postgres user** into `PGDATA` | **OK** — fault 4 (PGDATA under `/root`, untraversable) does not reproduce |
| `pg_ctl start -l` to the postgres-owned log | **started** — fault 5 (log on `/workspace`, unwritable and unchownable) does not reproduce |
| `CREATE EXTENSION vector; SELECT extversion` | **pgvector 0.8.6** |

The last row is the brief's "record both engine versions as engine facts from
the image, not from apt": 1.19.1 from the qdrant binary and 0.8.6 from the
running server's own `pg_extension`, neither read from a package index.

Both versions are the pins the local compose files run, which is the property
that makes a pod row and a laptop row comparable at all.

## Observed, not done

- **`characterize` writes an absolute path into `build_info.json`**:
  `requirements_file.path` is `os.path.abspath(requirements_path)`, which runs
  through the developer's home directory. It does not reach the tracked tree
  today because `runs/` is gitignored, so the new scan does not fire on it —
  but it is the same class of thing 014 removed, it is generated at run time so
  no redaction pass can reach it, and `interpreter()` three files away
  deliberately omits `sys.executable` for exactly this reason. A fixture's
  `build_info.json` that ever does get committed would carry it. Not changed:
  no brief asks, and it is a published-artifact schema change.
- **The identifier scan reads tracked files, not the diff.** It will not catch
  an identifier in a file that is staged but not committed, or in a commit
  message. Both are plausible routes for the same leak. A pre-commit hook is
  the natural home and is not in this brief.
- **`docs/POD.md` is still stale on `volume: none`**, carried from 016's report
  and untouched for the same reason: `docs/` is read-only unless a brief names
  the file and the change, and this brief names `VERIFY.md` and `INTAKE.md`.
  017 adds a second staleness — the image is now a digest from a lock file, and
  POD.md does not mention it.
- **The restart between runs is `docker restart` or an explicit command, and
  the pod path has neither by default.** On a pod the engines are native
  processes, not containers, so `restart_engine` will report
  `not restarted: no engine_restart_command and no known container` unless the
  session spec sets one. That is honest and recorded per run, but it means the
  first pod spread will be measured across runs that shared a warm process
  unless `engine_restart_command` is set. The session spec for the next matched
  run should set it; I have not, because that is a session file and the brief
  did not name one.
- **`ramp_to_ceiling`'s ladder tops out at concurrency 128.** If neither limit
  is hit the result says so in `stopped_because` — "a floor on the ceiling, not
  the ceiling" — rather than reporting the top rung as the answer. Nothing
  raises the ladder automatically.
- **The ceiling ran at 20 s per rung.** Long enough to see degradation on smoke,
  almost certainly too short for arxiv-150k, where the first rung would still be
  paging. The step length is a parameter and has no measured basis yet.
- **The `qps_max` caveat is a string carried in the artifact.** Nothing enforces
  that a reader of `report.json` sees it, and nothing stops a future verdict
  from reading `verify.json:qps_max`. The test asserts the current code does
  not; a guard like the `platform.node()` AST check would assert that no future
  code does.

## Repo now contains

New:

    docker/pod/Dockerfile                     the pre-baked image, pinned throughout
    docker/pod/IMAGE.lock                     the digest; NOT YET BUILT, and says so
    .github/workflows/pod-image.yml           build, push by digest, fail on a stale lock
    oneground/pod/image.py                    reads the lock; refuses to substitute a tag
    oneground/pod/test_image.py               8 tests, mostly about the refusal
    oneground/embed/test_truncation.py        11 tests, stub tokenizer, known counts

Changed:

    oneground/environment.py                  machine_identifiers, scan_text,
                                              tracked_files, identifier_findings
    oneground/test_environment.py             5 tests: the tree, the floor, the
                                              injected forms, the redacted forms
    oneground/embed/__init__.py               count_truncated + TRUNCATION_ADVICE
    oneground/characterize.py                 counts before embedding; warns;
                                              build_info gains max_seq_length,
                                              truncated_count, truncation
    oneground/verify/__init__.py              runs: N; restart_engine; p95_spread;
                                              measure_ceiling; image by digest
    oneground/verify/load.py                  ramp_to_ceiling + QPS_MAX_CAVEAT
    oneground/report/verdict.py               the three-way latency rule
    oneground/report/__init__.py              qps_max_lines; _prices_postdate_the_run;
                                              price_table_rejected
    oneground/report/test_verdict.py          9 tests: the spread rule, the ceiling
                                              kept out of the sustain verdict
    oneground/report/test_end_to_end.py       4 tests: the price-table date rule
    oneground/pod/cli.py                      setup script detects the baked venv
    corpora/run_verify_pod.sh                 marker detection; skips apt + qdrant
    corpora/run_fixture_build.sh              says which venv it got
    docs/VERIFY.md                            `runs: N` and the three-way rule
    docs/INTAKE.md                            one record is one vector; bring chunks
    tasks/016-decision-log.txt                two developer paths redacted

On disk and named by this report wherever a number came from one, but **not
tracked** — `.gitignore:62` keeps the working in `archive/private-history` and
ships the briefs and reports only:

    tasks/scratch/017-ceiling-and-spread.yaml     the local runs:3 + ceiling run
    tasks/scratch/017-truncation-end-to-end.py    the real-tokenizer check
    tasks/scratch/017-image-mechanism.Dockerfile  the image's install path, stripped base

## Blocked on developer

**1. GHCR packages must be public for the repo.** After the first successful
push of `.github/workflows/pod-image.yml` to `main`, the package appears at
`https://github.com/users/shamiksaharcciit-oss/packages/container/package/oneground-pod`.
The exact setting:

> Package settings → **Danger Zone** → **Change package visibility** → **Public**
> → confirm by typing the package name.

And, so the workflow keeps working without a PAT:

> Package settings → **Manage Actions access** → **Add Repository** →
> `shamiksaharcciit-oss/oneground` → role **Write**.

Until it is public, a pod pulling the image needs registry credentials, which
a session does not have.

**2. The order the smoke session has to happen in.** The brief's step 1 asks
for a before/after setup-time measurement, and the "after" half cannot be
measured until the image exists. The sequence:

1. Merge or push `task-017` so `pod-image.yml` runs on `main`.
2. Take the digest from the job summary, put it in `docker/pod/IMAGE.lock`,
   commit. (The workflow fails the *next* push if these disagree, so this
   cannot be forgotten silently.)
3. Make the package public — item 1 above.
4. **Then** the smoke session `y`, which is when the "after" number exists.

The "before" number can be taken from any earlier session's log — the
RUNNING-to-`run started` interval — or measured in the same session by
running once on the fallback image first. I have not assumed which you prefer.

**3. The smoke session itself needs one `y`.** It is step 1's measurement and
nothing else; the arXiv matched session is a later `y` and the brief excludes
it. I will tell you when everything above is in place — as of this report,
items 1 and 2 are still outstanding, so the `y` is not yet useful.
