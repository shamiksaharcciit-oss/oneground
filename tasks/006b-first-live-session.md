# Task 006b — First live session (smoke), and loose ends

## Expected repo state
Task 006 committed; tree clean. Developer has renamed the RunPod volume to
`vecbench` (verify with `oneground pod plan`; if the name still doesn't
resolve, stop and report).

## Do
1. `.gitignore`: add `*.code-workspace`.
2. `corpora/POD_SETUP.md`: replace the two `organic_orange_catfish_volume`
   / stale `vecbench` references so the doc matches the renamed volume and
   the helper flow; add a short "Using `oneground pod`" section at the top
   pointing to `docs/POD.md`, and mark the manual steps as the fallback.
3. `CLAUDE.md` Environment section: add one sentence: `RUNPOD_API_KEY is
   set at Windows user scope; if your process did not inherit it, read it
   from that scope into a subprocess environment for the call — never from
   files, history, or by asking. Never print, log, or persist the value.`
4. `sessions/smoke.yaml`: a session that runs the smoke fixture end to end
   on the pod (`SPEC=fixtures/arxiv-smoke.fixture.yaml
   SOURCE=tasks/scratch/001-synthetic-source.json TARBALL=/workspace/smoke-small.tgz`),
   fetching the small tarball to `./` with extract, caps
   `{max_hours: 0.5, max_concurrent: 1, max_usd: 0.50}`.
5. `oneground pod plan sessions/smoke.yaml` — must resolve; include output.
6. **Live run — developer participates.** Run
   `oneground pod up sessions/smoke.yaml`. The prompt will appear; the
   developer types `y`. Then `oneground pod watch <id>`: it must detect
   `DONE`, fetch the tarball, extract it over `fixtures/arxiv-smoke/`, and
   terminate the pod. Then `oneground pod ls` must show zero pods.
   Report: elapsed, cost from `status`, and the verifier on the fetched
   smoke fixture (8 verified expected, projection present since the pod
   spec has cuda).
   If anything in the chain fails, `oneground pod down <id>` first, then
   diagnose. A pod left running is the one unacceptable outcome.
7. `docs/POD.md`: append a "First live session" record: date, pod type,
   elapsed, cost, what was verified.

## Acceptance
- `ls` shows zero oneground pods at the end. State this explicitly.
- Smoke fixture on the laptop verifies from the fetched tarball.
- Cost of the session reported (expect under $0.05).

## Do not
- Run any session other than smoke. Change caps upward. Touch arxiv-150k.
