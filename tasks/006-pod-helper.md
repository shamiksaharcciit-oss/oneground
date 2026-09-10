# Task 006 — `oneground pod`: agent-driven pod sessions

## Expected repo state
Task 005 committed; tree clean. `RUNPOD_API_KEY` is set in the developer's
user environment (50 chars). You will find it in your terminal only after
VS Code has been restarted; if `os.environ.get("RUNPOD_API_KEY")` is None,
stop and report — do not ask for the value, do not search for it.

## Why
Every pod session so far was the developer pasting commands. This helper
makes sessions a single command driven by you, while keeping the money
boundary explicit: **you may prepare, dry-run, monitor, and terminate;
only the developer's typed confirmation creates a billable resource.**
The same code becomes the user-facing `verify.target: runpod` later, so
build it as package code, not a script.

## Do
1. Create `oneground/pod/` with a CLI `oneground pod <subcommand>`:
   - `plan <session.yaml>` — resolve a session spec to a concrete plan:
     GPU/CPU type, datacenter (must match the named volume's), volume id,
     template/image, container disk, env vars, the run command, and the
     **hourly price from the RunPod API**. Prints the plan and the cost cap.
     Never creates anything. This is the dry run; it must work end to end
     against the live API in read-only calls.
   - `up <session.yaml>` — prints the plan, then asks
     `Create this pod at $X.XX/hr with a hard cap of N hours? [y/N]` and
     reads from stdin. Only `y` proceeds. Non-interactive stdin → refuse.
     On `y`: deploy, wait for Running, sync the repo (git bundle over
     `runpodctl` or the pod's SSH; pick one and justify), run the session's
     command under `nohup`, record pod id + start time in
     `.oneground/sessions/<id>.json` (git-ignored).
   - `status [<id>]` — pod state, elapsed, cost so far, last 20 log lines.
   - `fetch <id>` — download the session's declared output files to the
     paths the spec names (small tarballs into the repo, large into a path
     outside it).
   - `down <id>` — terminate. No confirmation (it only saves money).
   - `watch <id>` — poll; when the run prints `DONE` or the cap is hit,
     fetch (if configured) then terminate automatically. This is the
     unattended path.
2. Session spec `sessions/<name>.yaml`, example committed for build-type
   sessions:
       gpu: ["RTX PRO 4500", "RTX 6000 Ada", "RTX 4090"]   # first available
       volume: vecbench            # by name; datacenter derived
       image: runpod/pytorch:latest-cuda13   # pinned tag, look up the real one
       disk_gb: 20
       env: {HF_HOME: /workspace/hf}
       setup: corpora/POD_SETUP.md   # steps executed, or a script path
       run: bash corpora/run_arxiv_150k.sh
       outputs:
         - {remote: /workspace/arxiv-150k-small.tgz, local: ./, extract: true}
         - {remote: /workspace/arxiv-150k-large.tgz, local: ../oneground-assets/}
       caps: {max_hours: 2, max_concurrent: 1, max_usd: 3.00}
   Caps are enforced client-side (refuse `up` if a session is live and
   max_concurrent would be exceeded; `watch` terminates at max_hours).
3. Safety rules, enforced in code with tests:
   - API key from env only; never logged, never written to disk, redacted
     in any error output.
   - No subcommand except `up` calls a create/deploy endpoint; test this by
     stubbing the API client and asserting `plan`, `status`, `fetch`,
     `down`, `watch` never invoke it.
   - `up` with `--yes` is **not** implemented. There is no non-interactive
     create path. Document why in the module docstring.
   - Every created pod gets a label `oneground-session=<id>` so
     `oneground pod ls` can find and terminate orphans; `ls` warns on any
     pod older than max_hours.
4. Move the venv to local disk on the pod: setup creates `/root/.venv`
   and symlinks it to `<repo>/.venv` (the network-volume venv took ~30 min
   to populate; local disk is minutes). Update `POD_SETUP.md` accordingly.
5. Tests: unit tests with a stubbed API; one integration test marked
   `@pytest.mark.live` that runs `plan` against the real API (read-only)
   and is skipped when the key is absent.
6. Docs: `docs/POD.md` — how sessions work, the money boundary, the caps,
   how to recover an orphan.

## Acceptance
- `oneground pod plan sessions/arxiv-build.yaml` runs live (read-only) and
  prints a plan with a real hourly price and the resolved datacenter.
- Stubbed tests prove no create call outside `up`; `up` refuses
  non-interactive stdin.
- Nothing billable was created during this task. State this explicitly in
  the report, with the `ls` output showing zero oneground pods.
- `.gitignore` covers `.oneground/`.

## Do not
- Run `up`. Create a volume. Store the key anywhere. Add a `--yes`.
- Touch fixture files or measured values.
