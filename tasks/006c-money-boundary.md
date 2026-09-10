# Task 006c — Money boundary by design, not by margin

## Expected repo state
Task 006b committed; tree clean; smoke fixture restored from
`tasks/scratch/006b-smoke-before/` and verifying 11/0 locally (do this
restore first if not yet done, and confirm the verifier).

## Why
006b showed the developer confirmed $0.34/hr and was billed $0.72/hr; the
`max_usd` cap held only because `max_hours` bounded the run in time. And
attempt 1 left a pod billing for ten minutes with no run started. Both are
defects in the boundary itself. Fix them so no real build runs on a
boundary that holds by luck.

## Do
1. **Quote the worst case.** `plan` stops reading `lowestPrice`. For each
   candidate GPU type it fetches the price range across configurations in
   the resolved datacenter (min and max on-demand `uninterruptablePrice`);
   the plan prints the range and the prompt confirms against the **max**:
   `Create this pod at up to $X.XX/hr (range $A–$B) with a hard cap of N
   hours = up to $C? [y/N]`. If the API cannot give a range, print
   `price: couldn't-check` and refuse `up` — never fall back to the floor.
2. **Verify the price you actually got.** After create, read the true
   `costPerHr` from the create/pod response. If it exceeds the confirmed
   max by more than 5%, terminate immediately, print both numbers, and
   exit non-zero. Record the true rate in the session file; `status` and
   `watch` use it for cost, never the quoted one.
3. **`max_usd` at the true rate.** Enforced twice: before create
   (`max_hours × confirmed max` must be ≤ `max_usd`, else refuse) and
   during `watch` (`elapsed × true rate`; terminate at the cap).
4. **No-run watchdog.** In `up`, after `start_run`, poll for the session
   log to appear; if no log within 3 minutes, terminate and exit non-zero
   with the reason. In `watch`, if the log has not grown for
   `stall_minutes` (session-configurable, default 15), terminate and
   report a stall. A pod with nothing to wait for must not survive.
5. **`sessions/arxiv-build.yaml`**: `volume: vecbench`. Also set its caps
   to `{max_hours: 1.0, max_usd: 1.50, max_concurrent: 1}` — build 3 took
   19 minutes; an hour is generous. Add `stall_minutes: 20` (pip install
   on the network volume was the slow phase; local-disk venv fixed that,
   so 20 covers it).
6. **`fetch` provenance guard.** When extracting a tarball that contains a
   MANIFEST into a directory holding files the tarball doesn't carry,
   print a warning listing those files as "local, not from this build"
   before extracting. Don't block; just don't be silent.
7. Tests with stubs, no pod: (a) range fetch used, floor never; (b) create
   returns +6% → terminate called; +4% → not; (c) `max_usd` refusal before
   create; (d) watchdog terminates on no-log and on stall; (e) provenance
   warning lists the right files.
8. `docs/POD.md`: update the money-boundary section to describe range
   quote, true-price check, and the watchdogs; add the 006b incident as a
   dated note (what happened, what changed).
9. Live check, read-only: `oneground pod plan sessions/arxiv-build.yaml`
   must resolve `vecbench` and print a price *range* for RTX PRO 4500.

## Acceptance
- Plan output shows a range and a worst-case total; no `lowestPrice` in
  the code path.
- All seven test cases pass; nothing billable created (state it; `ls`
  zero).
- `sessions/arxiv-build.yaml` resolves live.

## Do not
- Run `up`. Raise any cap. Touch fixtures beyond the smoke restore.
