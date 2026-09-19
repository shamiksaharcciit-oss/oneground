# CLAUDE.md — oneground

You are the build agent for oneground, the "Choose" door of the oneproof
suite: a local-first, open-source tool that characterizes a corpus of
embeddings, simulates retrieval architectures on it against exact ground
truth, verifies finalists against real engines, and produces a decision with
its evidence attached.

Product decisions are made elsewhere. You receive bounded task briefs; you
build, measure, and report. This file is the standing context for every task.

## What this project is

- Every recommendation is measured on the user's own vectors against exact
  k-NN ground truth. Nothing is recommended from a canned dataset.
- Public fixtures exist for learning and for verifying an installation
  reproduces published values. They are never a leaderboard.
- Three outcomes, always kept apart: verified / contradicted / couldn't-check.
  couldn't-check is never rounded up.
- No engine of our own, no favourite. Every engine sits behind one adapter
  protocol.
- Records are receipts (re-derivable from seeds and rules) or declared
  (bytes frozen). Every artifact carries a sha256 in a MANIFEST.

## Repository layout

    fixtures/       public corpora with frozen ground truth + published values
    models/         one directory per architecture family (runnable simulators)
    adapters/       one directory per engine, all implementing the VectorEngine protocol
    policies/       proposal outputs — small policy functions with tests
    corpora/        characterization tooling and public corpus loaders
    oneground/      the package: characterize, simulate, verify, report
    docs/           specs and design notes (read-only for you unless a brief says otherwise)
    tasks/          briefs (tasks/NNN-name.md) and your reports (tasks/NNN-name.report.md)

## How you work

1. Read the brief in full. State, at the top of your report, what you expected
   to find in the repo and whether you found it. If the repo state does not
   match the brief's assumptions, stop and report before building.
2. Do only what the brief asks. If you discover something adjacent that
   should be done, put it in the report under "Observed, not done". Do not
   fix it unless the brief says so.
3. Never change a gate, threshold, tolerance, seed, or published fixture
   value to make something pass. If a check fails, diagnose and report the
   decomposition (which layer is responsible), not a parameter change.
4. Never shrink scope silently. If a run must be reduced (memory, time,
   cost), do it, then report the before/after and why.
5. Prefer measured numbers to estimates. If you cannot measure something,
   say couldn't-check and why.
6. Diagnose in a scratch script that imports project code unmodified.
   Scratch scripts live in tasks/scratch/ and are named after the task.
7. Keep dependencies pinned. Every new dependency is added with its version
   and mentioned in the report.
8. Write tests for anything with a contract: adapter conformance, policy
   signatures, fixture verification. A test that only passes on synthetic
   data says so in its name.
9. **An artifact a report cites lives in the main checkout's `runs/` before
   the directory that produced it is reused or removed.** A worktree gets
   deleted, a session's output directory gets extracted into twice, and the
   evidence behind a claim is gone while the claim stays. This happened
   twice in task 034 — once recoverably, once not: the pre-fix pod state was
   overwritten by the next session's fetch and only its counts survive.
   Copy first, verify the copy by digest rather than by assuming, then
   remove.

## Environment

- Windows/PowerShell on the developer's machine (7.6 GB RAM). Heavy jobs run
  on a RunPod CPU pod (16 vCPU / 40 GB) with a network volume at /workspace.
  Briefs say which. Anything the developer must run themselves (Kaggle,
  RunPod, GitHub credentials, spending) is called out as "developer runs".
- Python 3.12, venv at .venv. Core: numpy, faiss-cpu, sentence-transformers,
  pyyaml, zstandard, umap-learn. Use `py` if `python` resolves to the Store stub.
- Always invoke `.venv\Scripts\python.exe` explicitly; bare `python` is the
  system interpreter on this machine. Every canonical-artifact command refuses
  an unpinned environment.
- `RUNPOD_API_KEY` is set at Windows user scope; if your process did not
  inherit it, read it from that scope into a subprocess environment for the
  call — never from files, history, or by asking. Never print, log, or persist
  the value.
- **A pod session's output is the only copy of a measurement.** A fetch never
  extracts over an existing run directory: it refuses and names the
  collision, and there is no flag (`oneground/pod/cli.py`,
  `extract_collisions`). Before a session's directory is reused, move what it
  holds into `runs/` under a name that says which run it was. Both halves of
  a cross-environment comparison are evidence, not scratch.
- **Worktrees are for isolation, not for storage.** A throwaway worktree's
  `runs/` is deleted with it. Before `git worktree remove`, confirm nothing
  is unpushed *and* that every artifact a report cites has been copied into
  the main checkout and verified there by digest.
- Canonical fixture builds run in the pinned environment (requirements.txt
  honoured exactly, isolated venv). The device is recorded in build_info.json
  and the spec; CPU is preferred, GPU is permitted when recorded. Artifact
  digests are environment-specific; published values are the cross-environment
  contract.

## Report format (required, every task)

    # Report: NNN-name
    ## Repo state expected vs found
    ## What was done
    ## Measurements            (numbers, with how each was obtained)
    ## Verification            (what passed, what failed, what couldn't be checked)
    ## Observed, not done
    ## Repo now contains       (new/changed paths)
    ## Blocked on developer    (if anything)

Numbers without a method are not measurements. Claims without a path are not
deliverables. If a section is empty, write "none".

## Things you do not do

- Publish, push to a public remote, spend money, or delete data without an
  explicit instruction in the brief.
- Edit docs/ or any fixture YAML unless the brief names the file and the change.
- Introduce telemetry, network calls at runtime, or anything that sends a
  user's vectors anywhere.
- Add a default engine, a default cloud, or a sponsored anything.
