# Report: 016-stackexchange-fixture

**Status: steps 1–4 complete. Step 5 (the build) ran once and was lost** —
killed at its cap 21 minutes from the finish, with no network volume to
survive on. Steps 5–8 still have no artifacts; step 9 (`docs/POD.md`) is done.
The three fixes that make the retry survivable are in (016g) and tested.

Two commits. `e29b622` built steps 1–4 and reported a planned fixture matching
at 1.00. This revision, after review, makes two changes the reviewer asked for:

1. **Only `built` or `verified` fixtures are matchable as analogies.** The
   finding `e29b622` reported is now fixed rather than only named.
2. **The source is streamed, never stored.** The 59 shards are read through the
   reservoir over the network; the build writes only the sample, and the 36 GiB
   of scratch disk it used to need is gone.

A third revision followed when `up` was refused by the region itself:

3. **`volume: none`.** EU-RO-1, where `vecbench` lives, offered only an
   over-cap B200 and an AMD card our CUDA build cannot use. A session that
   needs no volume now picks its datacenter by GPU availability instead of
   inheriting the volume's region.

And a fourth when the first `up` created a pod it could not talk to:

4. **Wait for sshd.** Session 20260911-200558 (pod `x514af1cflnw6m`) reached
   RUNNING, then its first real command hung for 60 s and died having printed
   only the known-hosts line. RUNNING is the container's state, not sshd's.

And a fifth when the pod could not be created at all:

5. **Fall through on no-capacity.** Three creates refused in a row — EU-CZ-1
   RTX 4090 twice, EU-RO-1 RTX PRO 4500 once, all Low stock. Each ended the
   session and made a human retype `y` for a machine they had already agreed
   to pay for.

Everything below covers all five. Headings marked **(016b)** are the second
revision, **(016c)** the third, **(016d)** the fourth, **(016e)** the fifth.

## Repo state expected vs found

| Expected on resuming | Found |
|---|---|
| 014d outstanding — "add `merge_history.py`, which is not in the commit" | **Already done, and the premise is wrong.** 014d is committed as `444c250` with its report. `merge_history.py` is in the commit and always was; run #5's cause was 014c's push checking the `calibration` branch *into the working tree*, which deleted the script from disk between checkout and invocation. The 014d report states this at its head. Nothing was added this session. |
| a referenced-path test to be written | **already shipped** as `.github/scripts/test_referenced_paths.py` in `444c250` — it asserts every path `calibration.yml`, `pages.yml` and `record-calibration/action.yml` name, that every trigger filter still matches a tracked file, and the structural invariant that the push never checks the target branch out. |
| 016 stopped somewhere mid-flight | uncommitted work in the tree covering brief steps 1–4: source pinned, spec written, builder made field-map driven, pod session written. Step 3's regression gate had been written (`tasks/scratch/016-smoke-regression.py`) but there was no record of it ever having been run. |

Per CLAUDE.md rule 1 the correction sits at the top rather than buried. I did
not stop, because the 014d work was already complete and correct — there was
nothing to build, only to verify — and 016's remaining work is unchanged by it.

## What was done

### 014d — verified, not rebuilt

Re-ran the suite the commit claims: `44 passed` in `.github/scripts`, matching
its report. The one unpushed commit on `main` is `444c250`; `origin/main` is
`1537ff5`. No code was changed.

### 016 step 3 — the regression gate, and what it actually measured

The gate rebuilds `arxiv-smoke` from a regenerated synthetic source and
compares receipts against the committed `MANIFEST.sha256`. It **crashed**:

    Batches:  19%|#8   | 3/16 [03:16<14:40, 67.70s/it]
    CalledProcessError: returned non-zero exit status 3221225477

`3221225477` is `0xC0000005`, an access violation, inside CPU embedding. That
is not a byte-identity failure and it is not a diff — the run never reached the
comparison. Decomposing it rather than re-running it:

**The layer 016 changed is verified byte-identical.** `sample.jsonl.zst` and
`query_ids.json` are written *before* embedding, so the crashed run had already
produced both. Both match the committed manifest exactly:

| artifact | committed | rebuilt | |
|---|---|---|---|
| `sample.jsonl.zst` | `b6383e22…4c6c` | `b6383e22…4c6c` | identical |
| `query_ids.json` | `0081604b…b8e2` | `0081604b…b8e2` | identical |

That is the whole sampling path: `sample_for_spec` dispatch, `field_map`, and
`split_queries(cat_field=…)` — the part of the builder task 016 rewrote.

**The layer that crashed is one 016 did not touch.**
`oneground/embed/__init__.py`, which defines `embed` and `load_model`, is
unmodified (`git status`). The crash came during *base* embedding, before the
one 016-changed line in that block (`queries = embed(model, [r[fm["title"]] …])`)
had executed. Its input is the records in the byte-identical
`sample.jsonl.zst`. Same code, same input.

**The cause is the machine, measured.** `\Memory\Available MBytes` is **748 MB**
of 7.56 GB total, with committed bytes at 25.6 GB against a 31.3 GB limit — the
box is paging. bge-base at `batch_size: 128` on CPU does not fit. `batch_size`
was **not** lowered: it is a spec value, rule 3 forbids changing one to make a
check pass, and padding length varies with batch composition, so a smaller batch
would not have produced comparable bytes anyway.

The gate is therefore **verified for the sampling layer and couldn't-check
beyond it** on this machine. It is not reported as passed.

### 016 step 3 — pinning the other changed layer without an embedding

The gate's blocked half covers `characterize()`, the second place 016 reads the
field map. Two tests now pin that invariant directly, in
`oneground/sample/test_fields.py`:

- `test_declaring_arxivs_own_field_map_changes_no_measure_synthetic` — a spec
  declaring arXiv's own names and cutoff must characterize *identically* to one
  declaring neither: all five measures and the centroid array.
- `test_a_declared_cutoff_actually_moves_the_drift_split_synthetic` — the
  negative control, so the first cannot pass for the wrong reason.

The synthetic corpus uses **three** date tiers, not two. The first draft used
two and the control died with `ZeroDivisionError` inside `recall` rather than
failing its assertion: with a cutoff past both tiers the "after" half is empty,
which is not a different measurement. Three tiers let the cutoff move between
them with both halves populated.

### The negative control, and a false pass it produced first

`tasks/scratch/016-negative-control.py` restores pre-016 behaviour by force and
re-runs both tests. Its **first run reported both passing** — a false pass. The
cause is worth recording:

    from oneground.fixture import build      # this is the *function*, not the module

`oneground/fixture/__init__.py` re-exports `build.build` under the submodule's
own name, so `build.drift_cutoff = …` set an attribute on a function object and
changed nothing. The control now reaches the module through
`sys.modules["oneground.fixture.build"]` and **asserts the patch took** before
it reports anything. With that fixed it behaves as required:

    passed               test_declaring_arxivs_own_field_map_changes_no_measure_synthetic
    FAILED (as it must)  test_a_declared_cutoff_actually_moves_the_drift_split_synthetic
        drift_cutoff was ignored

### The thing worth reading first: a planned fixture is a live analogy

Landing the spec turned the full suite red, and the failure is not cosmetic.

    FAILED oneground/test_analogy.py::
        test_a_ticket_queue_gets_no_analogy_from_a_papers_fixture_real_specs

Chasing it down produced the finding of this session. `analogy.load_fixture_analogies()`
collects **every** spec that declares an `analogy:` block and does **not** look
at `fixture.status`. Brief step 2 requires both an `analogy:` block *and*
`status: planned`, so the moment the spec exists:

    qa corpus -> stackexchange-150k   score 1.0
    why: nearest of 2 fixture(s) by declared character, scoring 1.00
         (matched on corpus_type, text_length, topics_trend, time_ordered,
          dimension, model_family)

    arxiv-150k           status=verified
    stackexchange-150k   status=planned

A user with a Q&A corpus is now handed a **perfect-scoring** analogy to a
fixture whose every measured value is `TO_BE_FILLED`. Tier 2's whole promise is
that an analogy is backed by published numbers; here there are none.

This resolves itself at **step 5** — the build sets `status: built` and fills
the values, and then the 1.0 match is exactly what the analogy block is for. In
`e29b622` it was named rather than fixed, because whether a `planned` fixture
should be matchable at all is a product decision.

**(016b) The decision came back: it should not be.** `load_fixture_analogies`
now skips any fixture whose `fixture.status` is not in
`MATCHABLE_STATUS = ("built", "verified")`. The status is read from the spec,
not inferred from whether artifacts are on disk, so a fresh clone with no
artifacts still offers arxiv-150k's published values as the analogy they are.

Measured after the change:

| corpus | analogy | score |
|---|---|---|
| `qa`, short | **none** — and stackexchange-150k is not even named as nearest | 0.33 vs the 0.70 floor |
| `papers`, medium | **arxiv-150k** | 1.00 |
| matchable set | `[('arxiv-150k', 'verified')]` | — |

Four tests pin it, and all four fail when `MATCHABLE_STATUS` is widened to
include `planned`:

    FAILED (as it must)  test_a_planned_fixture_is_not_matchable_synthetic
    FAILED (as it must)  test_only_built_and_verified_are_matchable_synthetic
    FAILED (as it must)  test_a_planned_fixture_cannot_be_the_nearest_either_synthetic
    FAILED (as it must)  test_the_planned_stackexchange_spec_is_not_matchable_real_specs

The third is worth naming: a planned fixture must not surface even as "the
nearest" in a refusal message, because that still reads as a recommendation to
anyone skimming. The real-specs test also asserts the stackexchange spec is on
disk and *does* declare a `qa` analogy, so it is excluded for its status rather
than because it was quietly missed.

Two further notes. `arxiv-smoke` is also `planned` and `glove-100-angular` is
`built`, but neither declares an `analogy:` block, so the filter changes nothing
for them. And the existing synthetic tests were unaffected because their helper
already wrote `status: built` — which is why the filter did not silently gut the
suite.

**What I did change** is the test, and only its stale premise. Its docstring
read "with only arxiv-150k available", which task 016 makes false. The verdict
it guards is untouched and still passes: a ticket queue still gets **no**
analogy, because 0.47 is below the 0.70 floor. What moved is which fixture is
*nearest* — now stackexchange-150k rather than arxiv-150k, which is correct, as
Q&A is genuinely nearer to a ticket queue than paper abstracts are. The
rewritten test no longer hardcodes the nearest fixture, and asserts more than
it did: the floor appears in the explanation, the nearest differs on
`corpus_type`, and the fixture named is a shipped one.

No threshold was touched. `MIN_SCORE` is still 0.70. The negative control
confirms the test is still a gate:

    FAILED (as it must) with floor lowered to 0.10: stackexchange-150k

### (016b) The source is streamed, and nothing is stored

`e29b622` fetched all 59 shards to the volume first — 34 GiB, plus 2 GiB
headroom, with a disk preflight that refused before the first byte. That whole
step is gone.

**Why it is possible at all.** Parquet is a random-access format: the footer at
the end of each file names the row groups and column chunks, so a reader can
fetch just what it wants without the bytes in between. I verified this against
the real pinned revision before building anything on it — the footer of shard
`00000` reads `PAR1` over a range request, with no local copy:

    size   : 409,251,174 bytes (0.38 GiB)
    etag   : 62633ca46fed061b72df8ee94ec80db25ce8cbd50fa1143ad2567b602b526249
    parquet footer magic at EOF: b'PAR1'   seekable remote file: True

Then the full path, on real rows from the real shard, through the shipped
cleaner — 8,192 rows scanned, 1,404 eligible, **no local copy**:

    Id           : 6
    Tags (raw)   : ['html', 'css', 'internet-explorer-7']
    CreationDate : 2008-07-31   year 2008
    Licence      : CC BY-SA 4.0

That probe caught a real problem before it could bite: **`Tags` is a list
column**, recorded in row-group metadata as `Tags.array`. The reader asks for
`Tags` and pyarrow resolves it correctly, but it was worth proving rather than
assuming, since a silently-empty `categories` field would have produced a
fixture whose hot-category query split was meaningless.

**"Nothing is stored" is measured, not asserted.** The unit test for this uses
a stubbed filesystem, so it proves the reader's plumbing and not the library's
behaviour. So I checked the real one: with `HF_HOME` and every temp-dir
variable pointed at empty directories, reading **262,144 rows including the
`Body` column** from the real pinned shard grew both by **0 bytes**.

    baseline   HF_HOME 6,007  spool 0
    read       262,144 rows including Body
    after      HF_HOME 6,007  spool 0
    growth during the read: 0 bytes

The 6,007-byte baseline is `.agent_harnesses.json`, which `huggingface_hub`
writes on import before any read — not shard content. `fsspec` keeps its
read-ahead blocks in memory, and nothing touches the disk.

**What it does not buy.** I measured per-column bytes rather than guessing:
`Body` is 88% of the file, so requesting only the 7 needed columns of 16 saves
**6.5%** — 364.9 MB of 390.2 MB per shard. The transfer is ~32 GB, not a small
fraction of 34 GB. The win here is disk and a deleted step, not bandwidth.

**The receipt cost, stated rather than glossed.** This is the one real loss and
it is recorded in the spec as `source.digest_scope`, not buried here. A reader
that fetches only some column chunks never reads a shard's bytes end to end, so
it cannot hash them. Instead `verify_source` runs **before any content is
read** and refuses the build unless the pinned revision still resolves and every
pinned sha256 still matches the one the Hub reports. Conveniently, an LFS
pointer's oid *is* the file's sha256 — the etag above matches the manifest's
first line exactly — which is how the pins were written in the first place.

So it catches a moved or deleted revision, and a shard added, removed, renamed
or changed. It does **not** catch a corrupted transfer of the bytes actually
read. arXiv's snapshot is one file read end to end and is still hashed
directly, so it has no such gap. The difference is a property of a 34 GB
sharded source, not a shortcut: closing it would mean transferring the whole
dump and storing it, which is the thing being removed.

`source.snapshot_sha256` keeps its old definition — the manifest digest over
the sorted `<sha256>  <name>` lines — and both paths now compute it through one
shared `receipts.manifest_digest`, so a local rebuild and a streamed one cannot
disagree about their own digest. A test asserts they agree.

**One pass, not two.** The brief's revision allowed two streaming passes if
stratification needed counts first. It does not: the existing per-year
reservoir counts eligible posts *as it goes*, so the proportional quota and its
largest-remainder rounding are computed after a single pass, identically to
arxiv-150k's. A second pass would re-read the `Body` column — 88% of the bytes
— for nothing.

**What moved.**

| | |
|---|---|
| `corpora/fetch_stackexchange.py` | **deleted** — its whole job was storing the shards |
| `corpora/run_stackexchange_build.sh` | **deleted** — it existed only to run the fetch before the build |
| `sessions/stackexchange-build.yaml` | `run:` is now the generic `run_fixture_build.sh`; `SOURCE` is gone |
| `--source` / `SOURCE` | now optional everywhere — the spec names its own source |

The local-directory path is deliberately kept, for tests and an offline
rebuild, and a test asserts it never consults the Hub.

### (016c) `volume: none` — the datacenter is chosen, not derived

`up` refused: EU-RO-1, where the `vecbench` volume lives, was offering only a
B200 at $5.98–6.79/hr (over cap) and an MI300X (AMD, which our cu130 torch
cannot use). Pinning a session to a volume also pins it to that region's stock
— and this session needs no volume at all, since the source streams and both
outputs come back as tarballs.

`volume:` stays **required**, and now takes `none` (or an explicit YAML null).
The two placement rules are separate and both tested:

| `volume:` | datacenter | `volume_mount_path` |
|---|---|---|
| a name | **derived from the volume** — unchanged | the mount |
| `none` | **chosen by GPU availability** | a directory on the container disk |

The choosing rule, precisely: **the cheapest listed datacenter offering the
first available GPU in the list**. GPU preference order is honoured *first* — a
cheaper region for a card the session did not ask for is a different answer,
not a better one — and only then does price choose between the regions offering
it. Ties break on datacenter id so two `plan` runs cannot silently move the pod.

**One honest wrinkle, recorded because it changes what "cheapest" means.**
`securePrice` — the number this project confirms against, per task 006b — is
reported **globally**, not per datacenter. Only the `lowestPrice` floor varies
by region. So "cheapest datacenter" can only be decided on the floor, while the
confirmed rate is identical everywhere. The ranking is still written
worst-case-first so it stays correct if that ever changes, and `plan` says so
in as many words rather than implying a saving that is not there.

**One query, not 33.** `lowestPrice` takes a `dataCenterId`, so the whole
price matrix is aliased into a single GraphQL call — measured at 5.8 s for 33
listed datacenters, against 33 sequential round trips. A test asserts the call
count is 1.

Unlisted datacenters are excluded from the *choice* but the volume-derived path
never consults the list at all, deliberately: a session pinned to a volume must
keep working in a region that has stopped taking new pods.

`deploy_spec` **omits** `networkVolumeId` and `volumeMountPath` entirely rather
than sending nulls — a mount path with no volume id describes a mount that does
not exist. And `_sync_and_start` now `mkdir -p`s the mount path before the first
scp: with a volume it already exists, without one nothing had created it, and
the bundle upload would have failed after the pod was already billing.

**Live, read-only, nothing created:**

    volume     : none   (nothing outlives the pod)
    datacenter : US-WA-1   (chosen by GPU availability, 33 searched)
                 cheapest of 1 offering RTX 6000 Ada, at $0.84/hr
    gpu        : RTX 6000 Ada   [NVIDIA RTX 6000 Ada Generation]
                 stock Low
    disk       : 60 GB container disk; /workspace is on it, not a volume
    price      : $0.74 - $0.84/hr   (live on-demand range, SECURE, US-WA-1)
                 confirmed at the TOP of the range, $0.84/hr
    caps       : max_hours 1.5, max_usd $2.50, max_concurrent 1
    COST CAP   : 1.5 h x up to $0.84/hr = up to $1.26   within max_usd
    considered : RTX PRO 4500=unavailable  RTX PRO 6000=unavailable
                 RTX 6000 Ada=$0.74-$0.84/Low  RTX 4090=unavailable  (in US-WA-1)

    datacenters offering RTX 6000 Ada, cheapest first:
      US-WA-1     $0.74 - $0.84/hr   stock Low   <- chosen

Worth noting how live this is: a probe twenty minutes earlier found RTX 4090 in
EU-CZ-1 and **no** listed datacenter offering RTX 6000 Ada. Stock moves between
runs, which is the argument for resolving it at `plan` time rather than writing
a region into the spec.

The session is now `volume: none` with `disk_gb: 60` — sized for the venv, the
bge-base weights, the artifacts (`vectors.npy` is ~460 MB) and both tarballs.
The 34 GB of shards are *not* on it; they are streamed. The disk dies with the
pod, so nothing is left behind to pay for.

### (016d) RUNNING is the container's state, not sshd's

The first `up` got as far as a live pod. I read its record rather than working
from the summary, and it is worth quoting, because it is both the bug and the
evidence problem in four lines:

    pod_id            x514af1cflnw6m
    volume            None
    data_center_id    EU-CZ-1          gpu RTX 4090      $0.74/hr
    state             terminated
    finished_because  failed-after-create
    last_error        timed out after 60s: ssh -p 40134
                        stderr: Warning: Permanently added
                        '[213.192.2.69]:40134' (ED25519) to the list of
                        known hosts.

Two things that summary does not say. **016c worked end to end** — a
volume-less session resolved EU-CZ-1, created an RTX 4090 at $0.74/hr and
reached RUNNING, which is exactly what the placement change was for.

And the command that hung was `ssh`, not `scp`: it is the `mkdir -p
/workspace` that 016c itself added, the first thing in `_sync_and_start`. So
the very first command over SSH was the one that met the race. The pod billed
for all 60 s of it and the session was torn down over something that usually
resolves in seconds.

Note what `last_error` could tell me and what it could not: the known-hosts
line proves ssh got as far as the host key, and `ssh -p 40134` is the *entire*
record of what was run. That is the second half of this fix.

**The fix is a probe that is allowed to fail.** Before anything that matters,
`ssh … true` is retried with backoff up to **180 s**. `true` is the smallest
thing that proves the whole path — endpoint, port mapping, key, and a shell —
and it is cheap enough to throw away as many times as needed.

Each attempt is bounded by **20 s**, not the session timeout: a probe that
hangs for 60 s teaches nothing a 20 s one does not, and it spends the budget
the retry loop exists to have. Backoff is `2, 3, 5, 8, 12, 15` seconds —
growing, then flat, because this almost always resolves in the first few
seconds and after that there is no point hammering it. The last attempt is
clamped to whatever is left, so the wait never overruns its deadline. Every
attempt is logged:

    waiting for sshd on 10.0.0.1:44089 ...
      sshd not ready yet (attempt 1, 0s elapsed): Connection refused
      retrying in 2s
      ...
      ssh ready after 4 attempt(s), 10s

**The second half is the record.** The timeout path in `_run` raised
`SshError` with **no** `command`, no streams and no timeout flag — so
20260911-200558's record could say only that something timed out after 60 s,
with the port number as the entire evidence. It now carries the full argv, the
tailed streams and `timed_out`, and `up` writes them to the session file as
`ssh_error` (readiness) or `last_ssh` (anything later). The exit-code path
recorded `" ".join(cmd[:3])` — `ssh -p 44089` — and now records the whole
command too. A successful wait is recorded as well, as `ssh_ready`, because how
long sshd actually took is the number that says whether 180 s is the right
window.

A pod that never comes up is terminated with reason `ssh-never-ready`, distinct
from `failed-after-create`: nothing ran, so there is no remote state to reason
about — only a pod that is billing and cannot be reached.

**Tested against a remote that refuses the first N connections.** `RefusingSsh`
overrides `_run`, not `run`, so the real argv construction, the real retry
loop, the real backoff and the real deadline all execute; a fake clock makes
the three-minute window cost nothing. Both failure shapes are covered —
connection *refused*, and the connection *hanging*, which is what
20260911-200558 actually saw and which a refusal-only stub would have missed.

**Two things this turned up that were not in the brief.**

The readiness wait is the one post-create step that does real network work
before anything under test happens, so inserting it **hung two existing
tests**: their harness drives `up` to a later step with a pod at `10.0.0.1`
that does not exist, and my probe dutifully retried it for the full window with
real sleeps. It is now behind a `cli._wait_ssh_ready` seam and stubbed by those
harnesses, the way `_wait_running` already was. Worth saying plainly: the first
version of this change would have added three minutes to every failing session.

And my own first draft of the test monkeypatched `subprocess.run` on the real
module — which patches it for pytest and every other test in the file, not just
the code under test. That is what wedged the suite for 10 minutes before I
caught it. The tests now rebind the `subprocess` *name* inside `sshx`.

### (016e) The confirmation is a ceiling, not a card

Three creates refused for want of capacity, each ending the session. The
authorisation this reuses is worth quoting, because the argument rests on it —
`ask_to_create` prints:

    Create this pod at up to $0.74/hr (range $0.34-$0.74) with a hard cap of
    1.5 hours = up to $1.11? [y/N]

That names a **rate** and a total. It names no GPU and no region. So a
candidate at or under the rate already confirmed is inside what was
authorised, and `up` now falls through to it without asking again. A candidate
*above* that rate is not, and is never tried: it is logged as skipped, and the
run ends telling the developer what a second `y` would buy.

**Only one error is retryable, and that is the load-bearing decision here.**
`api.is_no_capacity` matches RunPod's "there are no instances currently
available" and nothing else. Every other failed create may have made a pod
whose id this process never saw — a timeout, a proxy 502, a response that did
not parse — and retrying those could put **two pods behind one `y`**. They
propagate untouched. Matching on the phrase rather than the status code is for
the same reason: a 500 alone does not say whether anything was allocated.

The plan now carries every deployable `(datacenter, GPU)` in fallthrough order
— preference order outer, price inner — instead of only the winner, and
`deploy_spec` takes a candidate so the second attempt is built the same way
the first was. The state record names **the card that exists**, not the one
first chosen, with `planned_gpu` set when they differ; otherwise `status` and
`watch` would report a machine the account never had.

**The GPU list is widened**, as asked: `L4, RTX A5000, RTX A4000, RTX 3090,
A40` after the existing four. All run bge-base fine — the embedding is 152k
short texts at batch 128, roughly 4–6 minutes on the fast cards and about
**10–15 minutes** on these. Against a 1.5 h cap whose long pole is the ~32 GB
streamed read, that does not decide the run: an available slower card beats an
unavailable fast one.

**What the live account actually has, measured.** This is the part worth
knowing before a retry:

    3 GPU types purchasable on SECURE somewhere, of 48 known
      L4        US-MO-2   $0.49/hr  Low
      RTX 4090  EU-CZ-1   $0.74/hr  Low
      B300      US-WA-2   $7.89/hr  Low

So the market is thin, not just EU-RO-1. And it **moves between calls**: three
probes minutes apart saw RTX 4090 alone, then L4 in US-MO-2, then A40 in
CA-MTL-1. That flicker initially looked like a bug in my candidate list — a
card the availability survey found was missing from `deploy_candidates`. It
was not. Resolving both from a **single** price fetch shows them agreeing
exactly:

    raw availability          deploy_candidates (same fetch)
      RTX 4090  EU-CZ-1         1  RTX 4090  EU-CZ-1  $0.74
      A40       CA-MTL-1        2  A40       CA-MTL-1  $0.49

Preference order is honoured (RTX 4090 is 4th in the spec, A40 is 9th) and the
A40 at $0.49 sits under a $0.74 ceiling, so it is a fallthrough target that
needs no second `y`. I would rather record that I chased a phantom for ten
minutes than leave the discrepancy unexplained in the log.

Two negative controls beyond the usual: removing the fallthrough restores the
behaviour that cost three sessions, and removing the ceiling lets one `y` buy a
$2.09/hr card after confirming $0.84. A third makes `is_no_capacity` true for
everything, which is the two-pods-one-`y` regression.

### 016 step 4 — the pod session resolves

`oneground pod plan sessions/stackexchange-build.yaml` resolves live and
read-only. Nothing was created.

## Measurements

All on `.venv\Scripts\python.exe` (Python 3.12, pinned environment).

| Measurement | How obtained | Result |
|---|---|---|
| Workflow-script suite (014d) | `python -m pytest -q .github/scripts` | **44 passed** in 174.3 s |
| 016 unit tests | `python -m pytest -q oneground/sample/test_fields.py oneground/sample/test_stackexchange.py` | **31 passed** in 1.3 s |
| Full suite, before the analogy test was corrected | `python -m pytest -q` | 514 passed, **1 failed**, 1 skipped in 335.0 s |
| Full suite, after (`e29b622`) | `python -m pytest -q` | **515 passed, 1 skipped** in 312.6 s |
| — vs the 014d baseline | 484 passed, 1 skipped | **+31**, all task 016 (14 field-map, 17 stackexchange) |
| **(016b)** Full suite, after both changes | `python -m pytest -q` | **533 passed, 1 skipped** in 289.8 s |
| — vs `e29b622` | 515 passed, 1 skipped | **+18** (4 analogy status, 14 streamed source) |
| **(016b)** Streamed-source tests | `python -m pytest -q oneground/sample/test_stackexchange.py` | **31 passed** in 17.8 s |
| **(016b)** Analogy tests | `python -m pytest -q oneground/test_analogy.py` | **21 passed** in 5.7 s |
| **(016b)** Byte-identity re-checked after the refactor | smoke rebuild vs the committed manifest | `sample.jsonl.zst` and `query_ids.json` **still identical** |
| `fixture verify` before the build | `python -m oneground.cli fixture verify stackexchange-150k` | clean refusal, `no such fixture directory`, exit 1 — not a crash |
| `sample.jsonl.zst` byte-identity | rebuilt vs `fixtures/arxiv-smoke/MANIFEST.sha256` | **identical** |
| `query_ids.json` byte-identity | same | **identical** |
| Smoke rebuild, embedding onward | `tasks/scratch/016-smoke-regression.py` | **crashed**, `0xC0000005`, batch 3/16 |
| Free physical memory | `Get-Counter '\Memory\Available MBytes'` | **748 MB** of 7,924,988 KB total |
| Commit pressure | `\Memory\Committed Bytes` vs `\Memory\Commit Limit` | 25,622 MB / 31,291 MB |
| Peak reservoir footprint | `tasks/scratch/016-reservoir-footprint.py`, tracemalloc, N=20,000 | 871 B/record → **0.78 GiB** for 960,000 held records |
| Shard manifest | `sessions/stackexchange-shards.sha256` | **59** digests, no duplicates, all 64 hex — matches `source.shards: 59` |
| Pods on the account | `python -m oneground.pod ls` | **0** |
| Unpushed commits | `git log origin/main..main` | **1** (`444c250`) |
| Analogy for a `qa` corpus, **before** the filter | `A.choose({corpus_type: qa, …})` against the shipped specs | **stackexchange-150k, score 1.00**, `status: planned` |
| Analogy for a `qa` corpus, **after** | same | **none**; nearest arxiv-150k at 0.33 vs the 0.70 floor |
| Analogy for `papers`, after | same, `corpus_type: papers` | **arxiv-150k, 1.00** — unchanged |
| Matchable fixtures, after | `A.load_fixture_analogies()` | `[('arxiv-150k', 'verified')]` |
| Shard 00000 size | `get_hf_file_metadata` at the pinned revision | 409,251,174 B (0.38 GiB) |
| Remote random access | footer read over a range request | `PAR1` — seekable, no local copy |
| Column bytes per shard | parquet row-group metadata, shard 00000 | 390.2 MB all 16 columns; **364.9 MB** the 7 needed (**93.5%**) |
| — `Body` alone | same | 343.5 MB (88% of the file) |
| Streamed read, real rows | `tasks/scratch/016b-stream-feasibility.py` | 8,192 rows, 1,404 eligible, no local copy |
| Streamed sample == local sample | `test_a_streamed_dump_gives_the_same_sample_as_the_local_one` | **identical record lists** |
| Disk needed by the build | was 34 GiB shards + 2 GiB headroom | **0** for the source; only the sample is written |
| Real-library spooling | `tasks/scratch/016b-no-disk-probe2.py`, 262,144 rows incl. `Body`, empty `HF_HOME` + temp dirs | **0 bytes** written |
| **(016c)** Datacenters visible | `dataCenters` GraphQL query | 50 total, **33 listed** |
| **(016c)** Cross-datacenter price matrix | one aliased GraphQL call, 33 datacenters | **5.8 s**, 3,328-char query, **1** round trip |
| **(016c)** Live resolution, `volume: none` | `pod plan sessions/stackexchange-build.yaml` | **US-WA-1**, RTX 6000 Ada, $0.74–$0.84/hr |
| **(016c)** Cost cap on that plan | 1.5 h x $0.84 | **$1.26** vs `max_usd` $2.50 |
| **(016c)** Stock volatility | the same probe 20 min apart | RTX 4090 in EU-CZ-1, then unavailable; RTX 6000 Ada nowhere, then US-WA-1 |
| **(016c)** Pod tests | `python -m pytest -q oneground/pod/test_pod.py` | **130 passed, 1 skipped** (+22) |
| **(016d)** Readiness window | `sshx.READY_TIMEOUT_SECONDS` | **180 s**, per-attempt probe **20 s**, backoff `2,3,5,8,12,15` |
| **(016d)** Observed failure | session record `20260911-200558` | first SSH command (`mkdir -p`, added by 016c) hung **60 s**; the whole recorded evidence was `ssh -p 40134` plus the known-hosts line |
| **(016d)** That pod, placed by 016c | same record | EU-CZ-1, RTX 4090, **$0.74/hr** true rate, reached RUNNING |
| **(016d)** Pods left behind | `python -m oneground.pod ls` | **0 on the account** |
| **(016e)** Creates refused before this change | developer report | **3 in a row** — EU-CZ-1 RTX 4090 x2, EU-RO-1 RTX PRO 4500 x1, all Low stock |
| **(016e)** Purchasable on SECURE anywhere | `tasks/scratch/016e-whats-available.py`, 33 listed datacenters | **3 GPU types of 48** — L4 $0.49 (US-MO-2), RTX 4090 $0.74 (EU-CZ-1), B300 $7.89 (US-WA-2) |
| **(016e)** Stock flicker | three probes, minutes apart | RTX 4090 only -> +L4/US-MO-2 -> +A40/CA-MTL-1 |
| **(016e)** Candidates from one fetch | `tasks/scratch/016e-same-call.py` | availability and `deploy_candidates` agree exactly; 2 candidates, A40 at $0.49 under a $0.74 ceiling |
| **(016e)** Pod tests | `python -m pytest -q oneground/pod/test_pod.py` | **171 passed, 1 skipped**, 15.2 s |
| **(016e)** Full suite | `python -m pytest -q` | **596 passed, 1 skipped** in 260.8 s (+16) |
| **(016e)** GraphQL blips | two `plan` runs in a row | HTTP 500 twice, then fine; the aliased query re-probed OK at every size 2..33, so transient server-side |
| **(016f)** Session | 20260911-220320, pod `demdanrfl4y0gb` | A40 / CA-MTL-1, $0.49/hr true, `volume: none`, **fallback candidate** (planned RTX 4090) |
| **(016f)** ssh-ready | session record `ssh_ready` | **1.5 s, 1 attempt** |
| **(016f)** Streamed pass | build log, 22:08:27 -> 22:55:23 | **46m 56s**, 59 shards, ~34.06 GB, **~12.1 MB/s**, 47.7 s/shard |
| **(016f)** Eligible questions | same pass, counted exactly | **20,388,803** of 58,329,355 posts (**35.0%**), 16 years |
| **(016f)** Sample | build log | 150,000 base + 2,000 queries, **199 hot categories** |
| **(016f)** Embed on A40 | build log, 22:55:45 -> 23:02:00 | **6m 14s / 152,000 texts** (~406 texts/s) |
| **(016f)** Reference configs | build log | single-node HNSW 3m 06s; semantic-sharded 2m 32s |
| **(016f)** UMAP projection | build log | 4m 24s |
| **(016f)** Unfinished tail | 23:13:10 -> cap | **20m 21s** in `fixture verify` + ground-view + tar |
| **(016f)** Outcome | `finished_because` | **cap**; neither tarball present; **nothing recovered**; $0.73 |
| **(016f)** Pods left | `oneground pod ls` after terminate | **0** |
| **(016g)** Receipts byte-identity after the split | smoke rebuild vs the committed manifest | all **6** receipts identical |
| **(016g)** Projection byte-identity as its own step | `fixture project` on the same build | `adba4173…` — **identical** |
| **(016g)** Cap-kill mid-projection | `tasks/scratch/016g-capkill-smoke.sh`, shipped runner | **PASS** — receipts tarball 45,253 B and release tarball 6,418,819 B already on disk; `projection.npy` absent |
| **(016g)** New cap arithmetic | 2.0 h x $0.74/hr | **$1.48** against `max_usd` 2.50 |
| **(016g)** Verify tests | `python -m pytest -q oneground/fixture/test_verify.py` | **47 passed** |
| **(016g)** Full suite | `python -m pytest -q` | **608 passed, 1 skipped** in 191.2 s (+12) |
| **(016d)** Baseline note | `git log` | task 015 merged into `main` at 21:58, **after** 016c's commit at 21:44, so the 555 and 580 figures are not the same baseline — hence the collect-only delta above |
| **(016d)** Pod tests | `python -m pytest -q oneground/pod/test_pod.py` | **155 passed, 1 skipped**, 7.7 s (+15 from this change) |
| **(016d)** Suite runtime before the seam | same command | **hung** past 400 s — two harnesses retrying a pod at 10.0.0.1 for the full window |
| **(016d)** Full suite | `python -m pytest -q` | **580 passed, 1 skipped** in 213.3 s |
| — added by this change | `pytest --collect-only -q` at `26fc72e` vs HEAD | 566 -> 581 collected, **+15** |
| **(016c)** Full suite | `python -m pytest -q` | **555 passed, 1 skipped** in 560.7 s |
| — vs `8056afb` | 533 passed, 1 skipped | **+22**, all `volume: none` |

### What `plan` resolved

    volume     : vecbench, id rvoku0jgda, 50 GB
    datacenter : EU-RO-1   (derived from the volume, not the spec)
    gpu        : RTX PRO 4500 [NVIDIA RTX PRO 4500 Blackwell], stock Low
    price      : $0.34 - $0.72/hr live on-demand range, SECURE, EU-RO-1
    COST CAP   : 1.5 h x up to $0.72/hr = up to $1.08   within max_usd 2.50
    considered : RTX PRO 4500=$0.34-$0.72/Low  RTX PRO 6000=unavailable
                 RTX 6000 Ada=unavailable      RTX 4090=$0.34-$0.74/Low
    Nothing was created. This is a dry run.

## Verification

**Verified.**

- 014d's commit does what its report says: 44 workflow-script tests pass.
- The sampling half of the step 3 regression gate: two receipts byte-identical
  to the published manifest, from a rebuild through the new field-map path.
- `characterize()` is unchanged by declaring arXiv's own field map — and the
  test saying so fails against pre-016 behaviour.
- The shard digest manifest is internally consistent and agrees with the spec.
- `plan` resolves read-only, inside both caps, with zero pods on the account.
- The rewritten ticket-queue test still gates: it fails when `MIN_SCORE` is
  lowered, so it is not passing merely because the assertion was loosened.

- **(016b)** Only `built` or `verified` fixtures are offered as analogies, and
  the four tests that say so all fail without the filter.
- **(016b)** A streamed dump yields a record-for-record identical sample to the
  same shards read locally, and the streamed digest equals the on-disk digest.
- **(016b)** The real `HfFileSystem` writes **0 bytes** while reading 262,144
  rows including `Body` — checked against the live Hub, not a stub.
- **(016b)** The sampling layer is still byte-identical after the refactor:
  the smoke rebuild reproduced both pre-embedding receipts exactly.
- **(016c)** Both placement rules, against a stubbed API that dispatches on the
  request body and parses the alias→datacenter mapping out of the real query,
  so a change to the query shape fails the stub rather than slipping past it.
  Two negative controls: a naive "cheapest anything, anywhere" rule breaks
  preference order, the `listed` filter and the cheapest-datacenter choice;
  dropping `offered_on_cloud` re-creates the task 006b trap. All four tests
  fail as they must.
- **(016c)** A volume-less resolve makes **no** volume lookup and **no**
  billable call, and the volume-derived path's payload and rendering are
  unchanged.
- **(016f)** The whole `up` -> `watch` -> fetch -> terminate path worked on a
  real billing pod: the fallthrough deployed the A40, the readiness wait
  returned in 1.5 s, the stall watchdog correctly did not fire on an 11.7 min
  quiet stretch, and the cap terminated the pod and left **0** on the account.
- **(016d)** The readiness wait retries a refusing remote and a *hanging* one,
  logs every attempt, gives up exactly at its deadline and never overruns it,
  probes with a harmless `true`, and records the full command on failure —
  15 tests against a stub that refuses the first N connections. Two negative
  controls: removing the wait and restoring the pre-016d timeout path each
  fail the tests that guard them.

**Failed.** Nothing failed that indicates a defect in the code under test. The
smoke rebuild failed to *complete*, from memory exhaustion on this machine.
**(016b)** On the re-check it was stopped deliberately: it had already written
the two artifacts the comparison needs, and had then spent ~20 minutes in CPU
embedding with the box down to 289 MB available, where its only outcome was the
same `0xC0000005`. The layers past embedding remain couldn't-check, unchanged.

**Couldn't check.**

- **(016f) Every published value of stackexchange-150k.** Crispness, ambiguity,
  skew, the drift pair and both reference recalls were computed on the pod and
  destroyed with it. The spec stays `status: planned`, every value
  `TO_BE_FILLED`, and the changelog records the attempt. Nothing is read off
  the progress log into the spec.
- **(016f) Steps 6, 7 and 8** — simulate, the decision log, the findings, the
  ground-view parquets and `fixture verify --asset`. All need the artifacts.
  There is no decision log to paste because no decision was measured.

- Byte-identity of `vectors.npy`, `queries.npy`, `ground_truth.npy` and
  `characterization.json` for `arxiv-smoke`. The rebuild cannot finish in
  748 MB. The argument that they must match — unmodified code, proven-identical
  input — is an argument, not a measurement, and is not counted as one.
- Byte-identity for **arxiv-150k**, which the brief also asks for. Its
  `vectors.npy` / `queries.npy` / `sample.jsonl.zst` are not in the clone (they
  are the release asset; `../oneground-assets/` does not exist here), and a 150k
  rebuild is a pod job regardless. Nothing was measured for it.
- ~~Whether `vecbench` has the ~36 GiB free the fetch needs.~~ **(016b) Retired
  by the change, not by a measurement.** Nothing is fetched, so the question no
  longer exists.
- **(016b) How long the streamed pass takes on the pod.** It is bound by the
  pod's network throughput to the Hub, which `plan` cannot resolve and which my
  own connection cannot stand in for — the feasibility probe measured ~3 MB/s
  unauthenticated from here, which would be hours, while a datacentre pod is
  typically two orders faster. The transfer volume is the same ~32 GB the old
  fetch would have moved, so this is not a new risk, but it is the part of the
  1.5 h cap with no precedent. If the run hits the cap, `watch` terminates it
  and the report says where the time went.
- **(016b) Whether the Hub serves the pinned revision at build time.**
  `verify_source` checks it before any content is read and refuses cleanly, so
  the failure is cheap — but it is a live dependency the old design converted
  into a one-time fetch.

## Observed, not done

- ~~A `planned` fixture is matchable as an analogy.~~ **(016b) Fixed** — see
  above. Left here so the trail from finding to fix stays readable.
- **(016b) `fixture.status` is now load-bearing in a second place.** It already
  drove what `fixture verify` expects; it now also decides whether a fixture is
  offered as an analogy. Nothing validates that the value is one of
  `planned | built | verified` — `glove-100-angular` even writes it with
  irregular spacing. A typo would silently make a fixture unmatchable rather
  than raise. A one-line validator at spec load would close it. Not done: no
  brief asks for it, and the failure is quiet rather than wrong.
- **(016c) `docs/POD.md` is now partly stale.** It documents `volume:` as
  always naming a volume (line 158), states "the datacenter is never written
  down… derived from the volume's record" (line 171) as the only rule, and
  shows a `plan` output with a volume (lines 189–190). All of that is still
  true for a volume-backed session and incomplete for `volume: none`. Not
  edited: CLAUDE.md makes `docs/` read-only unless a brief names the file and
  the change, and this one named the session schema, not the doc. It wants one
  short section, and I would rather you commissioned it than found it.
- **(016d) The 180 s window is a judgement, not a measurement.** Nobody has
  yet observed how long this pod's sshd actually takes — 20260911-200558 died
  at 60 s without ever succeeding, so the only datum is "more than 60". The
  next run records `ssh_ready` with the real number, and that is what should
  size the window. It is deliberately generous rather than tuned: the cost of
  waiting too long is bounded by `max_hours`, and the cost of waiting too
  little is a wasted create.
- **(016d) `watch` does not probe readiness.** It reconnects to a pod that was
  reachable when `up` left it, so the race this fixes does not arise there. But
  a pod whose sshd restarts mid-run would hit the same wall with no retry.
  Untouched: no brief asks, and I have not seen it happen.
- **(016c) `watch` and `fetch` have not been exercised against a volume-less
  pod.** Nothing in them reads the volume — `fetch` pulls the declared outputs
  over scp and `state` now records `volume: None` — but the only proof is that
  the code paths do not mention it. The first real run is the test. Worth
  knowing because a failed fetch on a volume-less pod loses the artifacts
  outright: there is no volume left holding them.
- **(016c) `disk_gb: 60` is a judgement, not a measurement.** arxiv-150k's
  artifacts plus the venv and the model weights are roughly 3–4 GB, and 60 GB
  is deliberate slack because the container disk is now the only disk. Sizing
  it from a real run is a thing to do after this build, not before it.
- **(016b) `oneground fixture build` can now be called with no `--source`
  against an arXiv spec**, which fails inside `open()` with a less helpful
  message than a check at the top would give. The stackexchange reader refuses
  clearly; the arXiv one does not. Not changed — no brief asks, and the pod
  path always goes through `run_fixture_build.sh`, which sets `FIXTURE`.
- **`oneground/test_analogy.py`'s module docstring says "the two tests named
  `_real_specs`" and there are three.** Pre-existing — `git show HEAD` has the
  same count and the same wording. Not changed; it is not mine and rule 2
  applies.
- **`oneground.fixture.build` the module is shadowed by `build` the function.**
  `oneground/fixture/__init__.py` re-exports `build.build` under the submodule's
  name, so `from oneground.fixture import build` silently yields a function. It
  produced a false pass in my own control before I caught it, and any future
  patch or monkeypatch against that module is exposed to the same trap. Not
  changed: renaming an export is outside this brief and would touch callers.
- The step 3 gate cannot run on the developer's machine while the box sits at
  748 MB free, and nothing in the repo says so. It is a scratch script, not a
  test, so it does not announce its requirements. Worth a note in it, or a
  skip-with-reason if it is ever promoted to a test. Not done.
- `corpora/run_arxiv_150k.sh` is deliberately left in place beside the new
  generic `run_fixture_build.sh`: `sessions/arxiv-build.yaml` names it and three
  task reports invoke it by path.

## Repo now contains

All task 016, on `main`.

| Path | |
|---|---|
| `fixtures/stackexchange-150k.fixture.yaml` | new — the spec, `status: planned`, every value `TO_BE_FILLED` |
| `oneground/sample/fields.py` | new — the canonical five-field map and drift cutoff, defaulting to arXiv's |
| `oneground/sample/stackexchange.py` | new — one-pass per-year-reservoir reader over parquet shards, local or streamed |
| `oneground/sample/test_fields.py` | new — 14 tests, incl. the two call-site tests added this session |
| `oneground/sample/test_stackexchange.py` | new — 31 tests; **(016b)** +14 for the streamed source, stubbed Hub, no network |
| `oneground/sample/__init__.py` | reader dispatch on `source.format` |
| `oneground/sample/arxiv.py` | `split_queries` takes `cat_field` |
| `oneground/fixture/build.py` | field-map driven; **(016b)** `source` optional, digest via the reader's `receipt` |
| `oneground/test_analogy.py` | ticket-queue premise corrected; **(016b)** +4 tests for the status filter |
| `fixtures/arxiv-150k.fixture.yaml`, `fixtures/arxiv-smoke.fixture.yaml` | declare `field_map` — arXiv's own names, a documented no-op |
| `oneground/analogy.py` | **(016b)** `MATCHABLE_STATUS`; only built/verified fixtures are offered |
| `oneground/receipts/__init__.py` | **(016b)** `manifest_digest`, shared by the local and streamed paths |
| `oneground/sample/stackexchange.py` | **(016b)** `verify_source`, `open_shards`, `read_pinned_digests`, `local_source_digest`; the pass streams |
| `oneground/cli.py`, `corpora/build_fixture.py` | **(016b)** `--source` optional |
| `corpora/run_fixture_build.sh` | new — generic build runner; **(016b)** `SOURCE` optional |
| `corpora/fetch_stackexchange.py` | **(016b) deleted** — its job was storing the shards |
| `corpora/run_stackexchange_build.sh` | **(016b) deleted** — it only sequenced fetch-then-build |
| `oneground/pod/session.py` | **(016c)** `volume: none`, `uses_volume`, both rules documented |
| `oneground/pod/plan.py` | **(016c)** `resolve_anywhere`, `_pick_gpu` shared by both paths, volume-less payload and rendering |
| — | **(016e)** `deploy_candidates` in fallthrough order, `candidates_within`, per-candidate `deploy_spec` |
| `oneground/pod/api.py` | **(016c)** `list_datacenters`, `gpu_prices_across_datacenters` (one aliased call) |
| `oneground/pod/state.py` | **(016c)** records `volume: None` rather than crashing |
| `oneground/pod/cli.py` | **(016c)** `mkdir -p` the mount path before the first scp; **(016d)** `_wait_ssh_ready` seam, `--ssh-ready-timeout`, `_redact_dict`, records `ssh_ready`/`ssh_error`/`last_ssh` |
| `oneground/pod/test_pod.py` | **(016c)** `DcTransport` stub; **(016d)** `RefusingSsh` stub; **(016e)** `_CreateStub`, +16 |
| `oneground/pod/sshx.py` | **(016d)** `wait_ready`, `SshNotReady`, `SshError.as_dict`, timeouts carry their command |
| `oneground/pod/api.py` | **(016c)** datacenter listing + aliased price matrix; **(016e)** `is_no_capacity` |
| `oneground/pod/state.py` | **(016c)** `volume: None`; **(016e)** records the card actually deployed, plus `planned_gpu` |
| `sessions/stackexchange-build.yaml` | new — the pod session; **(016b)** no `SOURCE`, generic runner; **(016c)** `volume: none`, `disk_gb: 60` |
| `sessions/stackexchange-shards.sha256` | new — 59 pinned shard digests |
| `tasks/scratch/016-negative-control.py` | new (scratch is gitignored) |
| `tasks/scratch/016-reservoir-footprint.py` | new (scratch is gitignored) |
| `tasks/scratch/016b-stream-probe.py`, `016b-schema-probe.py`, `016b-stream-feasibility.py`, `016b-no-disk-probe.py`, `016b-no-disk-probe2.py` | **(016b)** the source probes (scratch is gitignored) |

### (016f) The build ran, and the cap killed it 21 minutes from the finish

Session **20260911-220320**, pod `demdanrfl4y0gb`, **A40 in CA-MTL-1** at
$0.49/hr — the fallback candidate, deployed without a second `y`, exactly as
016e intended. `finished_because: cap`. Neither tarball existed when `watch`
went to fetch, and with `volume: none` the container disk went with the pod.
**Nothing was recovered. Cost $0.73.**

Steps 5, 6, 7 and 8 are therefore **not done**: there are no artifacts to
publish values from, nothing to simulate against, no decision log and no
findings. The values were computed on that pod and are gone. I am not
publishing numbers read off a progress log rather than off the artifact they
belong to — `kind: receipt` exists to prevent exactly that.

**The three numbers the brief asked for did survive**, because the log carries
them:

| | |
|---|---|
| ssh-ready | **1.5 s, 1 attempt** — the 016d wait never had to retry |
| streamed pass | **46m 56s**, 59 shards, **~12.1 MB/s** sustained, nothing stored |
| embed on the A40 | **6m 14s for 152,000 texts** (~406 texts/s) |

and so did the sampling frame: **20,388,803 eligible questions** across 16
years, 35.0% of the 58,329,355 posts, sampled to 150,000 base + 2,000 queries
over **199 hot categories**. Source verified as
`a656730c7671…de1207` from LFS metadata in ~1 s, before any content moved.

#### Where the 90 minutes went

| phase | elapsed | share of cap |
|---|---|---|
| pod create → run start (image pull, venv, clone, setup) | 5m 01s | 5.6% |
| source verify (metadata only) | 1s | — |
| **streamed sampling pass, 59 shards** | **46m 56s** | **52.1%** |
| sample write + split | 22s | 0.4% |
| embed 152k texts | 6m 14s | 6.9% |
| exact ground truth | 15s | 0.3% |
| characterize (TwoNN, k-means 256, drift) | 49s | 0.9% |
| reference: single-node HNSW | 3m 06s | 3.4% |
| reference: semantic-sharded | 2m 32s | 2.8% |
| **MANIFEST written — receipts complete** | **at 23:08:44** | **24m 38s before the cap** |
| UMAP projection | 4m 24s | 4.9% |
| `fixture verify` + ground-view export + tar | **20m 21s, unfinished** | 22.6% |

Two things that table says.

**The streamed pass is half the budget.** 47 minutes for ~32 GB of column
chunks is the irreducible cost of not storing the source, and it is the thing
that makes a 1.5 h cap the wrong size for this build — not any of the
measurement steps, which together came to under 14 minutes.

**And the tail re-did work the build had already done.** `fixture verify` runs
as the next step after the builder, and
[verify.py:473](oneground/fixture/verify.py#L473) and
[verify.py:487](oneground/fixture/verify.py#L487) recompute `ref_single_node`,
a fresh `kmeans(base, 256)` and `ref_semantic_sharded` — **unconditionally**,
whether or not the spec has a value to compare against. This spec is
`status: planned` with every value `TO_BE_FILLED`, so those ~6–8 minutes of
recomputation could only ever produce `couldnt_check` rows, every one of them
knowable from the spec before a single vector was read. On the first build of
a planned fixture the verify step has nothing to verify: the build's own output
is what fills the values.

#### What I would change, and what I did not

I did **not** touch `caps.max_hours`. It is a spec value; rule 3 says a gate
does not move to make something pass, and the brief says not to raise caps.
The options are the developer's to pick, and they are not equal:

1. **Package the receipts as soon as the MANIFEST exists.** The strongest fix,
   and independent of the cap. At 23:08:44 every receipt artifact was on disk
   and complete; the run then spent 24 minutes on the projection, a verify that
   could not verify anything, and a ground-view export — and lost all of it for
   want of a `tar` that had not happened yet. A small tarball built immediately
   after the manifest would have survived this run.
2. **Skip `fixture verify` when every published value is `TO_BE_FILLED`.**
   Recovers ~6–8 minutes and removes a step that, on a first build, is
   guaranteed to report nothing.
3. **Raise `max_hours`.** The honest reading of the table is that this build
   needs ~100–105 minutes, not 90. That is a real number now rather than an
   estimate — but it is a cap, and moving it is your call, not mine.
4. **Give the session a volume.** It would have made this failure survivable:
   the artifacts would still be on `vecbench` and fetchable. But it re-pins the
   region to the volume's stock, which is what 016c removed for good reason —
   and that reason has not gone away.

(1) and (2) together would have brought this run home inside the existing cap
with room to spare. I have not implemented either: both change the build
runner, and neither was in this brief.

#### Also worth recording

`watch` behaved correctly throughout. It never tripped the stall watchdog —
peak idle was 11.7 min against a 20 min `stall_minutes`, during the verify
recomputation — and at the cap it tried to fetch before terminating, reported
`couldn't-check: not present on the pod` for both outputs rather than claiming
success, and left zero pods on the account.

### (016g) Receipts first, a verify that has nothing to verify, and a cap that fits

Three changes after the lost build, all asked for.

**1. The runner packages the receipts the moment they exist.**

The builder already wrote its MANIFEST before anything optional — that was
deliberate, and the comment in `build.py` says so. What it did not have was
anyone packaging at that point. So the projection moved out of the builder and
became its own step:

    build --skip-projection   ->  pack "the manifest (receipts complete)"
    fixture project           ->  pack "the projection"
    fixture verify            ->  pack "verify"
    export_ground_view        ->  pack "the ground view"

`--skip-projection` is now always passed by the runner; `SKIP_PROJECTION=1`
still means "do not project at all". `pack` writes to `$TARBALL.tmp` and
`mv -f`s it into place, so a `watch` that fetches mid-repack gets the previous
whole tarball rather than a truncated one. Optional members are included from
the stage that produces them onward, so an early pack cannot fail on a file
that does not exist yet.

**The split changes nothing about what is produced.** A smoke rebuild under the
new path reproduces all six receipts *and* the projection byte for byte against
the committed manifest:

| artifact | digest | |
|---|---|---|
| `sample.jsonl.zst` | `b6383e22…` | identical |
| `vectors.npy` | `d9f44ded…` | identical |
| `queries.npy` | `2359ce71…` | identical |
| `query_ids.json` | `0081604b…` | identical |
| `ground_truth.npy` | `13919bb5…` | identical |
| `characterization.json` | `07b576e2…` | identical |
| `projection.npy` | `adba4173…` | identical — run as its own step |

**The cap-kill test the brief asked for.** `tasks/scratch/016g-capkill-smoke.sh`
runs the *shipped* runner on smoke, waits for `UMAP projection` to appear, and
kills the process there — the same shape that killed session 20260911-220320:

    projection started.
      at projection start, receipts tarball EXISTS: 45253 bytes
    killing the run now (the cap-kill).

    --- tarball listing captured AT projection start ---
      .../MANIFEST.sha256        .../query_ids.json
      .../characterization.json  .../ground_truth.npy
      .../build_info.json        logs/build-arxiv-smoke.log

    release tarball EXISTS: /tmp/016g-capkill/smoke-large.tgz (6418819 bytes)
    PASS: receipts were on disk before the projection ran.

`projection.npy` is **absent** from that tarball, which is what makes the test
conclusive: the kill landed during the projection, not after it. The test
fails itself with `INCONCLUSIVE` if it ever lands late.

**2. `fixture verify` skips the recomputation when nothing is published.**

`_anything_published` decides via `_as_number` — the same function `_compare`
uses — so the guard and the comparison cannot disagree about what counts as a
published value. Deliberately generous: one filled value anywhere is enough to
make the recomputation worth doing, because that one value can still be
contradicted. Only the all-placeholder case is skipped, and every row is still
reported `couldnt_check` with the reason; it just costs nothing to say so.

Tests pin both shipped specs: `stackexchange-150k` is in the skip case,
`arxiv-150k` is not.

**3. `caps.max_hours: 1.5 -> 2.0`,** on the measured evidence rather than a
guess. `max_usd` is unchanged at 2.50 and still binds: 2.0 h × $0.74/hr (the
dearest card in the list that has actually been offered) is **$1.48**.

#### Two things I did that were not asked for

**`OUT` is now a runner variable.** The test had to drive the *shipped* script,
and the script hardcoded `--out fixtures/` — so testing it would have rebuilt
the committed smoke artifacts in place. `build_info.json` carries a timestamp,
so the MANIFEST would have differed and dirtied the repo on every test run.
`OUT` defaults to `fixtures/`, and `fixture verify` is passed
`--fixtures-dir "${OUT%/}"` so the two cannot point at different directories.

**A structural test of the packaging order**, alongside the end-to-end one:
that the first `pack` precedes the projection, that the builder is always told
to skip it, that every later stage repacks, that packing is atomic, and that
`projection.npy` is not a mandatory member. The end-to-end test costs a
9-minute rebuild; these run in milliseconds and fail for a readable reason.

#### Two bad tests before a good one

Worth recording, because both produced confident wrong output.

The first used `tar -tzf "$TAR" | grep -q "/$want$"`. `grep -q` exits at its
first match and closes the pipe, `tar` takes SIGPIPE, and under `pipefail` the
pipeline reports failure — so it printed `FAIL: MANIFEST.sha256 missing` for
five files listed one line above in its own output. The listing is now captured
once into a variable and matched with `case`.

The second polled for the projection every 5 seconds. Smoke's UMAP over 2,000
points finishes in less than that, so the kill landed after the projection and
after its repack, and `projection.npy` was in the tarball. That run proved
nothing about ordering — and said so, because the test checks for exactly that
and exits `INCONCLUSIVE`. The poll is now 0.1 s.

One bug I introduced and caught on a read-through: because the builder is now
*always* given `--skip-projection`, `SKIP_PROJECTION=1` had become a no-op that
printed a NOTE and then projected anyway through the new separate step.
Honouring it moved to the runner, with a test that pins the guard to the
projection call rather than to the earlier NOTE.

I also confirmed the one shell idiom the new `pack` depends on: under
`set -euo pipefail`, `[ -f "$f" ] && members+=("$f")` does **not** abort when
the file is absent. Checked rather than assumed, because it runs on a paid pod.

#### And a third test caught me

The full suite failed on
`test_every_dispatchable_command_is_guarded_or_deliberately_not`:

    assert not ['oneground fixture project']

That test walks the shipped parsers rather than a hand-written list, exactly so
a new subcommand cannot be added without someone accounting for its
environment guard. `fixture project` *is* guarded — `guard_or_exit` runs before
its branch in `_cmd_fixture`, and the guard string now carries the action name
— but it was not registered in `GUARDS_ON_USE`, which is how `build` and
`verify` declare that they guard inside their own handler. Registered, with the
reason. Task 013b's note on that test says it was written after a hand-written
list let an unguarded seventh command through; it has now done its job on an
eighth.

## Blocked on developer

**(016g) Ready to retry.** The three fixes are in and tested: the receipts are
packaged the moment they exist, `fixture verify` no longer recomputes against
placeholders, and the cap is 2.0 h. A rerun that trips the cap now loses only
the stages after whatever it reached, not the build.

~~**(016f) The item that matters now: the build needs ~100–105 minutes and its
cap is 90.**~~ *Addressed in 016g — kept for the trail.* That is measured, not estimated — the phase table above accounts
for all 90 minutes of the killed run. Four ways forward, in the order I would
rank them, none of which I have taken because all four are yours:

   a. **Package the receipts the moment the MANIFEST is written.** — **done
      in 016g**, and tested with a cap-kill mid-projection.
   b. **Skip `fixture verify` when every published value is `TO_BE_FILLED`.**
      — **done in 016g**.
   c. **Raise `caps.max_hours`** to 2.0 — **done in 016g**, on the measured
      evidence, with `max_usd` unchanged and still binding at $1.48 worst case.
   d. **Give the session a volume.** Still **not** done, and still the one I
      would not take: it re-pins the region to that volume's stock, which is
      what 016c removed and why. (a) makes a cap-kill survivable without it.

1. **Push `444c250`** (task 014d). One commit. I do not push.
2. **Dispatch the calibration workflow** for run #6. Still open from 014c/014d,
   and still the only thing that settles whether GitHub's receive-pack accepts
   a push from the depth-1 checkout.
3. **The `y` for `oneground pod up sessions/stackexchange-build.yaml`** — brief
   step 5. `plan` resolves live to **US-WA-1 / RTX 6000 Ada**, worst case
   **$1.26** against `max_usd` 2.50. Steps 6–9 (simulate, decision log,
   `fixture verify --asset`, `docs/FIXTURES.md`) all need the artifacts this
   produces.

   **(016c) The one-pod-at-a-time constraint no longer applies to this
   session.** It uses no network volume, so it does not contend with the other
   stream's pod on `vecbench` — the two can run at the same time, in different
   regions. `caps.max_concurrent` is still 1 *within this session*.

   Two things to expect. Stock moved twice during this task, so `plan` may pick
   a different region or card by the time you run `up`; re-run `plan` first and
   the confirmation prompt will show what it actually resolved. And stock on the
   chosen card reads **Low**, so a create can fail outright — that costs
   nothing, but it means a retry rather than a queue.

   **(016d) The first attempt already ran and is cleaned up.** Session
   20260911-200558, pod `x514af1cflnw6m`, EU-CZ-1, RTX 4090 at $0.74/hr: it
   created, reached RUNNING, and died on the first SSH command. Its record says
   `terminated`, and `oneground pod ls` reports **0 pods on the account** —
   checked just now, not assumed. Nothing is billing.

   `up` now waits up to 180 s for sshd, logging each attempt, so a retry should
   get past where that one stopped. It also records `ssh_ready` with the real
   time sshd took, which is the number that should size the window.
