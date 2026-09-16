# Task 024 — `oneground lab`: the local server

## Setup
Branch `task-020` in the worktree, seven commits on `383c7a1`. `main` has
moved (a licence file, and task 022 is in progress there) — do not rebase
yet; the rebase happens on the 23rd, before anything else. Commit
`task 024:` on `task-020`.

## Why
Everything 020–023b built assumes a state directory exists. A user who
has run characterize → simulate on their own corpus has no way into the
lab at all. This task is the way in.

A local server rather than a generated file, decided: a corpus of any
size works without baking it into a document, the *run this ε* action
from 021b becomes possible, and 023b's render-on-release mode has
somewhere to live. The cost is a process and a port, and that cost is
paid in this task by making both boring.

## Do

1. **The command.** `oneground lab <workdir>` — where `<workdir>` is a
   run's directory containing `state/`, `simulate.json`,
   `characterization.json` and, if present, `verify.json` and
   `report.json`. It starts a server, prints one line with the URL, and
   opens nothing automatically. `--port` (default an ephemeral port),
   `--host` (default `127.0.0.1`, and a non-loopback value requires an
   explicit `--i-know` flag with a printed warning naming what is
   exposed). `--no-browser` is the default; `--open` opens one.
   Ctrl-C shuts down cleanly and says so.

2. **Read-only, and provably.** The server never writes to the workdir,
   never writes anywhere else, and holds no state of its own beyond the
   loaded state. A test asserts the workdir's digests are unchanged after
   a session that exercised every endpoint. The one exception is the
   *run this ε* action in item 5, which does not write either — it prints
   a command for the user to run.

3. **Serve state, not computation.** Endpoints return what the views in
   `oneground/lab/views/` produce, through the 021 contract — the server
   is a transport, not a second renderer. Any view the server exposes
   must already exist as a view; adding an endpoint that computes
   something is the defect this task must not introduce, and the contract
   guard must still pass over everything the server imports.

4. **Render mode chosen by measurement, per 023b.** On start, the server
   times a whole ground draw for this corpus, several times, and picks
   *redraw on move* only if the p95 fits one frame; otherwise *render on
   release*. It prints which mode it chose and why, with the measured
   p95, and the mode is visible in the interface — a lab that silently
   behaves differently on a slow host is the defect 023b named. `--mode`
   overrides with the same caption behaviour.

5. **The ε contract, unchanged from 021b.** Geometry recounts as ε moves.
   Recall, candidates and missed neighbours appear only at simulated ε;
   between them the panel reads *not simulated at this epsilon*, names
   the simulated values, gives the cost in minutes from the recorded
   timings, and prints the exact `oneground simulate … --emit-state`
   command to produce it. The server does not run it.

6. **The interface.** Two views to start: the ground and the query trace,
   as the design study shows them. Use the project's tokens from
   `docs/design/`. No external requests of any kind — fonts, scripts,
   data, all served locally or bundled — the same rule the teaser holds
   to, and here it is also a security property. A `check` endpoint or
   page footer states: the workdir it is serving, the run's digests, and
   the render mode.

7. **Security, stated and tested.** Loopback by default; no write path;
   no path traversal out of the workdir (test it with `../` and absolute
   paths); no directory listing; no CORS; and the printed URL carries a
   random token that must be present on every request, so another local
   process cannot read a colleague's corpus off their machine. Say in
   `docs/LAB.md` what the token does and does not protect against.

8. **Prove it on a real run.** Start it against the arXiv-150k workdir
   and against a 20k run, and report for each: startup time, the chosen
   mode with its measured p95, memory held, and that the workdir's
   digests are unchanged afterwards. Paste the startup line verbatim.

9. **Docs.** `docs/LAB.md` — what the command does, the two views, the ε
   rule, the render modes, the security model and its limits, and one
   sentence on why this is a server rather than a file.

## Acceptance
- `oneground lab <workdir>` serves both views from a real run; startup
  line pasted for both sizes.
- Workdir digests unchanged after a full session; test asserts it.
- Contract guard passes over the server's imports; no endpoint computes.
- Render mode measured, printed, and visible in the interface.
- Path traversal, token absence, and non-loopback without `--i-know` all
  refused, each with a test.
- No external requests; `docs/LAB.md` exists.

## Do not
- Write to the workdir. Run a simulate from the server. Add a view that
  is not a view. Rebase before the 23rd. Touch `main` or `site/teaser/`.
