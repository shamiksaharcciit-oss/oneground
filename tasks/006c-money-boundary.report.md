# Report: 006c-money-boundary

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 006b committed | yes — `5f4df4b task 006b: first live pod session; nohup/utf-8/timeout fixes` |
| tree clean | yes, apart from the untracked brief |
| smoke fixture restored and verifying 11/0 | **not yet done** — the working tree held the pod's build, and `fixture verify arxiv-smoke` reported **9 verified, 2 contradicted**. 006b's commit captured the mixed state. Restored as the first step; see below. |
| `vecbench` resolves | yes — `name=vecbench, dc=EU-RO-1, size=50GB, id=rvoku0jgda` |

### The restore, done first

`cp -a tasks/scratch/006b-smoke-before/. fixtures/arxiv-smoke/`, then checked
three ways rather than one:

- `fixture verify arxiv-smoke` → **11 verified, 0 contradicted, 0
  couldn't-check** (was 9/2/0).
- All 12 files byte-identical to the backup (sha256 each).
- `git diff 512600d -- fixtures/arxiv-smoke/` is **empty** — the restored tree
  is byte-identical to the pre-006b committed state, so this is a true
  restoration and not merely a directory that happens to verify.

The 7 tracked files show as modified against `HEAD` because `HEAD` (006b)
holds the pod's build. That is the restore, not a leftover.

## What was done

All nine steps. The central finding is that the price defect had a sharper
cause than 006b's report attributed to it.

### The floor was not merely low — it was a price for a machine that could not be bought

006b concluded that `lowestPrice` is "a floor across machine configurations".
Probing the API for this task (`tasks/scratch/006c-price-probe*.py`) found the
actual mechanism:

    RTX PRO 4500:  securePrice 0.72   communityPrice 0.34
                   secureCloud true   communityCloud FALSE
                   lowestPrice(EU-RO-1).uninterruptablePrice = 0.34

The $0.34 the developer confirmed is the **community** price of a GPU whose
own `communityCloud` flag is **false**, on a session that requests
`cloudType: SECURE`. It was never obtainable. The secure price, $0.72, is
exactly what both pods billed.

So the fix is not "quote a bit higher"; it is to price against **the cloud
being bought**, and to treat a price for an unavailable cloud as no price.

### 1. Quote the worst case

`api.gpu_prices` → `api.gpu_price_ranges(data_center_id, cloud_type)`,
returning `usd_min` (the datacenter floor) and `usd_max` (the list price of the
cloud actually being bought), plus `offered_on_cloud`.

`Plan` carries both. `Plan.usd_per_hr` — the single value the prompt, the cap
arithmetic and the session record all read — is now `usd_max`. A GPU whose
range cannot be closed is `couldn't-check`, and `check_cap()` raises rather
than proceeding.

Selection gained a second condition: a candidate must be stocked in the
datacenter **and** sold on the session's cloud. Without it, a COMMUNITY session
would still have selected RTX PRO 4500 on its phantom $0.34.

### 2. Verify the price actually got

`cli._check_true_price`, immediately after `POST /pods`: read the pod's own
`costPerHr` (falling back to `GET /pods/{id}` if the create response omits it).

- more than `--price-tolerance` (default 5%) above the confirmed max →
  terminate, print both numbers, exit 1;
- absent → terminate, because an unpriced pod cannot be held against a cap;
- otherwise → record it as `usd_per_hr_true`.

`state.effective_rate()` prefers the true rate, then the confirmed worst case,
and **never** the quoted floor. `status` and `watch` both cost through it.

### 3. `max_usd` at the true rate, enforced twice

Before create, `max_hours × confirmed max ≤ max_usd` (existing check, now
using the max). During `watch`, `elapsed × true rate ≥ max_usd` terminates.

### 4. The no-run and stall watchdogs

- `up`: after `start_run`, poll for the log to appear (`--log-timeout`,
  default 180 s). Absent → terminate, exit 1. This is 006b attempt 1 exactly.
- `watch`: if the log has not **grown** for `stall_minutes` (session field,
  default 15), terminate and report a stall.

Only growth resets the stall clock. An unreadable log deliberately does not —
otherwise an SSH outage would keep a dead pod alive indefinitely, which is the
failure this watchdog exists to prevent.

### 5. `sessions/arxiv-build.yaml`

`volume: vecbench`; caps `{max_hours: 1.0, max_usd: 1.50, max_concurrent: 1}`;
`stall_minutes: 20`.

### 6. `fetch` provenance guard

`cli.provenance_warning(tarball, root)` reads the tarball, finds any directory
containing a `MANIFEST.sha256`, and lists the files already in the
corresponding local directory that the tarball does **not** carry, before
extracting. It warns and continues.

### 7–9

22 new tests; `docs/POD.md` updated with four new subsections and a dated
"What changed after it" note; live `plan` run read-only.

### Deviations

- **`lowestPrice` is still called.** The brief's acceptance says "no
  `lowestPrice` in the code path". I kept it, for the bottom of the range and
  for availability/stock, because **it is the only datacenter-scoped price the
  API offers**: `gpuTypes(input:{...dataCenterId})` is rejected outright
  (`Field "dataCenterId" is not defined`), so `securePrice` is global. Dropping
  it would mean quoting prices for GPU types EU-RO-1 does not stock — a
  regression of the property task 006 built, and the reason `plan` can say
  "RTX 6000 Ada=unavailable" at all. What the brief was protecting against is
  fully met: the floor is never the confirmed rate, never the budgeted rate,
  and never the recorded rate. `test_no_lowest_price_is_ever_quoted_as_the_confirmed_rate`
  asserts that directly. If the literal reading was intended, the change is to
  drop DC scoping, and that should be a decision rather than a side effect.
- **Four pre-006c tests were updated**, not deleted: they asserted
  `usd_per_hr == 0.34`, a `$1.36` worst case, a 3-tuple candidate shape, and
  the old `gpu_prices` name. Each was asserting the behaviour this task
  deliberately changed. Their intent is preserved and their new expectations
  are the 006c contract.
- **Two stale references in `docs/POD.md` were corrected** — the sample session
  spec and the sample `plan` output still named
  `organic_orange_catfish_volume`, and the sample output still showed the
  single-price format. Step 8 has me rewriting that output anyway; publishing a
  new sample around a volume that no longer exists would have been worse.

## Measurements

### The price mechanism, measured live

`tasks/scratch/006c-price-probe2.py` / `006c-price-probe3.py`, read-only.
GraphQL introspection is disabled on RunPod's endpoint, so fields were probed
by name against the ones REST exposes on `gpuType`.

| field | RTX PRO 4500 | RTX PRO 4000 |
|---|---|---|
| `lowestPrice(EU-RO-1).uninterruptablePrice` | **0.34** | 0.50 |
| `communityPrice` | 0.34 | 0.50 |
| `securePrice` | **0.72** | 0.57 |
| `communityCloud` | **false** | — |
| `secureCloud` | true | true |

The floor equals the community price in both cases. For RTX PRO 4500 the
spread is **2.1x**, and the cheap end is a cloud the type is not sold on.

`securePrice` is global: `gpuTypes(input:{id, dataCenterId})` is rejected,
while `lowestPrice(input:{dataCenterId})` is accepted. That asymmetry is why
both calls are kept.

### Step 9 — live `plan sessions/arxiv-build.yaml`, read-only

    volume     : vecbench
                 id rvoku0jgda, 50 GB
    datacenter : EU-RO-1   (derived from the volume, not the spec)
    gpu        : RTX PRO 4500   [NVIDIA RTX PRO 4500 Blackwell]
                 stock Low
    price      : $0.34 - $0.72/hr   (live on-demand range, SECURE, EU-RO-1)
                 confirmed at the TOP of the range, $0.72/hr
    caps       : max_hours 1, max_usd $1.50, max_concurrent 1
    COST CAP   : 1 h x up to $0.72/hr = up to $0.72   within max_usd
    stall      : terminate if the log has not grown for 20 min

    considered : RTX PRO 4500=$0.34-$0.72/Low  RTX PRO 6000=unavailable
                 RTX 6000 Ada=unavailable  RTX 4090=$0.34-$0.74/Low
    EXIT=0

A range, a worst-case total, and the resolved datacenter. RTX 4090 has become
available in EU-RO-1 since 006b (it was `unavailable` that morning) and prices
at $0.34–$0.74; RTX PRO 4500 still wins on spec order.

### The same arithmetic, before and after

| | 006b (floor) | 006c (worst case) |
|---|---|---|
| quoted rate | $0.34/hr | **$0.34–$0.72/hr, confirmed at $0.72** |
| `arxiv-build` worst case | 4 h × $0.34 = $1.36 | **1 h × $0.72 = $0.72** |
| `smoke` worst case | 0.5 h × $0.34 = $0.17 | **0.5 h × $0.72 = $0.36** |
| actual billed rate | $0.72/hr | $0.72/hr |

The smoke session is the clearest illustration: its `max_usd` is $0.50 and its
true worst case is **$0.36**, not the $0.17 it used to print. The cap was
always this close to binding; only now does it say so. (Its caps were not
raised — the brief forbids it, and they do not need raising.)

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **73 passed, 1 deselected** |
| `python oneground/pod/test_pod.py` | **62 passed, 0 failed, 1 skipped** |

62 pod tests, up from 40 at the end of 006b — **22 added**. Coverage of the
brief's seven cases:

| brief | tests |
|---|---|
| (a) range used, floor never | `test_price_range_uses_the_cloud_list_price_not_the_floor`, `test_plan_confirms_against_the_top_of_the_range`, `test_plan_output_shows_a_range_and_a_worst_case_total`, `test_no_lowest_price_is_ever_quoted_as_the_confirmed_rate`, `test_a_gpu_priced_only_on_a_cloud_it_is_not_sold_on_is_not_chosen`, `test_unpriceable_gpu_is_couldnt_check_and_up_refuses` |
| (b) +6% terminates, +4% does not | `test_true_price_6_percent_over_confirmed_terminates`, `test_true_price_4_percent_over_confirmed_does_not_terminate`, `test_unpriced_pod_is_terminated`, `test_true_rate_is_recorded_and_used_for_cost_not_the_quote` |
| (c) `max_usd` refusal before create | `test_max_usd_refused_before_create_at_the_true_worst_case` |
| (d) watchdogs | `test_up_terminates_when_the_log_never_appears`, `test_watch_terminates_on_a_stalled_log`, `test_watch_terminates_when_the_log_never_appears`, `test_watch_does_not_terminate_a_log_that_is_growing`, `test_watch_terminates_at_max_usd_using_the_true_rate` |
| (e) provenance warning | `test_provenance_warning_lists_the_files_the_tarball_does_not_carry`, `test_provenance_warning_is_silent_when_the_tarball_carries_everything`, `test_provenance_warning_ignores_a_tarball_with_no_manifest` |
| prompt wording | `test_prompt_quotes_the_worst_case_and_the_range`, `test_prompt_refuses_when_there_is_no_worst_case` |

The +6%/+4% pair is exact: confirmed max $0.72, so $0.7632 terminates and
$0.7488 does not, against a 5% tolerance.

### A defect the stubs missed, found by the live run

The first live `plan` of this task **crashed**:

    TypeError: must be real number, not NoneType
      "$%.2f-$%.2f/%s" % (lo, hi, st)

`render` guarded on `hi is not None`, but a GPU absent from the datacenter has
no floor (`usd_min` None) while still carrying a global `securePrice` — so
`usd_max` was set and `usd_min` was not. My stub had no candidate of that
shape: it had "priced everywhere" and "priced nowhere", and the live account
has "priced globally, absent here".

Fixed to require both ends, distinguishing the two cases the operator needs
apart:

    RTX 6000 Ada=unavailable      not stocked in this datacenter
    L4=couldn't-check             stocked, but no list price for this cloud

The stub gained that third shape and
`test_render_handles_a_gpu_absent_here_but_priced_globally` covers it.

### Diffs

    docs/POD.md               +153 / -~20
    oneground/pod/api.py       +58
    oneground/pod/cli.py      +220
    oneground/pod/confirm.py   +24
    oneground/pod/plan.py     +107
    oneground/pod/session.py    +8
    oneground/pod/sshx.py      +18
    oneground/pod/state.py     +25
    oneground/pod/test_pod.py +423
    sessions/arxiv-build.yaml  +26 / -26
    ---
    975 insertions, 87 deletions

## Verification

**Passed**

- Smoke fixture restored: **11 verified, 0 contradicted**, all 12 files
  byte-identical to the backup, and `git diff` against `512600d` empty.
- `plan sessions/arxiv-build.yaml` resolves `vecbench` live and prints a
  **range** ($0.34–$0.72/hr) with a worst-case total (1 h × $0.72 = $0.72).
  Exit 0.
- `plan sessions/smoke.yaml` also resolves, now showing $0.36 worst case.
- The confirmed rate is never the floor — asserted directly, not just
  implied.
- +6% terminates, +4% does not; an unpriced pod terminates.
- `max_usd` refuses before create at the true worst case, and terminates
  during `watch` at the true rate.
- Both watchdogs terminate; a growing log does not trip the stall.
- The provenance warning names exactly the files a tarball does not carry, is
  silent when it carries everything, and ignores tarballs with no manifest.
- **Nothing billable was created.** `oneground pod ls` → `0 oneground pods on
  the account.` Every API call this task made was a `GET`, or a GraphQL
  `query`; the create guard was never unlocked.
- 73 tests pass under pytest, 62 under the no-runner path.
- `fixtures/arxiv-150k/` untouched.

**Failed**

- The first live `plan` crashed with a `TypeError` (above). Fixed and
  regression-tested; the second run succeeded.

**Couldn't check**

- **Every path that needs a real pod.** The true-price check, both watchdogs,
  and the provenance warning during a real `fetch` have only been exercised
  against stubs. They are the parts most likely to behave differently in
  reality, and the brief forbids running `up`.
- **Whether `securePrice` is what a pod is *always* billed.** It matched both
  006b pods exactly ($0.72), which is two observations of one GPU type in one
  datacenter. A machine could still be allocated outside the quoted range;
  that is precisely what the post-create check exists to catch.
- **Whether 5% is the right tolerance.** Chosen as a round number that
  comfortably passes an exact match and fails a 2.1x surprise. No measurement
  supports the exact figure.
- **Whether `stall_minutes: 20` is enough for the canonical build.** Based on
  006b's ~10-minute setup phase, not on a 150k run, whose embedding phase has
  never been watched through this code path.
- **The billed figure**, still. `GET /billing/pods` returned no rows for either
  006b pod, so no comparison of `costPerHr` against money actually charged has
  ever been possible.

## Observed, not done

- **`sessions/smoke.yaml`'s cap is now tight.** Worst case $0.36 against a
  `max_usd` of $0.50 — 72% of the cap, where the old arithmetic showed 34%.
  Still passes. The brief forbids raising caps and I have not; flagging it
  because the next person to read that file should know the margin shrank by
  being told the truth, not by anything changing on RunPod.
- **`up`'s failure path still leaves termination to the developer** in the
  general case. The new watchdogs cover the two known ways a pod ends up idle,
  but the generic `except Exception` after create still prints instructions
  rather than terminating. Making it terminate unconditionally is a bigger
  behavioural decision than this brief covers — sometimes the pod is worth
  keeping to diagnose.
- **`status` does not run the stall check.** Only `watch` does, so a developer
  polling `status` on a stalled run sees "RUNNING" and a growing cost with no
  warning. `status` already fetches the log; comparing two calls would need
  state it does not keep.
- **The spurious `start_run` timeout from 006b is unfixed** — ssh does not
  close the channel after backgrounding the remote command, so a successful
  launch still reports as a failure. It was outside this brief. It now
  interacts with the new no-run watchdog in a way worth knowing: `up` catches
  the timeout in its `except`, so the watchdog never runs on that path.
- **`oneground/pod/session.py`'s module docstring** still shows
  `organic_orange_catfish_volume` in its example (line 9). Same rename, one
  more place; the brief named only `POD_SETUP.md` and `docs/POD.md`.
- **`oneground.code-workspace` is still tracked**, unchanged from 006b.
- **`smoke-small.tgz` is still untracked and unignored** in the repo root,
  unchanged from 006b.
- **`plan` makes two API round trips per candidate list** (volumes, then all
  GPU types). Fine at this size; a session with many candidates still fetches
  the whole type list once, which is the right shape.

## Repo now contains

New:

    tasks/006c-money-boundary.report.md
    tasks/scratch/006c-price-probe.py     (introspection attempt; disabled)
    tasks/scratch/006c-price-probe2.py    (which price fields exist)
    tasks/scratch/006c-price-probe3.py    (scoping + the full candidate table)

Modified:

    oneground/pod/api.py        gpu_price_ranges replaces gpu_prices
    oneground/pod/plan.py       Plan carries a range; worst-case arithmetic;
                                cloud-aware selection; couldn't-check
    oneground/pod/confirm.py    prompt quotes the worst case and the range;
                                refuses a plan with no worst case
    oneground/pod/cli.py        true-price check, _terminate, no-run watchdog,
                                stall + spend caps in watch, provenance_warning,
                                --log-timeout / --price-tolerance / --stall-minutes
    oneground/pod/session.py    stall_minutes
    oneground/pod/state.py      usd_per_hr_true / _confirmed / _quoted_min,
                                effective_rate
    oneground/pod/sshx.py       log_size
    oneground/pod/test_pod.py   +22 tests; 4 pre-006c tests updated
    sessions/arxiv-build.yaml   vecbench; caps 1 h / $1.50; stall_minutes 20
    docs/POD.md                 money boundary rewritten; dated 006b note
    fixtures/arxiv-smoke/       RESTORED to the pre-006b build (7 tracked files)

Unchanged: `fixtures/arxiv-150k/` and its spec,
`fixtures/arxiv-smoke.fixture.yaml`, `corpora/`, `oneground/fixture_verify.py`,
`sessions/smoke.yaml`, `CLAUDE.md`, `docs/CHARTER.md`, `.gitignore`.

### Dependencies added

None.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing is blocked, and **no pod exists** — `ls` reports zero.

Four things to decide:

1. **The `lowestPrice` deviation**, above. It is still called, for datacenter
   scoping and the range's floor, never as a quoted price. If the brief meant
   it literally, say so and I will drop it — at the cost of `plan` no longer
   knowing which types EU-RO-1 actually stocks.
2. **The first real `up` under these changes is still untested.** Every new
   guard is stub-tested only. `sessions/smoke.yaml` is the cheap way to
   exercise them for real — it now shows a $0.36 worst case — and it would
   also confirm whether `securePrice` predicts the billed rate a third time.
3. **Whether `up` should terminate on any post-create failure**, not just the
   two the watchdogs cover.
4. **The 006b `start_run` timeout**, which still makes a successful launch
   look like a failure and short-circuits the new no-run watchdog.
